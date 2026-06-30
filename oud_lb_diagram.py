#!/usr/bin/env python3
"""
oud_lb_diagram.py
-----------------
Reads an Oracle Unified Directory (OUD) proxy config file (LDIF format)
and prints a generic text-based load-balancing architecture diagram.

The script explores the workflow element tree dynamically at any depth,
showing algorithms, weights, priorities and backend IPs as-is from the config.
Semantic interpretation (e.g. WRITE vs READ) is left to the reader.

Usage:
    python oud_lb_diagram.py <path-to-config.ldif>
    python oud_lb_diagram.py                        # looks for 'config.ldif' in cwd
    python oud_lb_diagram.py --version               # print version and exit

See CHANGELOG.md for version history.
"""

__version__ = "1.1.0"

import sys
import re
from collections import defaultdict

MIN_W = 60   # minimum diagram width
MAX_W = 200  # safety cap so a single rogue line can't blow up the layout

# ─────────────────────────────────────────────────────────────────────────────
# LDIF PARSER
# ─────────────────────────────────────────────────────────────────────────────

def parse_ldif(path):
    entries = {}
    current_dn = None
    current = defaultdict(list)
    with open(path, encoding='utf-8', errors='replace') as fh:
        for raw in fh:
            line = raw.rstrip('\n')
            if line.strip() == '':
                if current_dn:
                    entries[current_dn] = dict(current)
                current_dn = None
                current = defaultdict(list)
                continue
            if line.startswith('#') or ':' not in line:
                continue
            key, _, val = line.partition(':')
            key = key.strip().lower()
            val = val.lstrip(' ').rstrip()
            if key == 'dn':
                current_dn = val
                current = defaultdict(list)
            elif current_dn is not None:
                current[key].append(val)
    if current_dn and current:
        entries[current_dn] = dict(current)
    return entries


def first(entry, attr, default=''):
    return entry.get(attr, [default])[0]

def cn_of(dn):
    m = re.match(r'cn=([^,]+)', dn, re.IGNORECASE)
    return m.group(1) if m else dn

# ─────────────────────────────────────────────────────────────────────────────
# CLASSIFIERS
# ─────────────────────────────────────────────────────────────────────────────

def is_lb_we(entry):
    return 'LoadBalancingWorkflowElement' in first(entry, 'ds-cfg-java-class')

def is_proxy_we(entry):
    return 'ProxyLdapWorkflowElement' in first(entry, 'ds-cfg-java-class')

def is_extension(entry):
    return 'LDAPServerExtension' in first(entry, 'ds-cfg-java-class')

def algo_type(jc):
    if 'Proportional' in jc: return 'PROPORTIONAL'
    if 'Failover'     in jc: return 'FAILOVER'
    if 'RoundRobin'   in jc: return 'ROUND-ROBIN'
    return jc.split('.')[-1]

# ─────────────────────────────────────────────────────────────────────────────
# MODEL EXTRACTION
# ─────────────────────────────────────────────────────────────────────────────

def extract_model(entries):
    extensions     = {}
    proxy_we       = {}
    lb_we          = {}
    network_groups = []
    workflows      = {}

    for dn, e in entries.items():
        if is_extension(e):
            extensions[dn] = {
                'cn':          first(e, 'cn'),
                'address':     first(e, 'ds-cfg-remote-ldap-server-address'),
                'port':        first(e, 'ds-cfg-remote-ldap-server-port', '389'),
                'ssl_port':    first(e, 'ds-cfg-remote-ldap-server-ssl-port', '1636'),
                'ssl_policy':  first(e, 'ds-cfg-remote-ldap-server-ssl-policy', '-'),
                'pool_max':    first(e, 'ds-cfg-pool-max-size', '-'),
                'conn_timeout':first(e, 'ds-cfg-remote-ldap-server-connect-timeout', '-'),
                'read_timeout':first(e, 'ds-cfg-remote-ldap-server-read-timeout', '-'),
                'ssl_trust_all':first(e, 'ds-cfg-ssl-trust-all', 'false'),
            }

    for dn, e in entries.items():
        if is_proxy_we(e):
            proxy_we[dn] = {
                'cn':           first(e, 'cn'),
                'extension_dn': first(e, 'ds-cfg-ldap-server-extension'),
                'cred_mode':    first(e, 'ds-cfg-client-cred-mode', '-'),
            }

    for dn, e in entries.items():
        oc = ' '.join(e.get('objectclass', []))
        if 'ds-cfg-workflow' in oc.lower() and 'ds-cfg-workflow-element' not in oc.lower():
            workflows[dn] = {
                'cn':          first(e, 'cn'),
                'base_dn':     first(e, 'ds-cfg-base-dn'),
                'entry_we_dn': first(e, 'ds-cfg-workflow-element'),
            }

    for dn, e in entries.items():
        oc = ' '.join(e.get('objectclass', []))
        if 'ds-cfg-network-group' in oc.lower():
            network_groups.append({
                'dn':          dn,
                'cn':          first(e, 'cn'),
                'workflow_dn': first(e, 'ds-cfg-workflow'),
                'priority':    first(e, 'ds-cfg-priority', '-'),
                'enabled':     first(e, 'ds-cfg-enabled', 'true'),
            })

    for dn, e in entries.items():
        if not is_lb_we(e):
            continue
        algo_dn   = f'cn=algorithm,{dn}'
        algorithm = None
        for adn, ae in entries.items():
            if adn.lower() == algo_dn.lower():
                ajc = first(ae, 'ds-cfg-java-class')
                sb  = first(ae, 'ds-cfg-switch-back', 'false').lower() == 'true'
                algorithm = {'type': algo_type(ajc), 'switch_back': sb, 'java_class': ajc}
                break

        routes_parent = f'cn=routes,cn=algorithm,{dn}'.lower()
        routes = []
        for rdn, re_ in entries.items():
            if ',' not in rdn:
                continue
            parent_dn = rdn.split(',', 1)[1].lower()
            if parent_dn != routes_parent:
                continue
            child_we = first(re_, 'ds-cfg-workflow-element')
            ops = ('search','bind','add','modify','delete','compare','modifydn','extended')

            # per-operation priorities (failover)
            priorities = {}
            for op in ops:
                v = first(re_, f'ds-cfg-{op}-priority', '')
                if v.isdigit():
                    priorities[op] = int(v)

            # per-operation weights (proportional)
            weights = {}
            for op in ops:
                w = first(re_, f'ds-cfg-{op}-weight', '')
                if w.isdigit():
                    weights[op] = int(w)

            routes.append({
                'cn': cn_of(rdn), 'dn': rdn,
                'we_dn': child_we, 'priorities': priorities, 'weights': weights,
            })

        if routes and any(r["priorities"] for r in routes):
            routes.sort(key=lambda r: min(r["priorities"].values()) if r["priorities"] else 999)

        lb_we[dn] = {
            'cn':        first(e, 'cn'),
            'enabled':   first(e, 'ds-cfg-enabled', 'true'),
            'algorithm': algorithm,
            'routes':    routes,
        }

    return {
        'extensions':     extensions,
        'proxy_we':       proxy_we,
        'lb_we':          lb_we,
        'network_groups': network_groups,
        'workflows':      workflows,
    }

# ─────────────────────────────────────────────────────────────────────────────
# FORMATTERS
# ─────────────────────────────────────────────────────────────────────────────

def fmt_weights(weights):
    if not weights:
        return ''
    groups = defaultdict(list)
    for op, w in weights.items():
        groups[w].append(op)
    parts = []
    for w in sorted(groups.keys(), reverse=True):
        parts.append(f'{"/".join(groups[w])}:{w}')
    return '  '.join(parts)

def fmt_priorities(priorities):
    """
    Group ops by priority value, show compactly.
    If all ops have the same priority → 'all:<N>'
    Otherwise → 'search/bind:1  add/modify:2'
    """
    if not priorities:
        return ''
    groups = defaultdict(list)
    for op, p in priorities.items():
        groups[p].append(op)
    # if single group covering all ops
    if len(groups) == 1:
        p = list(groups.keys())[0]
        return f'all:{p}'
    parts = []
    for p in sorted(groups.keys()):
        parts.append(f'{"/".join(groups[p])}:{p}')
    return '  '.join(parts)

def fmt_algo(algo):
    if not algo:
        return ''
    sb = '  switch-back:ON' if algo.get('switch_back') else ''
    return f'[{algo["type"]}{sb}]'

# ─────────────────────────────────────────────────────────────────────────────
# RECURSIVE TREE RENDERER
# ─────────────────────────────────────────────────────────────────────────────

def render_tree(we_dn, model, prefix='', is_last=True):
    lb_we      = model['lb_we']
    proxy_we   = model['proxy_we']
    extensions = model['extensions']

    connector = '└─ ' if is_last else '├─ '
    child_pfx = prefix + ('   ' if is_last else '│  ')

    # ── PROXY WE (leaf) ──────────────────────────────────────────────────────
    if we_dn in proxy_we:
        p    = proxy_we[we_dn]
        ext  = extensions.get(p['extension_dn'], {})
        addr = ext.get('address', '?')
        port = ext.get('port', '?')
        ssl  = ext.get('ssl_port', '?')
        pol  = ext.get('ssl_policy', '?')
        cred = p.get('cred_mode', '?')
        print(f'{prefix}{connector}{p["cn"]}'
              f'  →  {addr}  port:{port}  SSL:{ssl}  ({pol})'
              f'  cred:{cred}')
        return

    # ── LB WE ────────────────────────────────────────────────────────────────
    if we_dn in lb_we:
        info = lb_we[we_dn]
        enab = '' if info['enabled'] == 'true' else '  [DISABLED]'
        print(f'{prefix}{connector}{info["cn"]}  {fmt_algo(info["algorithm"])}{enab}')

        routes = info['routes']
        for i, route in enumerate(routes):
            last  = (i == len(routes) - 1)
            r_con = '└─ ' if last else '├─ '
            r_pfx = child_pfx + ('   ' if last else '│  ')

            prio_s = ''
            if route['priorities']:
                prio_s = f'  prio: {fmt_priorities(route["priorities"])}'
            w_s = ''
            if route['weights']:
                w_s = f'  weights: {fmt_weights(route["weights"])}'
            print(f'{child_pfx}{r_con}{route["cn"]}{prio_s}{w_s}')

            render_tree(route['we_dn'], model, prefix=r_pfx, is_last=True)
        return

    # ── UNKNOWN ──────────────────────────────────────────────────────────────
    print(f'{prefix}{connector}[?] {cn_of(we_dn)}  (not resolved)')

# ─────────────────────────────────────────────────────────────────────────────
# DIAGRAM
#
# Boxed sections (network groups / workflow-tree headers / backend servers /
# legend) are built as plain text first, so the frame width can be computed
# from actual content instead of a hardcoded constant. The workflow tree body
# itself stays unframed (rendered separately, as before).
# ─────────────────────────────────────────────────────────────────────────────

class Section:
    """A titled box whose body lines are collected before being framed."""
    def __init__(self, title):
        self.title = title
        self.lines = []

    def add(self, text=''):
        self.lines.append(text)

    def content_width(self):
        widths = [len(self.title) + 2]  # "  TITLE"
        widths += [len(l) + 2 for l in self.lines]  # "  line"
        return max(widths) if widths else 0


def build_network_groups_section(model):
    sec = Section('NETWORK GROUPS')
    ngs = model['network_groups']
    wfs = model['workflows']
    if not ngs:
        sec.add('(none found)')
    for ng in sorted(ngs, key=lambda x: x.get('priority', '0')):
        wf_info = wfs.get(ng['workflow_dn'], {})
        sec.add(f'cn={ng["cn"]}  priority:{ng["priority"]}  enabled:{ng["enabled"]}'
                f'  →  workflow:{cn_of(ng["workflow_dn"])}  base-dn:{wf_info.get("base_dn","?")}')
    return sec


def build_workflow_header_sections(model):
    """One small header box per workflow tree (title only, body printed unframed)."""
    sections = []
    ngs = model['network_groups']
    wfs = model['workflows']
    printed = set()
    for ng in sorted(ngs, key=lambda x: x.get('priority', '0')):
        wf_dn = ng['workflow_dn']
        if wf_dn in printed:
            continue
        printed.add(wf_dn)
        wf_info = wfs.get(wf_dn, {})
        base_dn = wf_info.get('base_dn', '?')
        sec = Section(f'WORKFLOW TREE  —  {cn_of(wf_dn)}  —  base-dn: {base_dn}')
        sections.append((wf_dn, wf_info, sec))
    return sections


def build_backend_servers_section(model):
    sec = Section('BACKEND SERVERS')
    pwe  = model['proxy_we']
    exts = model['extensions']
    hdr = f'{"Extension":<10}  {"WE":<14}  {"IP Address":<18}  {"Port":<6}  {"SSL":<6}  {"Policy":<8}  {"Pool":<7}  Cred-mode'
    sec.add(hdr)
    sec.add('-' * len(hdr))
    for pwe_dn in sorted(pwe.keys(), key=lambda d: pwe[d]['cn']):
        p   = pwe[pwe_dn]
        ext = exts.get(p['extension_dn'], {})
        sec.add(f'{ext.get("cn","?"):<10}  {p["cn"]:<14}  '
                f'{ext.get("address","?"):<18}  {ext.get("port","?"):<6}  '
                f'{ext.get("ssl_port","?"):<6}  {ext.get("ssl_policy","?"):<8}  '
                f'{ext.get("pool_max","?"):<7}  {p.get("cred_mode","?")}')
    return sec


def build_legend_section():
    sec = Section('LEGEND')
    for l in [
        'PROPORTIONAL   Distributes traffic by weight per operation type.',
        '               weights shown as  ops:value  —  e.g. add/modify/delete:1  search/bind:0',
        'FAILOVER       One active node at a time; lower [prio] = preferred.',
        '               switch-back:ON = auto-restore to primary when it recovers.',
        'ROUND-ROBIN    Cycles through available routes in order.',
        '└─ <node>      Leaf node = backend proxy WE resolved to IP:port.',
        'cred-mode      How client credentials are forwarded to the backend.',
    ]:
        sec.add(l)
    return sec


def print_section(sec, w):
    print('┌' + '─' * (w - 2) + '┐')
    print('│' + ('  ' + sec.title).ljust(w - 2) + '│')
    print('├' + '─' * (w - 2) + '┤')
    for l in sec.lines:
        print('│' + ('  ' + l).ljust(w - 2) + '│')
    print('└' + '─' * (w - 2) + '┘')


def print_header(w):
    title = ' OUD PROXY — LOAD BALANCING ARCHITECTURE '
    print()
    print('╔' + '═' * (w - 2) + '╗')
    print('║' + title.center(w - 2) + '║')
    print('╚' + '═' * (w - 2) + '╝')
    print()


def print_diagram(model):
    ngs_sec = build_network_groups_section(model)
    wf_sections = build_workflow_header_sections(model)
    backend_sec = build_backend_servers_section(model)
    legend_sec = build_legend_section()

    # Width is computed once from every boxed section, so all frames line up.
    candidates = [ngs_sec.content_width(), backend_sec.content_width(), legend_sec.content_width()]
    candidates += [sec.content_width() for _, _, sec in wf_sections]
    title_width = len(' OUD PROXY — LOAD BALANCING ARCHITECTURE ') + 2
    candidates.append(title_width)
    # content_width() = len(longest "  line") . We need w-2 to be strictly
    # greater than that, so the right border always has at least 1 space gap.
    w = (max(candidates) if candidates else MIN_W) + 3
    w = max(MIN_W, min(MAX_W, w))

    print_header(w)

    print_section(ngs_sec, w)
    print()

    for wf_dn, wf_info, sec in wf_sections:
        print_section(sec, w)
        print()
        entry_we = wf_info.get('entry_we_dn', '')
        if not entry_we:
            print('  [!] No entry workflow element found.')
            print()
            continue
        render_tree(entry_we, model, prefix='  ', is_last=True)
        print()

    print_section(backend_sec, w)
    print()

    print_section(legend_sec, w)
    print()

# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) > 1 and sys.argv[1] in ('--version', '-v'):
        print(f'oud_lb_diagram.py v{__version__}')
        sys.exit(0)

    path = sys.argv[1] if len(sys.argv) > 1 else 'config.ldif'
    try:
        entries = parse_ldif(path)
    except FileNotFoundError:
        print(f'[ERROR] File not found: {path}')
        print('Usage: python oud_lb_diagram.py <path-to-config.ldif>')
        sys.exit(1)

    print(f'\n[+] Parsed {len(entries)} LDIF entries from: {path}')
    model = extract_model(entries)
    print(f'[+] Found: {len(model["network_groups"])} network group(s)  '
          f'{len(model["workflows"])} workflow(s)  '
          f'{len(model["lb_we"])} LB WE(s)  '
          f'{len(model["proxy_we"])} proxy WE(s)  '
          f'{len(model["extensions"])} backend extension(s)')
    print_diagram(model)

if __name__ == '__main__':
    main()
