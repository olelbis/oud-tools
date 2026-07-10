#!/usr/bin/env python3
"""
test_oud_config_lint.py
--------------------------
Basic unit tests for oud_config_lint.py (P3).
"""

import unittest
import tempfile
import os

from oud_ldif_core import parse_ldif
from oud_lb_diagram import extract_model
from oud_config_lint import lint_proxy, lint_ds, SEV_ERROR, SEV_WARNING, SEV_INFO


def write_ldif(text):
    fd, path = tempfile.mkstemp(suffix='.ldif')
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(text)
    return path


MINI_PROXY_CONFIG = """\
dn: cn=network-group,cn=Network Groups,cn=config
objectClass: ds-cfg-network-group
objectClass: top
ds-cfg-enabled: true
ds-cfg-priority: 1
ds-cfg-workflow: cn=wf1,cn=Workflows,cn=config
cn: network-group

dn: cn=wf1,cn=Workflows,cn=config
objectClass: ds-cfg-workflow
objectClass: top
ds-cfg-workflow-element: cn=LB1,cn=Workflow elements,cn=config
cn: wf1
ds-cfg-base-dn: dc=example,dc=com

dn: cn=ext1,cn=Extensions,cn=config
objectClass: ds-cfg-extension
objectClass: top
objectClass: ds-cfg-ldap-server-extension
ds-cfg-java-class: com.sun.dps.server.workflowelement.proxyldap.LDAPServerExtension
ds-cfg-remote-ldap-server-address: 10.0.0.1
ds-cfg-pool-max-size: 0
ds-cfg-ssl-trust-all: true
ds-cfg-remote-ldap-server-ssl-policy: never
cn: ext1

dn: cn=proxy-we1,cn=Workflow elements,cn=config
objectClass: ds-cfg-workflow-element
objectClass: top
objectClass: ds-cfg-proxy-ldap-workflow-element
ds-cfg-java-class: com.sun.dps.server.workflowelement.proxyldap.ProxyLdapWorkflowElement
ds-cfg-ldap-server-extension: cn=ext1,cn=Extensions,cn=config
cn: proxy-we1

dn: cn=LB1,cn=Workflow elements,cn=config
objectClass: ds-cfg-load-balancing-workflow-element
objectClass: ds-cfg-workflow-element
objectClass: top
ds-cfg-java-class: com.sun.dps.server.workflowelement.loadbalancing.LoadBalancingWorkflowElement
ds-cfg-enabled: true
cn: LB1

dn: cn=algorithm,cn=LB1,cn=Workflow elements,cn=config
objectClass: top
objectClass: ds-cfg-failover-load-balancing-algorithm
objectClass: ds-cfg-load-balancing-algorithm
ds-cfg-java-class: com.sun.dps.server.workflowelement.loadbalancing.FailoverLoadBalancingAlgorithm
cn: algorithm

dn: cn=routes,cn=algorithm,cn=LB1,cn=Workflow elements,cn=config
objectClass: top
objectClass: ds-cfg-branch
cn: routes

dn: cn=route1,cn=routes,cn=algorithm,cn=LB1,cn=Workflow elements,cn=config
objectClass: top
objectClass: ds-cfg-failover-load-balancing-route
objectClass: ds-cfg-load-balancing-route
ds-cfg-workflow-element: cn=proxy-we1,cn=Workflow elements,cn=config
ds-cfg-search-priority: 1
cn: route1
"""


class TestLintProxy(unittest.TestCase):
    def setUp(self):
        self.path = write_ldif(MINI_PROXY_CONFIG)
        self.entries, _ = parse_ldif(self.path)
        self.model = extract_model(self.entries)

    def tearDown(self):
        os.remove(self.path)

    def test_detects_ssl_trust_all(self):
        findings = lint_proxy(self.entries, self.model)
        rule_ids = [f.rule_id for f in findings]
        self.assertIn('P-SEC-1', rule_ids)

    def test_detects_weak_ssl_policy(self):
        findings = lint_proxy(self.entries, self.model)
        rule_ids = [f.rule_id for f in findings]
        self.assertIn('P-SEC-2', rule_ids)

    def test_detects_zero_pool_size(self):
        findings = lint_proxy(self.entries, self.model)
        rule_ids = [f.rule_id for f in findings]
        self.assertIn('P-PERF-1', rule_ids)

    def test_no_orphan_in_reachable_config(self):
        findings = lint_proxy(self.entries, self.model)
        rule_ids = [f.rule_id for f in findings]
        self.assertNotIn('P-ARCH-1', rule_ids)  # everything here is reachable

    def test_broken_reference_detected(self):
        broken = MINI_PROXY_CONFIG.replace(
            'ds-cfg-workflow-element: cn=proxy-we1,cn=Workflow elements,cn=config\nds-cfg-search-priority: 1',
            'ds-cfg-workflow-element: cn=proxy-we-GHOST,cn=Workflow elements,cn=config\nds-cfg-search-priority: 1'
        )
        path = write_ldif(broken)
        try:
            entries, _ = parse_ldif(path)
            model = extract_model(entries)
            findings = lint_proxy(entries, model)
            rule_ids = [f.rule_id for f in findings]
            self.assertIn('P-REF-1', rule_ids)
            severities = {f.rule_id: f.severity for f in findings}
            self.assertEqual(severities['P-REF-1'], SEV_ERROR)
        finally:
            os.remove(path)


MINI_DS_CONFIG = """\
dn: cn=userRoot,cn=Workflow Elements,cn=config
objectClass: ds-cfg-local-backend-workflow-element
objectClass: ds-cfg-workflow-element
objectClass: ds-cfg-db-local-backend-workflow-element
objectClass: top
ds-cfg-base-dn: dc=example,dc=com
ds-cfg-enabled: true
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

dn: cn=dc=example\\,dc=com,cn=domains,cn=Multimaster Synchronization,cn=Synchronization Providers,cn=config
objectClass: ds-cfg-replication-domain
objectClass: top
ds-cfg-base-dn: dc=example,dc=com
ds-cfg-server-id: 1001
cn: dc=example,dc=com

dn: cn=cn=schema,cn=domains,cn=Multimaster Synchronization,cn=Synchronization Providers,cn=config
objectClass: ds-cfg-replication-domain
objectClass: top
ds-cfg-base-dn: cn=schema
ds-cfg-server-id: 1001
cn: cn=schema
"""


class TestLintDS(unittest.TestCase):
    def setUp(self):
        self.path = write_ldif(MINI_DS_CONFIG)
        self.entries, _ = parse_ldif(self.path)

    def tearDown(self):
        os.remove(self.path)

    def test_detects_missing_mail_index(self):
        findings = lint_ds(self.entries)
        msgs = [f.message for f in findings if f.rule_id == 'D-PERF-1']
        self.assertTrue(any('mail' in m for m in msgs))

    def test_no_missing_uid_index(self):
        findings = lint_ds(self.entries)
        msgs = [f.message for f in findings if f.rule_id == 'D-PERF-1']
        self.assertFalse(any('"uid"' in m for m in msgs))

    def test_detects_duplicate_server_id(self):
        findings = lint_ds(self.entries)
        rule_ids = [f.rule_id for f in findings]
        self.assertIn('D-HYG-1', rule_ids)


if __name__ == '__main__':
    unittest.main(verbosity=2)
