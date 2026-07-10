#!/usr/bin/env python3
"""
oud_config_lint.py
--------------------
Validator/linter for Oracle Unified Directory (OUD) configs — both Proxy
and Directory Server. Runs a set of rule-based checks and prints a
findings report grouped by severity.

Built on the shared oud_ldif_core.py parser and reuses the object models
already built by oud_lb_diagram.py (proxy) and oud_backend_report.py (DS).
Uses oud_config_type.py to decide which rule set(s) to run. All four files
must sit in the same directory.

Usage:
    python oud_config_lint.py <path-to-config.ldif>
    python oud_config_lint.py --version
    python oud_config_lint.py <config> --output <file>
    python oud_config_lint.py <config> --format json

Exit code: 1 if any ERROR-severity finding is present, 0 otherwise
(0 findings or only WARNING/INFO) — suitable for CI use.

Scope (v1.0.0):
  Proxy rules   — broken references, orphaned/unreachable workflow
                  elements, disabled-but-referenced components, weak SSL
                  settings, missing/zero connection pool or timeouts,
                  duplicate CNs, network groups with no workflow.
  DS rules      — replication domains with no matching local backend (and
                  vice versa), duplicate replication server-id across
                  domains, commonly-queried attributes (uid/mail) with no
                  index at all (suggestion only, since actual query
                  patterns aren't visible from config alone).
"""

__version__ = "1.0.0"

import sys
import json

try:
    from oud_ldif_core import parse_ldif, first, cn_of
except ImportError:
    print('[ERROR] oud_config_lint.py requires oud_ldif_core.py in the same directory.')
    sys.exit(1)

try:
    from oud_config_type import classify_ldif_entries
except ImportError:
    classify_ldif_entries = None

try:
    from oud_lb_diagram import extract_model, find_duplicate_cn_warnings
except ImportError:
    extract_model = None
    find_duplicate_cn_warnings = None

try:
    from oud_backend_report import extract_backends, extract_replication_domains
except ImportError:
    extract_backends = None
    extract_replication_domains = None


# ─────────────────────────────────────────────────────────────────────────────
# FINDING MODEL
# ─────────────────────────────────────────────────────────────────────────────

SEV_ERROR   = 'ERROR'
SEV_WARNING = 'WARNING'
SEV_INFO    = 'INFO'
SEV_ORDER   = {SEV_ERROR: 0, SEV_WARNING: 1, SEV_INFO: 2}


class Finding:
    def __init__(self, rule_id, severity, category, message, ref=None):
        self.rule_id  = rule_id
        self.severity = severity
        self.category = category
        self.message   = message
        self.ref       = ref  # optional DN or identifier for context

    def to_dict(self):
        return {
            'rule_id': self.rule_id, 'severity': self.severity,
            'category': self.category, 'message': self.message, 'ref': self.ref,
        }


# ─────────────────────────────────────────────────────────────────────────────
# PROXY RULES
# ─────────────────────────────────────────────────────────────────────────────

def lint_proxy(entries, model):
    findings = []
    all_we = set(model['lb_we']) | set(model['proxy_we'])

    # P-REF-1: broken references
    for ng in model['network_groups']:
        wf_dn = ng['workflow_dn']
        if not wf_dn:
            findings.append(Finding('P-HYG-2', SEV_WARNING, 'hygiene',
                f'network-group "{ng["cn"]}" has no workflow configured', ng['cn']))
        elif wf_dn not in model['workflows']:
            findings.append(Finding('P-REF-1', SEV_ERROR, 'references',
                f'network-group "{ng["cn"]}" references unknown workflow: {wf_dn}', ng['cn']))
    for wf_dn, wf in model['workflows'].items():
        if wf['entry_we_dn'] and wf['entry_we_dn'] not in all_we:
            findings.append(Finding('P-REF-1', SEV_ERROR, 'references',
                f'workflow "{wf["cn"]}" references unknown WE: {wf["entry_we_dn"]}', wf['cn']))
    for lb_dn, lb in model['lb_we'].items():
        for r in lb['routes']:
            if r['we_dn'] and r['we_dn'] not in all_we:
                findings.append(Finding('P-REF-1', SEV_ERROR, 'references',
                    f'route "{r["cn"]}" in "{lb["cn"]}" references unknown WE: {r["we_dn"]}', lb['cn']))
    for pwe_dn, pwe in model['proxy_we'].items():
        if pwe['extension_dn'] and pwe['extension_dn'] not in model['extensions']:
            findings.append(Finding('P-REF-1', SEV_ERROR, 'references',
                f'proxy-we "{pwe["cn"]}" references unknown extension: {pwe["extension_dn"]}', pwe['cn']))

    # P-ARCH-1: orphaned WEs (unreachable from any network-group's workflow tree)
    reachable = set()
    def visit(we_dn):
        if we_dn in reachable or we_dn not in all_we:
            return
        reachable.add(we_dn)
        if we_dn in model['lb_we']:
            for r in model['lb_we'][we_dn]['routes']:
                visit(r['we_dn'])
    for ng in model['network_groups']:
        wf = model['workflows'].get(ng['workflow_dn'])
        if wf and wf['entry_we_dn']:
            visit(wf['entry_we_dn'])
    for we_dn in all_we - reachable:
        cn = model['lb_we'].get(we_dn, model['proxy_we'].get(we_dn, {})).get('cn', we_dn)
        findings.append(Finding('P-ARCH-1', SEV_WARNING, 'architecture',
            f'workflow element "{cn}" is not reachable from any network group', cn))

    # P-ARCH-2: disabled-but-still-referenced components
    for pwe_dn, pwe in model['proxy_we'].items():
        if pwe_dn not in reachable:
            continue
        ext = model['extensions'].get(pwe['extension_dn'], {})
        if pwe.get('enabled', 'true').lower() == 'false' or ext.get('enabled', 'true').lower() == 'false':
            findings.append(Finding('P-ARCH-2', SEV_WARNING, 'architecture',
                f'proxy-we "{pwe["cn"]}" is disabled (or its extension is) but still reachable/referenced',
                pwe['cn']))

    # P-SEC-1 / P-SEC-2: SSL settings
    for ext_dn, ext in model['extensions'].items():
        if ext.get('ssl_trust_all', 'false').lower() == 'true':
            findings.append(Finding('P-SEC-1', SEV_WARNING, 'security',
                f'extension "{ext["cn"]}" has ssl-trust-all: true — backend certificate is not validated',
                ext['cn']))
        if ext.get('ssl_policy', '-') not in ('always',):
            findings.append(Finding('P-SEC-2', SEV_INFO, 'security',
                f'extension "{ext["cn"]}" ssl-policy is "{ext.get("ssl_policy","-")}" '
                f'(not "always") — backend connection may be unencrypted', ext['cn']))

    # P-PERF-1 / P-PERF-2: pool size and timeouts
    for ext_dn, ext in model['extensions'].items():
        pool = ext.get('pool_max', '-')
        if pool in ('-', '0') or (pool.isdigit() and int(pool) <= 0):
            findings.append(Finding('P-PERF-1', SEV_WARNING, 'performance',
                f'extension "{ext["cn"]}" has no usable connection pool size configured '
                f'(pool-max-size={pool})', ext['cn']))
        for label, key in (('connect', 'conn_timeout'), ('read', 'read_timeout')):
            val = ext.get(key, '-')
            if val == '0':
                findings.append(Finding('P-PERF-2', SEV_INFO, 'performance',
                    f'extension "{ext["cn"]}" has {label}-timeout set to 0 (no timeout — '
                    f'a hung backend connection could block indefinitely)', ext['cn']))

    # P-HYG-1: duplicate CNs
    if find_duplicate_cn_warnings:
        for w in find_duplicate_cn_warnings(model):
            findings.append(Finding('P-HYG-1', SEV_INFO, 'hygiene', w))

    return findings


# ─────────────────────────────────────────────────────────────────────────────
# DIRECTORY SERVER RULES
# ─────────────────────────────────────────────────────────────────────────────

COMMONLY_QUERIED_ATTRS = ('uid', 'mail')


def lint_ds(entries):
    findings = []
    backends = extract_backends(entries)
    domains  = extract_replication_domains(entries)

    backend_base_dns = {b['base_dn'].lower() for b in backends.values() if b['base_dn']}
    domain_base_dns  = {d['base_dn'].lower() for d in domains if d['base_dn']}

    # D-ARCH-1 / D-ARCH-2: backend <-> replication domain cross-check
    for base_dn in domain_base_dns - backend_base_dns:
        # skip well-known non-data suffixes that legitimately have their own
        # replication domain without a "local data backend" of the same name
        if base_dn in ('cn=admin data', 'cn=schema'):
            continue
        findings.append(Finding('D-ARCH-2', SEV_WARNING, 'architecture',
            f'replication domain for base-dn "{base_dn}" has no matching local backend '
            f'in this config — dangling domain or backend defined elsewhere?', base_dn))
    for base_dn in backend_base_dns - domain_base_dns:
        findings.append(Finding('D-ARCH-1', SEV_INFO, 'architecture',
            f'backend with base-dn "{base_dn}" has no replication domain configured '
            f'(standalone instance, or replication intentionally not enabled?)', base_dn))

    # D-HYG-1: duplicate server-id across replication domains
    seen_ids = {}
    for d in domains:
        sid = d['server_id']
        if sid == '-':
            continue
        if sid in seen_ids:
            findings.append(Finding('D-HYG-1', SEV_WARNING, 'hygiene',
                f'replication domains "{seen_ids[sid]}" and "{d["base_dn"]}" share the same '
                f'server-id ({sid}) — likely a copy-paste misconfiguration', sid))
        else:
            seen_ids[sid] = d['base_dn']

    # D-PERF-1: commonly-queried attributes with no index at all (soft suggestion)
    for dn, b in backends.items():
        indexed_attrs = set()
        index_parent = f'cn=index,{dn}'
        for idn, e in entries.items():
            if idn == index_parent or idn.endswith(',' + index_parent):
                attr = first(e, 'ds-cfg-attribute')
                if attr:
                    indexed_attrs.add(attr.lower())
        for attr in COMMONLY_QUERIED_ATTRS:
            if attr not in indexed_attrs:
                findings.append(Finding('D-PERF-1', SEV_INFO, 'performance',
                    f'backend "{b["cn"]}" has no index at all on "{attr}" — if this attribute '
                    f'is used in search filters or binds, consider adding one '
                    f'(this is a suggestion, not a confirmed usage pattern)', b['cn']))

    return findings


# ─────────────────────────────────────────────────────────────────────────────
# REPORT
# ─────────────────────────────────────────────────────────────────────────────

def print_report(findings, profile, confidence, file=None):
    print(f'\n[+] Detected profile: {profile}  (confidence: {confidence})', file=file)
    if not findings:
        print('[+] No findings. Clean bill of health for the checks in this version.', file=file)
        return

    by_sev = {SEV_ERROR: [], SEV_WARNING: [], SEV_INFO: []}
    for f in findings:
        by_sev[f.severity].append(f)

    for sev in (SEV_ERROR, SEV_WARNING, SEV_INFO):
        items = by_sev[sev]
        if not items:
            continue
        print(f'\n{sev} ({len(items)})', file=file)
        print('-' * 60, file=file)
        for f in items:
            print(f'  [{f.rule_id}] {f.message}', file=file)

    print(f'\n[+] Total: {len(findings)} finding(s)  '
          f'({len(by_sev[SEV_ERROR])} error, {len(by_sev[SEV_WARNING])} warning, '
          f'{len(by_sev[SEV_INFO])} info)', file=file)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def parse_args(argv):
    args = {'path': None, 'output': None, 'version': False, 'format': 'text'}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ('--version', '-v'):
            args['version'] = True
        elif a == '--output':
            i += 1
            if i >= len(argv):
                print('[ERROR] --output requires a file path'); sys.exit(1)
            args['output'] = argv[i]
        elif a == '--format':
            i += 1
            if i >= len(argv) or argv[i] not in ('text', 'json'):
                print('[ERROR] --format requires "text" or "json"'); sys.exit(1)
            args['format'] = argv[i]
        elif a.startswith('--'):
            print(f'[ERROR] Unknown option: {a}'); sys.exit(1)
        elif args['path'] is None:
            args['path'] = a
        else:
            print(f'[ERROR] Unexpected argument: {a}'); sys.exit(1)
        i += 1
    if args['path'] is None:
        args['path'] = 'config.ldif'
    return args


def main():
    args = parse_args(sys.argv[1:])
    if args['version']:
        print(f'oud_config_lint.py v{__version__}')
        sys.exit(0)

    diag = sys.stderr if args['format'] == 'json' else sys.stdout

    path = args['path']
    try:
        entries, parse_warnings = parse_ldif(path)
    except FileNotFoundError:
        print(f'[ERROR] File not found: {path}')
        sys.exit(1)

    print(f'\n[+] Parsed {len(entries)} LDIF entries from: {path}', file=diag)
    for w in parse_warnings:
        print(f'[WARN] {w}', file=diag)

    if classify_ldif_entries:
        profile, _secondary, confidence, _signals = classify_ldif_entries(entries)
    else:
        profile, confidence = 'Unknown (oud_config_type.py not available)', 'low'

    findings = []
    if profile.startswith('OUD Proxy') or profile.startswith('Hybrid'):
        if extract_model:
            findings += lint_proxy(entries, extract_model(entries))
        else:
            print('[WARN] oud_lb_diagram.py not available — proxy rules skipped', file=diag)
    if profile.startswith('OUD Directory Server') or profile.startswith('Hybrid'):
        if extract_backends:
            findings += lint_ds(entries)
        else:
            print('[WARN] oud_backend_report.py not available — DS rules skipped', file=diag)
    if profile.startswith('Unknown'):
        print('[WARN] Could not determine config profile — no rules were run. '
              'Run oud_config_type.py for details.', file=diag)

    has_error = any(f.severity == SEV_ERROR for f in findings)

    if args['format'] == 'json':
        payload = {
            'tool': 'oud_config_lint.py', 'tool_version': __version__,
            'source_file': path, 'profile': profile, 'confidence': confidence,
            'findings': [f.to_dict() for f in findings],
        }
        text = json.dumps(payload, indent=2, ensure_ascii=False)
        if args['output']:
            with open(args['output'], 'w', encoding='utf-8') as out:
                out.write(text + '\n')
            print(f'[+] JSON written to: {args["output"]}', file=diag)
        else:
            print(text)
    else:
        if args['output']:
            with open(args['output'], 'w', encoding='utf-8') as out:
                print_report(findings, profile, confidence, file=out)
            print(f'[+] Report written to: {args["output"]}', file=diag)
        else:
            print_report(findings, profile, confidence)

    sys.exit(1 if has_error else 0)


if __name__ == '__main__':
    main()
