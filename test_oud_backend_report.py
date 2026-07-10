#!/usr/bin/env python3
"""
test_oud_backend_report.py
----------------------------
Basic unit tests for oud_backend_report.py (E3).
"""

import unittest
import tempfile
import os

from oud_ldif_core import parse_ldif
from oud_backend_report import (
    extract_backends, extract_indexes, extract_replication_domains,
    anonymize_domains,
)


def write_ldif(text):
    fd, path = tempfile.mkstemp(suffix='.ldif')
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(text)
    return path


MINI_DS_CONFIG = """\
dn: cn=userRoot,cn=Workflow Elements,cn=config
objectClass: ds-cfg-local-backend-workflow-element
objectClass: ds-cfg-workflow-element
objectClass: ds-cfg-db-local-backend-workflow-element
objectClass: top
ds-cfg-base-dn: dc=example,dc=com
ds-cfg-enabled: true
ds-cfg-writability-mode: enabled
ds-cfg-db-directory: db
ds-cfg-db-txn-durability: write-to-filesystem
ds-cfg-index-entry-limit: 4000
cn: userRoot

dn: cn=Index,cn=userRoot,cn=Workflow Elements,cn=config
objectClass: top
objectClass: ds-cfg-branch
cn: Index

dn: ds-cfg-attribute=uid,cn=Index,cn=userRoot,cn=Workflow Elements,cn=config
objectClass: top
objectClass: ds-cfg-local-db-index
ds-cfg-attribute: uid
ds-cfg-index-type: equality
ds-cfg-index-type: presence
ds-cfg-index-entry-limit: 5000

dn: cn=adminRoot,cn=Workflow Elements,cn=config
objectClass: ds-cfg-local-backend-workflow-element
objectClass: ds-cfg-workflow-element
objectClass: ds-cfg-ldif-local-backend-workflow-element
objectClass: top
ds-cfg-base-dn: cn=admin data
ds-cfg-is-private-backend: true
cn: adminRoot

dn: cn=dc=example\\,dc=com,cn=domains,cn=Multimaster Synchronization,cn=Synchronization Providers,cn=config
objectClass: ds-cfg-replication-domain
objectClass: top
ds-cfg-base-dn: dc=example,dc=com
ds-cfg-server-id: 1001
ds-cfg-group-id: 1
ds-cfg-replication-server: 10.0.0.1:8989
ds-cfg-replication-server: 10.0.0.2:8989
ds-cfg-isolation-policy: reject-all-updates
cn: dc=example,dc=com
"""


class TestExtractBackends(unittest.TestCase):
    def setUp(self):
        self.path = write_ldif(MINI_DS_CONFIG)
        self.entries, _ = parse_ldif(self.path)

    def tearDown(self):
        os.remove(self.path)

    def test_finds_one_user_data_backend(self):
        backends = extract_backends(self.entries)
        self.assertEqual(len(backends), 1)
        b = list(backends.values())[0]
        self.assertEqual(b['cn'], 'userRoot')
        self.assertEqual(b['base_dn'], 'dc=example,dc=com')

    def test_excludes_system_backend(self):
        backends = extract_backends(self.entries)
        cns = [b['cn'] for b in backends.values()]
        self.assertNotIn('adminRoot', cns)


class TestExtractIndexes(unittest.TestCase):
    def setUp(self):
        self.path = write_ldif(MINI_DS_CONFIG)
        self.entries, _ = parse_ldif(self.path)
        self.backends = extract_backends(self.entries)
        self.backend_dn = list(self.backends.keys())[0]

    def tearDown(self):
        os.remove(self.path)

    def test_finds_index(self):
        indexes = extract_indexes(self.entries, self.backend_dn, 'userRoot')
        self.assertEqual(len(indexes), 1)
        self.assertEqual(indexes[0]['attribute'], 'uid')
        self.assertIn('equality', indexes[0]['types'])
        self.assertEqual(indexes[0]['entry_limit'], '5000')


class TestExtractReplicationDomains(unittest.TestCase):
    def setUp(self):
        self.path = write_ldif(MINI_DS_CONFIG)
        self.entries, _ = parse_ldif(self.path)

    def tearDown(self):
        os.remove(self.path)

    def test_finds_one_domain(self):
        domains = extract_replication_domains(self.entries)
        self.assertEqual(len(domains), 1)
        d = domains[0]
        self.assertEqual(d['base_dn'], 'dc=example,dc=com')
        self.assertEqual(d['server_id'], '1001')
        self.assertEqual(len(d['servers']), 2)


class TestAnonymizeDomains(unittest.TestCase):
    def setUp(self):
        self.path = write_ldif(MINI_DS_CONFIG)
        self.entries, _ = parse_ldif(self.path)
        self.domains = extract_replication_domains(self.entries)

    def tearDown(self):
        os.remove(self.path)

    def test_replaces_host_preserves_port(self):
        count = anonymize_domains(self.domains)
        self.assertEqual(count, 2)  # 10.0.0.1 and 10.0.0.2
        servers = self.domains[0]['servers']
        for s in servers:
            host, _, port = s.partition(':')
            self.assertTrue(host.startswith('198.51.100.') or host.startswith('203.0.113.'))
            self.assertEqual(port, '8989')

    def test_same_host_maps_to_same_placeholder(self):
        dup_config = MINI_DS_CONFIG + """
dn: cn=dc=other\\,dc=com,cn=domains,cn=Multimaster Synchronization,cn=Synchronization Providers,cn=config
objectClass: ds-cfg-replication-domain
objectClass: top
ds-cfg-base-dn: dc=other,dc=com
ds-cfg-server-id: 1002
ds-cfg-group-id: 1
ds-cfg-replication-server: 10.0.0.1:8989
cn: dc=other,dc=com
"""
        path = write_ldif(dup_config)
        try:
            entries, _ = parse_ldif(path)
            domains = extract_replication_domains(entries)
            anonymize_domains(domains)
            first_host = domains[0]['servers'][0].split(':')[0]
            second_domain_host = [d for d in domains if d['base_dn'] == 'dc=other,dc=com'][0]['servers'][0].split(':')[0]
            self.assertEqual(first_host, second_domain_host)
        finally:
            os.remove(path)


if __name__ == '__main__':
    unittest.main(verbosity=2)
