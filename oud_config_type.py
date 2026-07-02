#!/usr/bin/env python3
"""
oud_config_type.py
-------------------
Generic classifier for Oracle Unified Directory (OUD) instance configs
(LDIF format). Inspects `ds-cfg-java-class` / objectClass patterns to
determine whether a config belongs to an OUD Proxy, an OUD Directory
Server, a hybrid, or is inconclusive — without assuming which one it is
up front.

This exists so other tools in this repo (oud_lb_diagram.py's B7 early
warning, and the planned oud_config_lint.py) can share one classification
routine instead of re-deriving it. It currently imports the LDIF parser
from oud_lb_diagram.py (both files must sit in the same directory); a
future refactor (see BACKLOG.md item E2) will extract a standalone
oud_ldif_core module so this dependency direction goes away.

Usage:
    python oud_config_type.py <path-to-config.ldif>

Classification is intentionally conservative: it only reports a category
when there is direct evidence for it in the parsed entries, and lists
that evidence so the result can be checked by a human rather than trusted
blindly.
"""

__version__ = "1.0.0"

import sys

try:
    from oud_lb_diagram import parse_ldif, first
except ImportError:
    print('[ERROR] oud_config_type.py must be run from the same directory as oud_lb_diagram.py')
    sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL DETECTION
# ─────────────────────────────────────────────────────────────────────────────

# objectClass fragments for local-backend WE subtypes that are always
# OUD-internal/system backends, regardless of the is-private-backend flag
# (schema, tasks, monitor, backup, trust store, LDIF admin backend).
SYSTEM_BACKEND_OC_FRAGMENTS = (
    'ds-cfg-ldif-local-backend-workflow-element',
    'ds-cfg-trust-store-local-backend-workflow-element',
    'ds-cfg-backup-local-backend-workflow-element',
    'ds-cfg-monitor-local-backend-workflow-element',
    'ds-cfg-schema-local-backend-workflow-element',
    'ds-cfg-task-local-backend-workflow-element',
)
# The DB-backed local backend (ds-cfg-db-local-backend-workflow-element) is
# the only subtype that can hold real user data — but OUD also uses it
# internally (e.g. virtualAcis), so it only counts as "user data" when
# ds-cfg-is-private-backend is NOT true.
DB_BACKEND_OC_FRAGMENT = 'ds-cfg-db-local-backend-workflow-element'


def collect_signals(entries):
    """
    Scan all entries once and collect evidence for each candidate category.
    Returns a dict of signal_name -> list of DNs that triggered it.
    """
    signals = {
        'proxy_lb':        [],  # LoadBalancingWorkflowElement / ProxyLdapWorkflowElement
        'local_data_backend': [],  # non-private DB local backend WE (real user data)
        'local_private_backend': [],  # private/system local backend WE (admin, schema, tasks...)
        'global_index':    [],  # com.sun.dps.server.globalindex.*
        'replication':     [],  # replication domain(s) configured
    }

    for dn, e in entries.items():
        jc = first(e, 'ds-cfg-java-class')
        oc = ' '.join(e.get('objectclass', [])).lower()

        if 'LoadBalancingWorkflowElement' in jc or 'ProxyLdapWorkflowElement' in jc:
            signals['proxy_lb'].append(dn)

        if 'globalindex' in jc.lower():
            signals['global_index'].append(dn)

        if any(frag in oc for frag in SYSTEM_BACKEND_OC_FRAGMENTS):
            signals['local_private_backend'].append(dn)
        elif DB_BACKEND_OC_FRAGMENT in oc:
            is_private = first(e, 'ds-cfg-is-private-backend', 'false').lower() == 'true'
            if is_private:
                signals['local_private_backend'].append(dn)
            else:
                signals['local_data_backend'].append(dn)

    # replication domains: entries nested under cn=domains,cn=Multimaster Synchronization,...
    for dn in entries:
        if ',cn=domains,cn=multimaster synchronization,' in dn and dn != 'cn=domains,cn=multimaster synchronization,cn=synchronization providers,cn=config':
            signals['replication'].append(dn)

    return signals


# ─────────────────────────────────────────────────────────────────────────────
# CLASSIFICATION
# ─────────────────────────────────────────────────────────────────────────────

def classify(signals):
    """
    Decide a primary type from collected signals. Returns
    (primary_type: str, secondary_features: list[str], confidence: str).
    """
    has_proxy = bool(signals['proxy_lb'])
    has_data_backend = bool(signals['local_data_backend'])
    has_global_index = bool(signals['global_index'])

    secondary = []
    if signals['replication']:
        secondary.append(f'Replication configured ({len(signals["replication"])} domain(s))')
    if has_global_index:
        secondary.append(f'Global Index Catalog components present ({len(signals["global_index"])} entries)')

    if has_proxy and not has_data_backend:
        return 'OUD Proxy', secondary, 'high'
    if has_data_backend and not has_proxy:
        return 'OUD Directory Server', secondary, 'high'
    if has_proxy and has_data_backend:
        return 'Hybrid / unusual (both proxy-LB and local data backend detected)', secondary, 'medium'
    if has_global_index and not has_proxy and not has_data_backend:
        return 'OUD Proxy — Global Index Catalog only (no LB workflow elements found)', secondary, 'medium'

    return 'Unknown / inconclusive (no proxy, data backend, or global index signals found)', secondary, 'low'


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API  (for reuse by oud_lb_diagram.py and future tools)
# ─────────────────────────────────────────────────────────────────────────────

def classify_ldif_entries(entries):
    """
    One-call convenience wrapper: entries -> (primary_type, secondary_features, confidence, signals).
    This is the function other tools should import and call.
    """
    signals = collect_signals(entries)
    primary, secondary, confidence = classify(signals)
    return primary, secondary, confidence, signals


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) > 1 and sys.argv[1] in ('--version', '-v'):
        print(f'oud_config_type.py v{__version__}')
        sys.exit(0)

    path = sys.argv[1] if len(sys.argv) > 1 else 'config.ldif'
    try:
        entries, parse_warnings = parse_ldif(path)
    except FileNotFoundError:
        print(f'[ERROR] File not found: {path}')
        print('Usage: python oud_config_type.py <path-to-config.ldif>')
        sys.exit(1)

    print(f'\n[+] Parsed {len(entries)} LDIF entries from: {path}')
    for w in parse_warnings:
        print(f'[WARN] {w}')

    primary, secondary, confidence, signals = classify_ldif_entries(entries)

    print(f'\n[+] Detected type: {primary}  (confidence: {confidence})')
    if secondary:
        print('[+] Additional features:')
        for f in secondary:
            print(f'    - {f}')

    print('\n[+] Evidence:')
    labels = {
        'proxy_lb':              'Proxy / load-balancing workflow elements',
        'local_data_backend':    'Local data backend (non-private) workflow elements',
        'local_private_backend': 'Local private/system backend workflow elements',
        'global_index':          'Global Index Catalog components',
        'replication':           'Replication domain entries',
    }
    for key, dns in signals.items():
        label = labels[key]
        if dns:
            print(f'    {label}: {len(dns)} found')
            for d in dns[:3]:
                print(f'      - {d}')
            if len(dns) > 3:
                print(f'      ... and {len(dns) - 3} more')
        else:
            print(f'    {label}: none found')


if __name__ == '__main__':
    main()
