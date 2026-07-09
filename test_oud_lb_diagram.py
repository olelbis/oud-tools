#!/usr/bin/env python3
"""
test_oud_lb_diagram.py
-----------------------
Basic unit tests for oud_lb_diagram.py (C3).

Covers:
  - LDIF parsing: basic entries, RFC 4511 line folding, base64 decoding,
    comments, blank-line entry separation, DN/attribute case normalisation
  - Small utility functions: first(), cn_of(), classifiers, algo_type()
  - Formatters: fmt_weights(), fmt_priorities()
  - Model extraction: each _extract_* function in isolation, plus a full
    extract_model() integration test against a small synthetic config
  - find_duplicate_cn_warnings() (B5)

Run with:
    python3 -m unittest test_oud_lb_diagram.py -v
or simply:
    python3 test_oud_lb_diagram.py
"""

import unittest
import tempfile
import os

from oud_lb_diagram import (
    parse_ldif, first, cn_of,
    is_lb_we, is_proxy_we, is_extension, algo_type,
    fmt_weights, fmt_priorities,
    _extract_extensions, _extract_proxy_we, _extract_workflows,
    _extract_network_groups, _extract_lb_we,
    extract_model,
    find_duplicate_cn_warnings,
    anonymize_model,
    disabled_marker,
)


def write_ldif(text):
    """Write `text` to a temp file and return its path. Caller must delete it."""
    fd, path = tempfile.mkstemp(suffix='.ldif')
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(text)
    return path


class TestParseLdifBasics(unittest.TestCase):
    def setUp(self):
        self.path = write_ldif(
            "dn: cn=foo,cn=config\n"
            "objectClass: top\n"
            "cn: foo\n"
            "ds-cfg-enabled: true\n"
            "\n"
            "dn: cn=bar,cn=config\n"
            "objectClass: top\n"
            "cn: bar\n"
        )

    def tearDown(self):
        os.remove(self.path)

    def test_two_entries_parsed(self):
        entries, warnings = parse_ldif(self.path)
        self.assertEqual(len(entries), 2)
        self.assertEqual(warnings, [])

    def test_dn_keys_are_lowercase(self):
        entries, _ = parse_ldif(self.path)
        self.assertIn('cn=foo,cn=config', entries)
        self.assertIn('cn=bar,cn=config', entries)

    def test_attribute_values_preserved(self):
        entries, _ = parse_ldif(self.path)
        self.assertEqual(first(entries['cn=foo,cn=config'], 'cn'), 'foo')
        self.assertEqual(first(entries['cn=foo,cn=config'], 'ds-cfg-enabled'), 'true')

    def test_missing_attribute_returns_default(self):
        entries, _ = parse_ldif(self.path)
        self.assertEqual(first(entries['cn=bar,cn=config'], 'nope', 'fallback'), 'fallback')


class TestParseLdifLineFolding(unittest.TestCase):
    def test_continuation_line_is_joined(self):
        path = write_ldif(
            "dn: cn=foo,cn=config\n"
            "description: this is a long value that\n"
            " continues on the next line\n"
        )
        try:
            entries, _ = parse_ldif(path)
            self.assertEqual(
                first(entries['cn=foo,cn=config'], 'description'),
                'this is a long value thatcontinues on the next line'
            )
        finally:
            os.remove(path)


class TestParseLdifBase64(unittest.TestCase):
    def test_base64_value_decoded(self):
        import base64
        encoded = base64.b64encode(b'hello world').decode('ascii')
        path = write_ldif(f"dn: cn=foo,cn=config\ndescription:: {encoded}\n")
        try:
            entries, _ = parse_ldif(path)
            self.assertEqual(first(entries['cn=foo,cn=config'], 'description'), 'hello world')
        finally:
            os.remove(path)


class TestParseLdifCommentsAndBlankLines(unittest.TestCase):
    def test_comment_lines_ignored(self):
        path = write_ldif(
            "# this is a comment\n"
            "dn: cn=foo,cn=config\n"
            "# another comment\n"
            "cn: foo\n"
        )
        try:
            entries, _ = parse_ldif(path)
            self.assertEqual(len(entries), 1)
            self.assertEqual(first(entries['cn=foo,cn=config'], 'cn'), 'foo')
        finally:
            os.remove(path)


class TestCnOf(unittest.TestCase):
    def test_extracts_first_cn_component(self):
        self.assertEqual(cn_of('cn=foo,cn=bar,cn=config'), 'foo')

    def test_returns_dn_if_no_cn(self):
        self.assertEqual(cn_of('ou=people,dc=example,dc=com'), 'ou=people,dc=example,dc=com')


class TestClassifiers(unittest.TestCase):
    def test_is_lb_we(self):
        entry = {'ds-cfg-java-class': ['com.sun.dps.server.workflowelement.loadbalancing.LoadBalancingWorkflowElement']}
        self.assertTrue(is_lb_we(entry))
        self.assertFalse(is_proxy_we(entry))

    def test_is_proxy_we(self):
        entry = {'ds-cfg-java-class': ['com.sun.dps.server.workflowelement.proxyldap.ProxyLdapWorkflowElement']}
        self.assertTrue(is_proxy_we(entry))
        self.assertFalse(is_lb_we(entry))

    def test_is_extension(self):
        entry = {'ds-cfg-java-class': ['com.sun.dps.server.workflowelement.proxyldap.LDAPServerExtension']}
        self.assertTrue(is_extension(entry))

    def test_unrelated_entry_matches_nothing(self):
        entry = {'ds-cfg-java-class': ['org.opends.server.extensions.SomeOtherPlugin']}
        self.assertFalse(is_lb_we(entry))
        self.assertFalse(is_proxy_we(entry))
        self.assertFalse(is_extension(entry))


class TestAlgoType(unittest.TestCase):
    def test_proportional(self):
        self.assertEqual(algo_type('...ProportionalLoadBalancingAlgorithm'), 'PROPORTIONAL')

    def test_failover(self):
        self.assertEqual(algo_type('...FailoverLoadBalancingAlgorithm'), 'FAILOVER')

    def test_round_robin(self):
        self.assertEqual(algo_type('...RoundRobinLoadBalancingAlgorithm'), 'ROUND-ROBIN')

    def test_unknown_falls_back_to_last_segment(self):
        self.assertEqual(algo_type('com.example.SomeWeirdAlgorithm'), 'SomeWeirdAlgorithm')


class TestFormatters(unittest.TestCase):
    def test_fmt_weights_groups_by_value(self):
        result = fmt_weights({'add': 1, 'modify': 1, 'search': 0})
        self.assertIn('add/modify:1', result)
        self.assertIn('search:0', result)

    def test_fmt_weights_empty(self):
        self.assertEqual(fmt_weights({}), '')

    def test_fmt_priorities_all_same(self):
        result = fmt_priorities({'search': 1, 'add': 1, 'bind': 1})
        self.assertEqual(result, 'all:1')

    def test_fmt_priorities_mixed(self):
        result = fmt_priorities({'search': 1, 'add': 2})
        self.assertIn('search:1', result)
        self.assertIn('add:2', result)

    def test_fmt_priorities_empty(self):
        self.assertEqual(fmt_priorities({}), '')


# ─────────────────────────────────────────────────────────────────────────────
# MODEL EXTRACTION — synthetic minimal proxy config
# ─────────────────────────────────────────────────────────────────────────────

MINI_CONFIG = """\
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
ds-cfg-enabled: true
ds-cfg-workflow-element: cn=LB1,cn=Workflow elements,cn=config
cn: wf1
ds-cfg-base-dn: dc=example,dc=com

dn: cn=ext1,cn=Extensions,cn=config
objectClass: ds-cfg-extension
objectClass: top
objectClass: ds-cfg-ldap-server-extension
ds-cfg-java-class: com.sun.dps.server.workflowelement.proxyldap.LDAPServerExtension
ds-cfg-remote-ldap-server-address: 10.0.0.1
ds-cfg-remote-ldap-server-port: 389
ds-cfg-remote-ldap-server-ssl-port: 1636
ds-cfg-remote-ldap-server-ssl-policy: always
cn: ext1

dn: cn=proxy-we1,cn=Workflow elements,cn=config
objectClass: ds-cfg-workflow-element
objectClass: top
objectClass: ds-cfg-proxy-ldap-workflow-element
ds-cfg-java-class: com.sun.dps.server.workflowelement.proxyldap.ProxyLdapWorkflowElement
ds-cfg-ldap-server-extension: cn=ext1,cn=Extensions,cn=config
ds-cfg-client-cred-mode: use-client-identity
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
ds-cfg-switch-back: true
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
ds-cfg-add-priority: 1
cn: route1
"""


class TestModelExtraction(unittest.TestCase):
    def setUp(self):
        self.path = write_ldif(MINI_CONFIG)
        self.entries, _ = parse_ldif(self.path)

    def tearDown(self):
        os.remove(self.path)

    def test_extract_extensions(self):
        exts = _extract_extensions(self.entries)
        self.assertEqual(len(exts), 1)
        ext = list(exts.values())[0]
        self.assertEqual(ext['address'], '10.0.0.1')
        self.assertEqual(ext['ssl_port'], '1636')

    def test_extract_proxy_we(self):
        pwe = _extract_proxy_we(self.entries)
        self.assertEqual(len(pwe), 1)
        p = list(pwe.values())[0]
        self.assertEqual(p['cn'], 'proxy-we1')
        self.assertEqual(p['cred_mode'], 'use-client-identity')

    def test_extract_workflows(self):
        wfs = _extract_workflows(self.entries)
        self.assertEqual(len(wfs), 1)
        wf = list(wfs.values())[0]
        self.assertEqual(wf['base_dn'], 'dc=example,dc=com')

    def test_extract_network_groups(self):
        ngs = _extract_network_groups(self.entries)
        self.assertEqual(len(ngs), 1)
        self.assertEqual(ngs[0]['cn'], 'network-group')
        self.assertEqual(ngs[0]['priority'], '1')

    def test_extract_lb_we_algorithm_and_routes(self):
        lb_we = _extract_lb_we(self.entries)
        self.assertEqual(len(lb_we), 1)
        lb = list(lb_we.values())[0]
        self.assertEqual(lb['algorithm']['type'], 'FAILOVER')
        self.assertTrue(lb['algorithm']['switch_back'])
        self.assertEqual(len(lb['routes']), 1)
        route = lb['routes'][0]
        self.assertEqual(route['priorities'], {'search': 1, 'add': 1})

    def test_full_extract_model_integration(self):
        model = extract_model(self.entries)
        self.assertEqual(len(model['network_groups']), 1)
        self.assertEqual(len(model['workflows']), 1)
        self.assertEqual(len(model['lb_we']), 1)
        self.assertEqual(len(model['proxy_we']), 1)
        self.assertEqual(len(model['extensions']), 1)

        # end-to-end DN chain resolves correctly
        ng = model['network_groups'][0]
        wf = model['workflows'][ng['workflow_dn']]
        lb = model['lb_we'][wf['entry_we_dn']]
        route = lb['routes'][0]
        pwe = model['proxy_we'][route['we_dn']]
        ext = model['extensions'][pwe['extension_dn']]
        self.assertEqual(ext['address'], '10.0.0.1')


class TestDuplicateCnDetection(unittest.TestCase):
    def test_no_warning_when_all_cns_unique(self):
        path = write_ldif(MINI_CONFIG)
        try:
            entries, _ = parse_ldif(path)
            model = extract_model(entries)
            warnings = find_duplicate_cn_warnings(model)
            self.assertEqual(warnings, [])
        finally:
            os.remove(path)

    def test_warning_when_proxy_we_cn_duplicated(self):
        dup_config = MINI_CONFIG + """
dn: cn=proxy-we1,cn=fake-branch,cn=Workflow elements,cn=config
objectClass: ds-cfg-workflow-element
objectClass: top
objectClass: ds-cfg-proxy-ldap-workflow-element
ds-cfg-java-class: com.sun.dps.server.workflowelement.proxyldap.ProxyLdapWorkflowElement
ds-cfg-ldap-server-extension: cn=ext1,cn=Extensions,cn=config
cn: proxy-we1
"""
        path = write_ldif(dup_config)
        try:
            entries, _ = parse_ldif(path)
            model = extract_model(entries)
            warnings = find_duplicate_cn_warnings(model)
            self.assertEqual(len(warnings), 1)
            self.assertIn('proxy-we1', warnings[0])
        finally:
            os.remove(path)


class TestAnonymize(unittest.TestCase):
    def setUp(self):
        self.path = write_ldif(MINI_CONFIG)
        entries, _ = parse_ldif(self.path)
        self.model = extract_model(entries)

    def tearDown(self):
        os.remove(self.path)

    def test_replaces_real_ip(self):
        count = anonymize_model(self.model)
        self.assertEqual(count, 1)
        ext = list(self.model['extensions'].values())[0]
        self.assertNotEqual(ext['address'], '10.0.0.1')
        self.assertTrue(ext['address'].startswith('198.51.100.'))

    def test_is_deterministic_across_calls(self):
        anonymize_model(self.model)
        first_ip = list(self.model['extensions'].values())[0]['address']
        # re-extract fresh model and anonymize again — same mapping order in, same result out
        entries, _ = parse_ldif(self.path)
        model2 = extract_model(entries)
        anonymize_model(model2)
        second_ip = list(model2['extensions'].values())[0]['address']
        self.assertEqual(first_ip, second_ip)

    def test_same_real_ip_maps_to_same_placeholder(self):
        # add a second extension entry sharing the same real IP as ext1
        dup_config = MINI_CONFIG + """
dn: cn=ext2,cn=Extensions,cn=config
objectClass: ds-cfg-extension
objectClass: top
objectClass: ds-cfg-ldap-server-extension
ds-cfg-java-class: com.sun.dps.server.workflowelement.proxyldap.LDAPServerExtension
ds-cfg-remote-ldap-server-address: 10.0.0.1
ds-cfg-remote-ldap-server-port: 389
cn: ext2
"""
        path = write_ldif(dup_config)
        try:
            entries, _ = parse_ldif(path)
            model = extract_model(entries)
            anonymize_model(model)
            addrs = {ext['address'] for ext in model['extensions'].values()}
            self.assertEqual(len(addrs), 1)  # same real IP -> same placeholder
        finally:
            os.remove(path)


class TestDisabledMarker(unittest.TestCase):
    def test_no_marker_when_all_enabled(self):
        self.assertEqual(disabled_marker('true', 'true'), '')

    def test_marker_when_any_flag_false(self):
        self.assertIn('DISABLED', disabled_marker('true', 'false'))
        self.assertIn('DISABLED', disabled_marker('false', 'true'))
        self.assertIn('DISABLED', disabled_marker('false'))

    def test_case_insensitive(self):
        self.assertIn('DISABLED', disabled_marker('FALSE'))
        self.assertEqual(disabled_marker('TRUE'), '')


class TestExtractProxyWeAndExtensionsTrackEnabled(unittest.TestCase):
    """O3 — proxy WEs and extensions must expose their enabled state so
    render_tree/backend table can flag disabled components."""

    def setUp(self):
        self.path = write_ldif(MINI_CONFIG)
        self.entries, _ = parse_ldif(self.path)

    def tearDown(self):
        os.remove(self.path)

    def test_proxy_we_has_enabled_field(self):
        pwe = _extract_proxy_we(self.entries)
        p = list(pwe.values())[0]
        self.assertIn('enabled', p)
        self.assertEqual(p['enabled'], 'true')  # MINI_CONFIG doesn't set it explicitly -> default

    def test_extension_has_enabled_field(self):
        exts = _extract_extensions(self.entries)
        ext = list(exts.values())[0]
        self.assertIn('enabled', ext)
        self.assertEqual(ext['enabled'], 'true')


if __name__ == '__main__':
    unittest.main(verbosity=2)
