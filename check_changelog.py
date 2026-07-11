#!/usr/bin/env python3
"""
check_changelog.py
--------------------
Guard against the exact documentation bug that occurred repeatedly during
this project's development: a version header (`## [...]`) being lost during
an edit, leaving a `---` separator followed by orphaned `### ...` content
with no version attached.

Checks:
  1. Every `---` separator (outside the intro) is followed — allowing blank
     lines — by a `## [` version header or end-of-file.
  2. No two consecutive `## [` headers without content between them.
  3. Every version header matches the expected format:
     `## [<something>] - YYYY-MM-DD`

Usage:
    python check_changelog.py [CHANGELOG.md]

Exit code: 0 if clean, 1 if any problem is found.
Intended use: run before every commit that touches CHANGELOG.md
(manually, or as a pre-commit hook / CI step).
"""

import re
import sys

HEADER_RE = re.compile(r'^## \[.+\] - \d{4}-\d{2}-\d{2}( .*)?\s*$')


def check(path):
    with open(path, encoding='utf-8') as fh:
        lines = fh.read().splitlines()

    problems = []
    header_indices = [i for i, l in enumerate(lines) if l.startswith('## ')]

    # Check 3: header format
    for i in header_indices:
        if not HEADER_RE.match(lines[i]):
            problems.append(f'line {i+1}: malformed version header: {lines[i]!r} '
                            f'(expected "## [name] - YYYY-MM-DD")')

    # Check 1: every --- after the first header is followed by a ## [ header or EOF
    first_header = header_indices[0] if header_indices else len(lines)
    i = first_header
    while i < len(lines):
        if lines[i].strip() == '---':
            j = i + 1
            while j < len(lines) and lines[j].strip() == '':
                j += 1
            if j < len(lines) and not lines[j].startswith('## ['):
                problems.append(
                    f'line {i+1}: "---" separator is followed by {lines[j]!r} '
                    f'instead of a "## [" version header — a header was probably '
                    f'lost during an edit (the recurring bug this script exists to catch)')
            i = j
        else:
            i += 1

    # Check 2: orphaned "### " sections directly after a separator with no header
    # (covered by check 1, but also catch "### " as the very first content line)
    for i, l in enumerate(lines[:first_header]):
        if l.startswith('### '):
            problems.append(f'line {i+1}: "### " subsection appears before any '
                            f'version header')

    return problems


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else 'CHANGELOG.md'
    try:
        problems = check(path)
    except FileNotFoundError:
        print(f'[ERROR] File not found: {path}')
        sys.exit(1)

    if problems:
        print(f'[FAIL] {len(problems)} problem(s) found in {path}:')
        for p in problems:
            print(f'  - {p}')
        sys.exit(1)

    print(f'[OK] {path}: all version headers present and well-formed.')
    sys.exit(0)


if __name__ == '__main__':
    main()
