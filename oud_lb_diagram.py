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
    python oud_lb_diagram.py                          # looks for 'config.ldif' in cwd
    python oud_lb_diagram.py --version                 # print version and exit
    python oud_lb_diagram.py <config> --output <file>   # save diagram to file instead of stdout
    python oud_lb_diagram.py <config> --no-tree          # print only network groups + backend table
    python oud_lb_diagram.py <config> --anonymize        # mask real backend IPs with RFC 5737 placeholders
    python oud_lb_diagram.py <config> --format json      # output the parsed model as JSON instead of the ASCII diagram

See CHANGELOG.md for version history.
"""

__version__ = "1.9.1"

import sys
import io
import json
from collections import defaultdict

try:
    from oud_ldif_core import parse_ldif, first, cn_of
except ImportError:
    print('[ERROR] oud_lb_diagram.py requires oud_ldif_core.py in the same directory.')
    sys.exit(1)

MIN_W = 60   # minimum diagram width
MAX_W = 200  # safety cap so a single rogue line can't blow up the layout

# ─────────────────────────────────────────────────────────────────────────────
# JAVA CLASS CONSTANTS  (fragments matched against ds-cfg-java-class)
# ─────────────────────────────────────────────────────────────────────────────

JC_LOAD_BALANCING_WE = 'LoadBalancingWorkflowElement'
JC_PROXY_LDAP_WE     = 'ProxyLdapWorkflowElement'
JC_LDAP_SERVER_EXT   = 'LDAPServerExtension'

JC_ALGO_PROPORTIONAL = 'Proportional'
JC_ALGO_FAILOVER     = 'Failover'
JC_ALGO_ROUND_ROBIN  = 'RoundRobin'

ALGO_LABELS = {
    JC_ALGO_PROPORTIONAL: 'PROPORTIONAL',
    JC_ALGO_FAILOVER:     'FAILOVER',
    JC_ALGO_ROUND_ROBIN:  'ROUND-ROBIN',
}

# ─────────────────────────────────────────────────────────────────────────────
# CLASSIFIERS
# ─────────────────────────────────────────────────────────────────────────────

def is_lb_we(entry):
    return JC_LOAD_BALANCING_WE in first(entry, 'ds-cfg-java-class')

def is_proxy_we(entry):
    return JC_PROXY_LDAP_WE in first(entry, 'ds-cfg-java-class')

def is_extension(entry):
    return JC_LDAP_SERVER_EXT in first(entry, 'ds-cfg-java-class')

def algo_type(jc):
    for fragment, label in ALGO_LABELS.items():
        if fragment in jc:
            return label
    return jc.split('.')[-1]

# ─────────────────────────────────────────────────────────────────────────────
# MODEL EXTRACTION
# ─────────────────────────────────────────────────────────────────────────────

def _extract_extensions(entries):
    """LDAPServerExtension entries: backend connection details."""
    extensions = {}
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
                'enabled':     first(e, 'ds-cfg-enabled', 'true'),
            }
    return extensions


def _extract_proxy_we(entries):
    """ProxyLdapWorkflowElement entries: leaf nodes pointing at an extension."""
    proxy_we = {}
    for dn, e in entries.items():
        if is_proxy_we(e):
            proxy_we[dn] = {
                'cn':           first(e, 'cn'),
                'extension_dn': first(e, 'ds-cfg-ldap-server-extension').lower(),
                'cred_mode':    first(e, 'ds-cfg-client-cred-mode', '-'),
                'enabled':      first(e, 'ds-cfg-enabled', 'true'),
            }
    return proxy_we


def _extract_workflows(entries):
    """Workflow entries (ds-cfg-workflow, excluding *-workflow-element)."""
    workflows = {}
    for dn, e in entries.items():
        oc = ' '.join(e.get('objectclass', []))
        if 'ds-cfg-workflow' in oc.lower() and 'ds-cfg-workflow-element' not in oc.lower():
            workflows[dn] = {
                'cn':          first(e, 'cn'),
                'base_dn':     first(e, 'ds-cfg-base-dn'),
                'entry_we_dn': first(e, 'ds-cfg-workflow-element').lower(),
            }
    return workflows


def _extract_network_groups(entries):
    """Network group entries: the client-facing entry point."""
    network_groups = []
    for dn, e in entries.items():
        oc = ' '.join(e.get('objectclass', []))
        if 'ds-cfg-network-group' in oc.lower():
            network_groups.append({
                'dn':          dn,
                'cn':          first(e, 'cn'),
                'workflow_dn': first(e, 'ds-cfg-workflow').lower(),
                'priority':    first(e, 'ds-cfg-priority', '-'),
                'enabled':     first(e, 'ds-cfg-enabled', 'true'),
            })
    return network_groups


def _extract_route_algorithm(entries, lb_we_dn):
    """Resolve the cn=algorithm,<lb_we_dn> child entry, if present."""
    algo_dn = f'cn=algorithm,{lb_we_dn}'  # dn is already lowercase
    if algo_dn not in entries:
        return None
    ae  = entries[algo_dn]
    ajc = first(ae, 'ds-cfg-java-class')
    sb  = first(ae, 'ds-cfg-switch-back', 'false').lower() == 'true'
    return {'type': algo_type(ajc), 'switch_back': sb, 'java_class': ajc}


def _extract_routes(entries, lb_we_dn):
    """Collect and sort all route children under cn=routes,cn=algorithm,<lb_we_dn>."""
    routes_parent = f'cn=routes,cn=algorithm,{lb_we_dn}'  # already lowercase
    ops = ('search', 'bind', 'add', 'modify', 'delete', 'compare', 'modifydn', 'extended')
    routes = []

    for rdn, re_ in entries.items():
        if ',' not in rdn:
            continue
        parent_dn = rdn.split(',', 1)[1]  # already lowercase
        if parent_dn != routes_parent:
            continue

        child_we = first(re_, 'ds-cfg-workflow-element').lower()

        priorities = {}
        for op in ops:
            v = first(re_, f'ds-cfg-{op}-priority', '')
            if v.isdigit():
                priorities[op] = int(v)

        weights = {}
        for op in ops:
            w = first(re_, f'ds-cfg-{op}-weight', '')
            if w.isdigit():
                weights[op] = int(w)

        # use cn attribute value (preserves original casing); fallback to cn_of(dn)
        route_cn = first(re_, 'cn') or cn_of(rdn)
        routes.append({
            'cn': route_cn, 'dn': rdn,
            'we_dn': child_we, 'priorities': priorities, 'weights': weights,
        })

    if routes and any(r['priorities'] for r in routes):
        routes.sort(key=lambda r: min(r['priorities'].values()) if r['priorities'] else 999)

    return routes


def _extract_lb_we(entries):
    """LoadBalancingWorkflowElement entries, with their algorithm and routes."""
    lb_we = {}
    for dn, e in entries.items():
        if not is_lb_we(e):
            continue
        lb_we[dn] = {
            'cn':        first(e, 'cn'),
            'enabled':   first(e, 'ds-cfg-enabled', 'true'),
            'algorithm': _extract_route_algorithm(entries, dn),
            'routes':    _extract_routes(entries, dn),
        }
    return lb_we


def extract_model(entries):
    """
    Build the full object model from parsed LDIF entries. Delegates each
    object category to its own extractor (C1) so each stays focused and
    testable in isolation.
    """
    return {
        'extensions':     _extract_extensions(entries),
        'proxy_we':       _extract_proxy_we(entries),
        'lb_we':          _extract_lb_we(entries),
        'network_groups': _extract_network_groups(entries),
        'workflows':      _extract_workflows(entries),
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

def disabled_marker(*enabled_flags):
    """
    O3 — return a visible marker if any given ds-cfg-enabled value is 'false'.
    Used for both LB WE nodes and proxy WE leaves so a disabled component is
    never silently indistinguishable from an active one in the diagram.
    """
    if any(str(f).lower() == 'false' for f in enabled_flags):
        return '  !! DISABLED'
    return ''


def render_tree(we_dn, model, prefix='', is_last=True, file=None):
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
        # flag disablement at either the WE level or the underlying extension
        # level — either one means this route is effectively unusable
        marker = disabled_marker(p.get('enabled', 'true'), ext.get('enabled', 'true'))
        print(f'{prefix}{connector}{p["cn"]}'
              f'  →  {addr}  port:{port}  SSL:{ssl}  ({pol})'
              f'  cred:{cred}{marker}', file=file)
        return

    # ── LB WE ────────────────────────────────────────────────────────────────
    if we_dn in lb_we:
        info = lb_we[we_dn]
        enab = disabled_marker(info['enabled'])
        print(f'{prefix}{connector}{info["cn"]}  {fmt_algo(info["algorithm"])}{enab}', file=file)

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
            print(f'{child_pfx}{r_con}{route["cn"]}{prio_s}{w_s}', file=file)

            render_tree(route['we_dn'], model, prefix=r_pfx, is_last=True, file=file)
        return

    # ── UNKNOWN ──────────────────────────────────────────────────────────────
    print(f'{prefix}{connector}[?] {cn_of(we_dn)}  (not resolved)', file=file)

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
    SEP = object()  # sentinel: render as a full-width separator at print time

    def __init__(self, title):
        self.title = title
        self.lines = []

    def add(self, text=''):
        self.lines.append(text)

    def add_separator(self):
        self.lines.append(Section.SEP)

    def content_width(self):
        widths = [len(self.title) + 2]  # "  TITLE"
        widths += [len(l) + 2 for l in self.lines if l is not Section.SEP]
        return max(widths) if widths else 0


def build_network_groups_section(model):
    sec = Section('NETWORK GROUPS')
    ngs = model['network_groups']
    wfs = model['workflows']
    if not ngs:
        sec.add('(none found)')
    for ng in sorted(ngs, key=lambda x: x.get('priority', '0')):
        wf_info = wfs.get(ng['workflow_dn'], {})
        wf_cn = wf_info.get('cn') or cn_of(ng['workflow_dn'])
        sec.add(f'cn={ng["cn"]}  priority:{ng["priority"]}  enabled:{ng["enabled"]}'
                f'  →  workflow:{wf_cn}  base-dn:{wf_info.get("base_dn","?")}')
    return sec


def build_workflow_tree_sections(model):
    """
    One boxed section per workflow tree: title + the full rendered tree body
    captured into the section (instead of printed unframed). This makes the
    tree's own width count toward the overall box width (fixes O1) and
    gives it the same frame as every other section (fixes O2).
    """
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
        wf_cn = wf_info.get('cn') or cn_of(wf_dn)
        sec = Section(f'WORKFLOW TREE  —  {wf_cn}  —  base-dn: {base_dn}')

        entry_we = wf_info.get('entry_we_dn', '')
        if not entry_we:
            sec.add('[!] No entry workflow element found.')
        else:
            buf = io.StringIO()
            render_tree(entry_we, model, prefix='', is_last=True, file=buf)
            for line in buf.getvalue().splitlines():
                sec.add(line)

        sections.append(sec)
    return sections


# ─────────────────────────────────────────────────────────────────────────────
# BACKEND TABLE COLUMN WIDTHS  (single source of truth for header + rows)
# ─────────────────────────────────────────────────────────────────────────────

COL_EXTENSION = 10
COL_WE        = 14
COL_IP        = 18
COL_PORT      = 6
COL_SSL       = 6
COL_POLICY    = 8
COL_POOL      = 7


def build_backend_servers_section(model):
    sec = Section('BACKEND SERVERS')
    pwe  = model['proxy_we']
    exts = model['extensions']
    hdr = (f'{"Extension":<{COL_EXTENSION}}  {"WE":<{COL_WE}}  {"IP Address":<{COL_IP}}  '
           f'{"Port":<{COL_PORT}}  {"SSL":<{COL_SSL}}  {"Policy":<{COL_POLICY}}  '
           f'{"Pool":<{COL_POOL}}  Cred-mode')
    sec.add(hdr)
    sec.add_separator()
    for pwe_dn in sorted(pwe.keys(), key=lambda d: pwe[d]['cn']):
        p   = pwe[pwe_dn]
        ext = exts.get(p['extension_dn'], {})
        marker = disabled_marker(p.get('enabled', 'true'), ext.get('enabled', 'true'))
        sec.add(f'{ext.get("cn","?"):<{COL_EXTENSION}}  {p["cn"]:<{COL_WE}}  '
                f'{ext.get("address","?"):<{COL_IP}}  {ext.get("port","?"):<{COL_PORT}}  '
                f'{ext.get("ssl_port","?"):<{COL_SSL}}  {ext.get("ssl_policy","?"):<{COL_POLICY}}  '
                f'{ext.get("pool_max","?"):<{COL_POOL}}  {p.get("cred_mode","?")}{marker}')
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
        '!! DISABLED    ds-cfg-enabled: false on this WE or its backend extension — inactive.',
    ]:
        sec.add(l)
    return sec


def print_section(sec, w, file=None):
    print('┌' + '─' * (w - 2) + '┐', file=file)
    print('│' + ('  ' + sec.title).ljust(w - 2) + '│', file=file)
    print('├' + '─' * (w - 2) + '┤', file=file)
    for l in sec.lines:
        if l is Section.SEP:
            print('│' + ('  ' + '-' * (w - 6)).ljust(w - 2) + '│', file=file)
        else:
            print('│' + ('  ' + l).ljust(w - 2) + '│', file=file)
    print('└' + '─' * (w - 2) + '┘', file=file)


def print_header(w, file=None):
    title = ' OUD PROXY — LOAD BALANCING ARCHITECTURE '
    print(file=file)
    print('╔' + '═' * (w - 2) + '╗', file=file)
    print('║' + title.center(w - 2) + '║', file=file)
    print('╚' + '═' * (w - 2) + '╝', file=file)
    print(file=file)


def print_diagram(model, file=None, no_tree=False):
    ngs_sec = build_network_groups_section(model)
    wf_sections = build_workflow_tree_sections(model)  # now full boxed sections (O1+O2)
    backend_sec = build_backend_servers_section(model)
    legend_sec = build_legend_section()

    # Width is computed once from every boxed section, so all frames line up.
    # Tree sections now carry their own rendered content, so their indentation
    # and node labels count toward the width just like any other section.
    candidates = [ngs_sec.content_width(), backend_sec.content_width(), legend_sec.content_width()]
    if not no_tree:
        candidates += [sec.content_width() for sec in wf_sections]
    title_width = len(' OUD PROXY — LOAD BALANCING ARCHITECTURE ') + 2
    candidates.append(title_width)
    # content_width() = len("  " + longest_line), i.e. left margin (2) + text.
    # w-2 must equal that plus a matching 2-space right margin, so both
    # borders have identical padding on the longest line in the box.
    w = (max(candidates) if candidates else MIN_W) + 4
    w = max(MIN_W, min(MAX_W, w))

    print_header(w, file=file)

    print_section(ngs_sec, w, file=file)
    print(file=file)

    if no_tree:
        print('  [--no-tree] Workflow tree(s) skipped.', file=file)
        print(file=file)
    else:
        for sec in wf_sections:
            print_section(sec, w, file=file)
            print(file=file)

    print_section(backend_sec, w, file=file)
    print(file=file)

    print_section(legend_sec, w, file=file)
    print(file=file)

# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def parse_args(argv):
    """
    Minimal hand-rolled arg parser (no external deps).
    Supports:
      <path>                positional config file (optional, default 'config.ldif')
      --version / -v        print version and exit
      --output <file>       write diagram/JSON to file instead of stdout
      --no-tree             skip workflow tree section(s) (text format only)
      --anonymize           replace real backend IPs with documentation-range placeholders
      --format text|json    output format (default: text). YAML isn't offered
                             since it isn't in the standard library and this
                             project has no external dependencies — pipe the
                             JSON output through a YAML converter if needed.
    """
    args = {'path': None, 'output': None, 'no_tree': False, 'version': False,
            'anonymize': False, 'format': 'text'}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ('--version', '-v'):
            args['version'] = True
        elif a == '--output':
            i += 1
            if i >= len(argv):
                print('[ERROR] --output requires a file path')
                sys.exit(1)
            args['output'] = argv[i]
        elif a == '--no-tree':
            args['no_tree'] = True
        elif a == '--anonymize':
            args['anonymize'] = True
        elif a == '--format':
            i += 1
            if i >= len(argv):
                print('[ERROR] --format requires a value (text or json)')
                sys.exit(1)
            fmt = argv[i]
            if fmt not in ('text', 'json'):
                print(f'[ERROR] Unsupported --format value: {fmt!r} '
                      f'(supported: text, json — YAML requires an external '
                      f'dependency not used by this project; convert the '
                      f'JSON output instead if you need YAML)')
                sys.exit(1)
            args['format'] = fmt
        elif a.startswith('--'):
            print(f'[ERROR] Unknown option: {a}')
            sys.exit(1)
        elif args['path'] is None:
            args['path'] = a
        else:
            print(f'[ERROR] Unexpected argument: {a}')
            sys.exit(1)
        i += 1
    if args['path'] is None:
        args['path'] = 'config.ldif'
    return args


def find_duplicate_cn_warnings(model):
    """
    B5 — internal lookups always use the full DN as key, so routing/rendering
    stays correct even if two entries share the same cn under different
    parents. But identical labels in the diagram can still mislead a human
    reader (e.g. two distinct proxy-we entries both showing as "proxy-we5").
    This scans each object category and warns about such display collisions.
    """
    warnings = []
    categories = {
        'proxy WE':  model['proxy_we'],
        'LB WE':     model['lb_we'],
        'extension': model['extensions'],
    }
    for label, objects in categories.items():
        by_cn = defaultdict(list)
        for dn, obj in objects.items():
            by_cn[obj['cn']].append(dn)
        for cn, dns in by_cn.items():
            if len(dns) > 1:
                warnings.append(
                    f'duplicate {label} cn "{cn}" used by {len(dns)} distinct entries '
                    f'(routing is still correct — each is resolved by its full DN, '
                    f'but the diagram will show "{cn}" more than once): '
                    + ' | '.join(dns)
                )
    return warnings


# ─────────────────────────────────────────────────────────────────────────────
# ANONYMIZATION  (F3)
# ─────────────────────────────────────────────────────────────────────────────

# RFC 5737 documentation ranges — safe to publish, never routable.
ANONYMIZE_RANGES = ['198.51.100', '203.0.113', '192.0.2']


def anonymize_model(model):
    """
    Replace every real backend IP in model['extensions'] with a placeholder
    from an RFC 5737 documentation range, using a stable mapping so the same
    real IP always maps to the same placeholder (needed since the same
    extension can be referenced by multiple proxy WEs / routes).
    Mutates model in place. Returns the number of unique IPs replaced.
    """
    mapping = {}
    next_index = 1

    # deterministic order: sort by DN so repeated runs produce the same mapping
    for dn in sorted(model['extensions'].keys()):
        ext = model['extensions'][dn]
        real_ip = ext.get('address', '')
        if not real_ip or real_ip == '?':
            continue
        if real_ip not in mapping:
            range_idx = (next_index - 1) // 254
            octet     = ((next_index - 1) % 254) + 1
            if range_idx >= len(ANONYMIZE_RANGES):
                # exhausted all documentation ranges — extremely unlikely,
                # fall back to a clearly-fake but non-standard marker
                mapping[real_ip] = f'198.51.100.{octet}-overflow{range_idx}'
            else:
                mapping[real_ip] = f'{ANONYMIZE_RANGES[range_idx]}.{octet}'
            next_index += 1
        ext['address'] = mapping[real_ip]

    return len(mapping)


def main():
    args = parse_args(sys.argv[1:])

    if args['version']:
        print(f'oud_lb_diagram.py v{__version__}')
        sys.exit(0)

    # When emitting JSON, all diagnostic/status lines go to stderr so that
    # stdout stays pure, pipeable JSON even without --output (e.g. so that
    # `oud_lb_diagram.py config.ldif --format json | jq .` works cleanly).
    # In text mode (default) diagnostics stay on stdout, unchanged from
    # every previous version.
    diag = sys.stderr if args['format'] == 'json' else sys.stdout

    path = args['path']
    try:
        entries, parse_warnings = parse_ldif(path)
    except FileNotFoundError:
        print(f'[ERROR] File not found: {path}')
        print('Usage: python oud_lb_diagram.py <path-to-config.ldif> [--output <file>] [--no-tree]')
        sys.exit(1)

    # Header / warnings always go to `diag`, even when the diagram/JSON is
    # saved to a file via --output
    print(f'\n[+] Parsed {len(entries)} LDIF entries from: {path}', file=diag)
    for w in parse_warnings:
        print(f'[WARN] {w}', file=diag)

    model = extract_model(entries)

    if args['anonymize']:
        n = anonymize_model(model)
        print(f'[+] --anonymize: replaced {n} unique backend IP(s) with '
              f'RFC 5737 documentation-range placeholders', file=diag)

    # B7 — early warning if this doesn't look like an OUD Proxy config.
    # Soft dependency: oud_config_type.py may not be present alongside this
    # script (e.g. if only oud_lb_diagram.py was copied out on its own),
    # in which case this check is silently skipped rather than failing.
    try:
        from oud_config_type import classify_ldif_entries
        primary_type, _secondary, confidence, _signals = classify_ldif_entries(entries)
        if not primary_type.startswith('OUD Proxy'):
            print(f'[WARN] Config does not look like an OUD Proxy instance '
                  f'(detected: "{primary_type}", confidence: {confidence}). '
                  f'This tool targets OUD Proxy configs specifically — the diagram below '
                  f'may be empty or incomplete. Run oud_config_type.py for details.', file=diag)
    except ImportError:
        pass

    # B4 — warn on unresolved workflow-element DN references
    # B6 — warn on network groups with no workflow reference at all
    #      (distinct from B4: here ds-cfg-workflow is empty/missing, not
    #      pointing at something nonexistent — the previous check silently
    #      skipped this case because `if wf_dn and ...` short-circuits on
    #      an empty string).
    all_we = set(model['lb_we']) | set(model['proxy_we'])
    for ng in model['network_groups']:
        wf_dn = ng['workflow_dn']
        if not wf_dn:
            print(f'[WARN] network-group "{ng["cn"]}" has no workflow configured '
                  f'(ds-cfg-workflow is empty) — it will show as base-dn:? with no tree.', file=diag)
        elif wf_dn not in model['workflows']:
            print(f'[WARN] network-group "{ng["cn"]}" references unknown workflow: {wf_dn}', file=diag)
    for wf_dn, wf in model['workflows'].items():
        if wf['entry_we_dn'] and wf['entry_we_dn'] not in all_we:
            print(f'[WARN] workflow "{wf["cn"]}" references unknown WE: {wf["entry_we_dn"]}', file=diag)
    for lb_dn, lb in model['lb_we'].items():
        for r in lb['routes']:
            if r['we_dn'] and r['we_dn'] not in all_we:
                print(f'[WARN] route "{r["cn"]}" in "{lb["cn"]}" references unknown WE: {r["we_dn"]}', file=diag)
    for pwe_dn, pwe in model['proxy_we'].items():
        if pwe['extension_dn'] and pwe['extension_dn'] not in model['extensions']:
            print(f'[WARN] proxy-we "{pwe["cn"]}" references unknown extension: {pwe["extension_dn"]}', file=diag)

    # B5 — warn on duplicate display CNs (routing correctness unaffected)
    for w in find_duplicate_cn_warnings(model):
        print(f'[WARN] {w}', file=diag)

    print(f'[+] Found: {len(model["network_groups"])} network group(s)  '
          f'{len(model["workflows"])} workflow(s)  '
          f'{len(model["lb_we"])} LB WE(s)  '
          f'{len(model["proxy_we"])} proxy WE(s)  '
          f'{len(model["extensions"])} backend extension(s)', file=diag)

    if args['format'] == 'json':
        if args['no_tree']:
            print('[+] Note: --no-tree has no effect with --format json '
                  '(the JSON payload always contains the full model).', file=diag)
        payload = {
            'tool': 'oud_lb_diagram.py',
            'tool_version': __version__,
            'source_file': path,
            'anonymized': args['anonymize'],
            'model': model,
        }
        json_text = json.dumps(payload, indent=2, ensure_ascii=False)
        if args['output']:
            try:
                with open(args['output'], 'w', encoding='utf-8') as out:
                    out.write(json_text + '\n')
                print(f'[+] JSON written to: {args["output"]}', file=diag)
            except OSError as ex:
                print(f'[ERROR] Could not write to {args["output"]}: {ex}', file=diag)
                sys.exit(1)
        else:
            print(json_text)
    elif args['output']:
        try:
            with open(args['output'], 'w', encoding='utf-8') as out:
                print_diagram(model, file=out, no_tree=args['no_tree'])
            print(f'[+] Diagram written to: {args["output"]}', file=diag)
        except OSError as ex:
            print(f'[ERROR] Could not write to {args["output"]}: {ex}')
            sys.exit(1)
    else:
        print_diagram(model, no_tree=args['no_tree'])

if __name__ == '__main__':
    main()
