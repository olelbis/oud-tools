#!/usr/bin/env python3
"""
oud_backend_report.py
-----------------------
Companion to oud_lb_diagram.py (E3): reads an Oracle Unified Directory
(OUD) **Directory Server** config file (LDIF format) — not a proxy — and
prints a text report of local data backends, their indexes, and
replication domains.

Built on the shared oud_ldif_core.py parser (E2), like oud_lb_diagram.py
and oud_config_type.py. All three files must sit in the same directory.

Usage:
    python oud_backend_report.py <path-to-config.ldif>
    python oud_backend_report.py --version
    python oud_backend_report.py <config> --output <file>
    python oud_backend_report.py <config> --anonymize    # mask replication-server IPs with RFC 5737 placeholders

Scope: only genuine user-data backends (ds-cfg-db-local-backend-workflow-element
with ds-cfg-is-private-backend not true) are reported — internal/system
backends (schema, tasks, monitor, backup, trust store, admin) are skipped,
same distinction oud_config_type.py already makes for classification.
"""

__version__ = "1.1.1"

import sys

try:
    from oud_ldif_core import parse_ldif, first
except ImportError:
    print('[ERROR] oud_backend_report.py requires oud_ldif_core.py in the same directory.')
    sys.exit(1)

MIN_W = 60
MAX_W = 200

SYSTEM_BACKEND_OC_FRAGMENTS = (
    'ds-cfg-ldif-local-backend-workflow-element',
    'ds-cfg-trust-store-local-backend-workflow-element',
    'ds-cfg-backup-local-backend-workflow-element',
    'ds-cfg-monitor-local-backend-workflow-element',
    'ds-cfg-schema-local-backend-workflow-element',
    'ds-cfg-task-local-backend-workflow-element',
)
DB_BACKEND_OC_FRAGMENT = 'ds-cfg-db-local-backend-workflow-element'


# ─────────────────────────────────────────────────────────────────────────────
# MODEL EXTRACTION
# ─────────────────────────────────────────────────────────────────────────────

def extract_backends(entries):
    """Genuine user-data DB local backends (excludes system/private ones)."""
    backends = {}
    for dn, e in entries.items():
        oc = ' '.join(e.get('objectclass', [])).lower()
        if DB_BACKEND_OC_FRAGMENT not in oc:
            continue
        if any(frag in oc for frag in SYSTEM_BACKEND_OC_FRAGMENTS):
            continue
        is_private = first(e, 'ds-cfg-is-private-backend', 'false').lower() == 'true'
        if is_private:
            continue
        backends[dn] = {
            'cn':              first(e, 'cn'),
            'base_dn':         first(e, 'ds-cfg-base-dn'),
            'enabled':         first(e, 'ds-cfg-enabled', 'true'),
            'writability':     first(e, 'ds-cfg-writability-mode', '-'),
            'db_directory':    first(e, 'ds-cfg-db-directory', '-'),
            'txn_durability':  first(e, 'ds-cfg-db-txn-durability', '-'),
            'index_entry_limit': first(e, 'ds-cfg-index-entry-limit', '-'),
            'entries_compressed': first(e, 'ds-cfg-entries-compressed', '-'),
        }
    return backends


def extract_indexes(entries, backend_dn, backend_cn):
    """
    Indexes live under cn=Index,<backend_dn>. Note: OUD's own config uses
    inconsistent casing for the parent DN across entries in the wild
    (seen: 'cn=Index,cn=userRoot,cn=Workflow Elements,...' AND
    'cn=Index,cn=userRoot,cn=Workflow elements,...' — lowercase 'elements'),
    but parse_ldif already lowercases every DN, so this is transparent here.
    """
    index_parent = f'cn=index,{backend_dn}'
    indexes = []
    for dn, e in entries.items():
        if not dn.endswith(',' + index_parent) and dn != index_parent:
            continue
        attr = first(e, 'ds-cfg-attribute')
        if not attr:
            continue
        idx_types = e.get('ds-cfg-index-type', [])
        limit = first(e, 'ds-cfg-index-entry-limit', '-')
        indexes.append({'attribute': attr, 'types': idx_types, 'entry_limit': limit})
    indexes.sort(key=lambda i: i['attribute'])
    return indexes


def extract_replication_domains(entries):
    """ds-cfg-replication-domain entries under cn=domains,...,cn=config."""
    domains = []
    for dn, e in entries.items():
        oc = ' '.join(e.get('objectclass', [])).lower()
        if 'ds-cfg-replication-domain' not in oc:
            continue
        domains.append({
            'cn':          first(e, 'cn'),
            'base_dn':     first(e, 'ds-cfg-base-dn'),
            'server_id':   first(e, 'ds-cfg-server-id', '-'),
            'group_id':    first(e, 'ds-cfg-group-id', '-'),
            'servers':     e.get('ds-cfg-replication-server', []),
            'isolation':   first(e, 'ds-cfg-isolation-policy', '-'),
            'window_size': first(e, 'ds-cfg-window-size', '-'),
        })
    domains.sort(key=lambda d: d['base_dn'])
    return domains


# ─────────────────────────────────────────────────────────────────────────────
# TEXT REPORT — minimal boxed-section renderer (mirrors oud_lb_diagram.py style)
# ─────────────────────────────────────────────────────────────────────────────

class Section:
    def __init__(self, title):
        self.title = title
        self.lines = []

    def add(self, text=''):
        self.lines.append(text)

    def content_width(self):
        widths = [len(self.title) + 2] + [len(l) + 2 for l in self.lines]
        return max(widths) if widths else 0


def print_section(sec, w, file=None):
    print('┌' + '─' * (w - 2) + '┐', file=file)
    print('│' + ('  ' + sec.title).ljust(w - 2) + '│', file=file)
    print('├' + '─' * (w - 2) + '┤', file=file)
    for l in sec.lines:
        print('│' + ('  ' + l).ljust(w - 2) + '│', file=file)
    print('└' + '─' * (w - 2) + '┘', file=file)


def print_header(w, file=None):
    title = ' OUD DIRECTORY SERVER — BACKEND REPORT '
    print(file=file)
    print('╔' + '═' * (w - 2) + '╗', file=file)
    print('║' + title.center(w - 2) + '║', file=file)
    print('╚' + '═' * (w - 2) + '╝', file=file)
    print(file=file)


def build_backends_section(entries, backends):
    sec = Section('LOCAL DATA BACKENDS')
    if not backends:
        sec.add('(none found — this may not be a Directory Server config; '
                 'run oud_config_type.py to check)')
        return sec
    for dn, b in sorted(backends.items(), key=lambda x: x[1]['cn']):
        idx_count = len(extract_indexes(entries, dn, b['cn']))
        marker = '  !! DISABLED' if b['enabled'].lower() == 'false' else ''
        sec.add(f'{b["cn"]}  base-dn:{b["base_dn"]}{marker}')
        sec.add(f'  writability:{b["writability"]}  txn-durability:{b["txn_durability"]}  '
                 f'db-dir:{b["db_directory"]}  compressed:{b["entries_compressed"]}  '
                 f'default-index-entry-limit:{b["index_entry_limit"]}  indexes:{idx_count}')
    return sec


def build_indexes_sections(entries, backends):
    sections = []
    for dn, b in sorted(backends.items(), key=lambda x: x[1]['cn']):
        indexes = extract_indexes(entries, dn, b['cn'])
        sec = Section(f'INDEXES  —  {b["cn"]}  ({len(indexes)})')
        if not indexes:
            sec.add('(no indexes found)')
        else:
            sec.add(f'{"Attribute":<30}  {"Type(s)":<30}  Entry Limit')
            sec.add('-' * 70)
            for idx in indexes:
                types_str = '/'.join(idx['types']) if idx['types'] else '-'
                sec.add(f'{idx["attribute"]:<30}  {types_str:<30}  {idx["entry_limit"]}')
        sections.append(sec)
    return sections


def build_replication_section(domains):
    sec = Section('REPLICATION DOMAINS')
    if not domains:
        sec.add('(none found — replication is not configured)')
        return sec
    for d in domains:
        servers_str = ', '.join(d['servers']) if d['servers'] else '-'
        sec.add(f'{d["base_dn"]}  server-id:{d["server_id"]}  group-id:{d["group_id"]}')
        sec.add(f'  isolation:{d["isolation"]}  window-size:{d["window_size"]}  '
                 f'replication-servers: {servers_str}')
    return sec


# ─────────────────────────────────────────────────────────────────────────────
# ANONYMIZATION  (F3 parity with oud_lb_diagram.py)
# ─────────────────────────────────────────────────────────────────────────────

ANONYMIZE_RANGES = ['198.51.100', '203.0.113', '192.0.2']


def anonymize_domains(domains):
    """
    Replace the host part of every 'host:port' replication-server entry
    with an RFC 5737 documentation-range placeholder, preserving the port.
    Same real host always maps to the same placeholder (stable, deterministic
    — sorted by domain base_dn then server order). Mutates domains in place.
    Returns the number of unique hosts replaced.
    """
    mapping = {}
    next_index = 1

    for d in sorted(domains, key=lambda x: x['base_dn']):
        new_servers = []
        for server in d['servers']:
            host, _, port = server.partition(':')
            if not host:
                new_servers.append(server)
                continue
            if host not in mapping:
                range_idx = (next_index - 1) // 254
                octet     = ((next_index - 1) % 254) + 1
                if range_idx >= len(ANONYMIZE_RANGES):
                    mapping[host] = f'198.51.100.{octet}-overflow{range_idx}'
                else:
                    mapping[host] = f'{ANONYMIZE_RANGES[range_idx]}.{octet}'
                next_index += 1
            new_servers.append(f'{mapping[host]}:{port}' if port else mapping[host])
        d['servers'] = new_servers

    return len(mapping)


def print_report(entries, file=None, anonymize=False):
    backends = extract_backends(entries)
    domains  = extract_replication_domains(entries)

    anonymized_count = 0
    if anonymize:
        anonymized_count = anonymize_domains(domains)

    backends_sec  = build_backends_section(entries, backends)
    indexes_secs  = build_indexes_sections(entries, backends)
    replication_sec = build_replication_section(domains)

    candidates = [backends_sec.content_width(), replication_sec.content_width()]
    candidates += [s.content_width() for s in indexes_secs]
    candidates.append(len(' OUD DIRECTORY SERVER — BACKEND REPORT ') + 2)
    w = max(MIN_W, min(MAX_W, max(candidates) + 4))

    print_header(w, file=file)
    print_section(backends_sec, w, file=file)
    print(file=file)
    for sec in indexes_secs:
        print_section(sec, w, file=file)
        print(file=file)
    print_section(replication_sec, w, file=file)
    print(file=file)

    return backends, domains


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def parse_args(argv):
    args = {'path': None, 'output': None, 'version': False, 'anonymize': False}
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
        elif a == '--anonymize':
            args['anonymize'] = True
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


def main():
    args = parse_args(sys.argv[1:])
    if args['version']:
        print(f'oud_backend_report.py v{__version__}')
        sys.exit(0)

    path = args['path']
    try:
        entries, parse_warnings = parse_ldif(path)
    except FileNotFoundError:
        print(f'[ERROR] File not found: {path}')
        sys.exit(1)

    print(f'\n[+] Parsed {len(entries)} LDIF entries from: {path}')
    for w in parse_warnings:
        print(f'[WARN] {w}')

    # Soft B7-style check, inverted: warn if this looks like a Proxy, not a DS.
    try:
        from oud_config_type import classify_ldif_entries
        primary_type, _sec, confidence, _sig = classify_ldif_entries(entries)
        if not primary_type.startswith('OUD Directory Server'):
            print(f'[WARN] Config does not look like a plain OUD Directory Server '
                  f'(detected: "{primary_type}", confidence: {confidence}). '
                  f'This tool targets Directory Server configs specifically.')
    except ImportError:
        pass

    if args['anonymize']:
        print('[+] --anonymize: replication-server IPs will be replaced with '
              'RFC 5737 documentation-range placeholders')

    if args['output']:
        try:
            with open(args['output'], 'w', encoding='utf-8') as out:
                backends, domains = print_report(entries, file=out, anonymize=args['anonymize'])
            print(f'[+] Report written to: {args["output"]}')
        except OSError as ex:
            print(f'[ERROR] Could not write to {args["output"]}: {ex}')
            sys.exit(1)
    else:
        backends, domains = print_report(entries, anonymize=args['anonymize'])

    print(f'[+] Found: {len(backends)} user-data backend(s), '
          f'{len(domains)} replication domain(s)')


if __name__ == '__main__':
    main()
