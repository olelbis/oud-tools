#!/usr/bin/env python3
"""
test_oud_ldif_core.py
-----------------------
Unit tests for the shared oud_ldif_core.py module (E2).

These mirror the parser-related tests already in test_oud_lb_diagram.py
(which re-exports the same functions via `from oud_ldif_core import ...`
inside oud_lb_diagram.py), but target oud_ldif_core.py directly so the
module can be tested in isolation from any downstream tool.

Run with:
    python3 -m unittest test_oud_ldif_core.py -v
"""

import unittest
import tempfile
import os
import base64

from oud_ldif_core import parse_ldif, first, cn_of


def write_ldif(text):
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

    def test_mixed_case_dn_normalised(self):
        path = write_ldif("dn: CN=Foo,CN=Config\ncn: Foo\n")
        try:
            entries, _ = parse_ldif(path)
            self.assertIn('cn=foo,cn=config', entries)
        finally:
            os.remove(path)


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

    def test_multiple_continuations(self):
        path = write_ldif(
            "dn: cn=foo,cn=config\n"
            "description: abc\n"
            " def\n"
            " ghi\n"
        )
        try:
            entries, _ = parse_ldif(path)
            self.assertEqual(first(entries['cn=foo,cn=config'], 'description'), 'abcdefghi')
        finally:
            os.remove(path)


class TestParseLdifBase64(unittest.TestCase):
    def test_base64_value_decoded(self):
        encoded = base64.b64encode(b'hello world').decode('ascii')
        path = write_ldif(f"dn: cn=foo,cn=config\ndescription:: {encoded}\n")
        try:
            entries, _ = parse_ldif(path)
            self.assertEqual(first(entries['cn=foo,cn=config'], 'description'), 'hello world')
        finally:
            os.remove(path)

    def test_url_reference_stored_as_is(self):
        path = write_ldif("dn: cn=foo,cn=config\njpegphoto:< file:///tmp/photo.jpg\n")
        try:
            entries, _ = parse_ldif(path)
            self.assertEqual(first(entries['cn=foo,cn=config'], 'jpegphoto'), 'file:///tmp/photo.jpg')
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

    def test_multiple_blank_lines_between_entries(self):
        path = write_ldif(
            "dn: cn=foo,cn=config\ncn: foo\n\n\n\ndn: cn=bar,cn=config\ncn: bar\n"
        )
        try:
            entries, _ = parse_ldif(path)
            self.assertEqual(len(entries), 2)
        finally:
            os.remove(path)


class TestCnOf(unittest.TestCase):
    def test_extracts_first_cn_component(self):
        self.assertEqual(cn_of('cn=foo,cn=bar,cn=config'), 'foo')

    def test_returns_dn_if_no_cn(self):
        self.assertEqual(cn_of('ou=people,dc=example,dc=com'), 'ou=people,dc=example,dc=com')

    def test_case_insensitive_match(self):
        self.assertEqual(cn_of('CN=Foo,cn=config'), 'Foo')


if __name__ == '__main__':
    unittest.main(verbosity=2)
