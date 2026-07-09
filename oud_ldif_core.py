#!/usr/bin/env python3
"""
oud_ldif_core.py
-----------------
Shared LDIF parsing layer for the oud-tools repo (E2).

This module contains everything that is generic to *any* OUD/OpenDS LDIF
config — not specific to proxy configs, directory server configs, or any
particular tool's object model. It exists so `oud_lb_diagram.py`,
`oud_config_type.py`, and future tools (e.g. the planned
`oud_backend_report.py` / `oud_config_lint.py`) can all parse LDIF the
same way without duplicating or drifting out of sync.

Provides:
    parse_ldif(path)   -> (entries, warnings)
    first(entry, attr, default='')
    cn_of(dn)

No external dependencies (standard library only).
"""

__version__ = "1.0.0"

import re
import base64
from collections import defaultdict


# ─────────────────────────────────────────────────────────────────────────────
# LDIF PARSER  (RFC 4511 compliant)
# ─────────────────────────────────────────────────────────────────────────────

def _decode_value(sep, raw_val):
    """
    Decode an LDIF attribute value based on separator:
      ':'  → plain UTF-8 string  (strip leading space)
      '::' → base64-encoded value (decode to UTF-8, fallback to hex repr)
      ':<' → URL reference (returned as-is)
    """
    val = raw_val.lstrip(' ')
    if sep == '::':
        try:
            return base64.b64decode(val).decode('utf-8')
        except Exception:
            return base64.b64decode(val).hex()
    return val   # plain or URL


def _fold_lines(fh):
    """
    Generator: yield logical LDIF lines by joining RFC 4511 continuations.
    A line starting with a single space is a continuation of the previous line
    (the leading space is stripped before joining).
    Yields '' for blank lines (entry separators).
    """
    current = None
    for raw in fh:
        line = raw.rstrip('\r\n')
        if line.startswith(' '):
            # continuation — append to current logical line (drop leading space)
            if current is not None:
                current += line[1:]
        else:
            if current is not None:
                yield current
            current = line
    if current is not None:
        yield current


def parse_ldif(path):
    """
    Return dict  dn (normalised to lower-case) -> {attr: [values]}.
    Handles:
      - RFC 4511 line folding (continuation lines starting with space)
      - base64-encoded values  (attr:: <b64>)
      - URL references         (attr:< <url>)  — stored as-is
      - Comment lines          (# ...)
      - Case-insensitive attribute names (stored lower-case)
      - Case-insensitive DN normalisation (stored lower-case)

    Returns (entries, warnings) — warnings is currently always [] but kept
    in the return signature for forward compatibility (e.g. malformed-line
    reporting), and because callers already destructure it.
    """
    entries  = {}
    dn_key   = None   # lower-case DN used as dict key
    dn_orig  = None   # original DN casing (for display if needed)
    current  = defaultdict(list)
    warnings = []

    with open(path, encoding='utf-8', errors='replace') as fh:
        for line in _fold_lines(fh):

            # blank line → flush current entry
            if line.strip() == '':
                if dn_key:
                    entries[dn_key] = dict(current)
                dn_key  = None
                dn_orig = None
                current = defaultdict(list)
                continue

            # comment
            if line.startswith('#'):
                continue

            # detect separator by inspecting what follows the FIRST colon
            # (a naive approach comparing '::'/':<' position against the
            # first ':' position never fires, since '::' and ':<' always
            # start with ':' — same position — so this must look at the
            # character right after the first colon instead)
            colon_pos = line.find(':')
            if colon_pos == -1:
                continue  # malformed line — skip
            key = line[:colon_pos]
            rest = line[colon_pos + 1:]
            if rest.startswith(':'):
                sep, raw_val = '::', rest[1:]
            elif rest.startswith('<'):
                sep, raw_val = ':<', rest[1:]
            else:
                sep, raw_val = ':', rest

            key = key.strip().lower()
            val = _decode_value(sep, raw_val)

            if key == 'dn':
                dn_orig = val
                dn_key  = val.lower()   # normalise for consistent lookup
                current = defaultdict(list)
            elif dn_key is not None:
                current[key].append(val)
            # else: attribute before first dn — skip silently

    # flush last entry (file not ending with blank line)
    if dn_key and current:
        entries[dn_key] = dict(current)

    return entries, warnings


# ─────────────────────────────────────────────────────────────────────────────
# SMALL DN / ATTRIBUTE UTILITIES
# ─────────────────────────────────────────────────────────────────────────────

def first(entry, attr, default=''):
    """Return the first value of `attr` in `entry`, or `default` if absent."""
    return entry.get(attr, [default])[0]


def cn_of(dn):
    """Extract the leftmost cn= component of a DN, or return the DN unchanged."""
    m = re.match(r'cn=([^,]+)', dn, re.IGNORECASE)
    return m.group(1) if m else dn
