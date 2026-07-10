# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

---

## [oud_backend_report.py v1.1.0] - 2026-07-02

### Added
- **`--anonymize` flag** — replaces replication-server hostnames/IPs with
  RFC 5737 documentation-range placeholders, preserving the port
  (`10.179.162.230:8989` → `198.51.100.1:8989`). Same real host always maps
  to the same placeholder across all replication domains. Closes a real
  gap: v1.0.0 had no way to safely share a report generated from a real
  config, unlike `oud_lb_diagram.py` which has had this since v1.7.0.
- **`config_ds_test.ldif`** — a small, safe, synthetic OUD Directory Server
  config fixture (19 entries: 1 user-data backend with 9 indexes, 3
  system/private backends correctly excluded, 3 replication domains with
  RFC 5737 addresses) for testing and documentation, so real production
  configs never need to be used or shared for this purpose.
- **2 new unit tests** for `anonymize_domains()`: host replacement with
  port preservation, and stable mapping when the same host appears in
  multiple replication domains. Combined repo test count: 58.

### Notes
- No change in behaviour when `--anonymize` is not passed.
- Verified against a real production config: the same host now
  consistently maps to the same placeholder across all 3 domains that
  shared it.

---

## [oud_backend_report.py v1.0.0] - 2026-07-02

### Added
- **New companion tool: `oud_backend_report.py` (E3)** — reads an OUD
  **Directory Server** config (not proxy) and reports:
  - Local user-data backends (excludes system/private backends like
    schema, tasks, admin, trust store, backup, using the same
    `ds-cfg-is-private-backend` / objectClass distinction `oud_config_type.py`
    already makes) — base-dn, writability, txn-durability, db-directory,
    compression, default index-entry-limit, index count, `⚠ DISABLED` marker.
  - Indexes per backend — attribute, index type(s), entry limit. Tested
    against a real config with 102 indexes on one backend.
  - Replication domains — base-dn, server-id, group-id, replication
    servers, isolation policy, window size.
  Built on the shared `oud_ldif_core.py` parser, same as the other two
  tools. Includes a soft, inverted B7-style check: warns if the loaded
  config looks like an OUD Proxy rather than a Directory Server.
  `--version` and `--output <file>` supported, same conventions as
  `oud_lb_diagram.py`.
- **`test_oud_backend_report.py`** — 4 unit tests (backend extraction,
  system-backend exclusion, index extraction, replication domain
  extraction). Combined repo test count: 56.

### Notes
- Verified end-to-end against a real production Directory Server config
  (380 entries, 1 user-data backend with 102 indexes, 3 replication
  domains) — output was clean and correctly excluded internal backends.
- This closes the last "Ecosystem" backlog item (E3). Only P3 (the
  planned linter) remains open.

---

## [1.9.0] - 2026-07-02

### Added
- **`--format json` flag (F4)** — outputs the full parsed model as
  structured JSON instead of the ASCII diagram, wrapped in a small envelope
  (`tool`, `tool_version`, `source_file`, `anonymized`, `model`). Combines
  with `--anonymize` and `--output`. YAML is intentionally not offered —
  it isn't in the Python standard library and this project has no external
  dependencies; pipe the JSON through a converter if YAML is needed.
  `--no-tree` has no effect in JSON mode (the payload always contains the
  full model) and prints a one-line note to that effect.
- **Disabled-component highlighting (O3)** — `proxy_we` and `extensions`
  entries now track their own `ds-cfg-enabled` state (previously only
  `lb_we` did). Both the workflow tree and the backend servers table now
  show a `⚠ DISABLED` marker whenever a proxy WE **or** its underlying
  extension is disabled — either one makes that route effectively unusable,
  so both are checked. New shared `disabled_marker()` helper used
  consistently in both places instead of the LB-WE-only inline check from
  earlier versions. Documented in the legend.
- **5 new unit tests**: 3 for `disabled_marker()`, 2 confirming `proxy_we`/
  `extensions` extraction expose the `enabled` field. Suite now at 38 tests
  in `test_oud_lb_diagram.py` (52 combined with `test_oud_ldif_core.py`).

### Changed
- **stdout/stderr split for JSON mode.** All diagnostic/status lines
  (`[+] Parsed ...`, `[WARN] ...`, `[+] Found ...`, etc.) are now written to
  **stderr** when `--format json` is active, so stdout carries pure,
  pipeable JSON even without `--output`
  (e.g. `oud_lb_diagram.py config.ldif --format json | jq .` now works
  cleanly). In text mode (default) diagnostics remain on stdout, unchanged
  from every previous version — verified byte-for-byte identical text-mode
  output against v1.8.0.

---

## [1.8.0] - 2026-07-02

### Added
- **New shared module: `oud_ldif_core.py` (E2)** — extracted `parse_ldif()`,
  `first()`, `cn_of()`, and their internal helpers (`_decode_value()`,
  `_fold_lines()`) out of `oud_lb_diagram.py` into a standalone module with
  no dependency on any downstream tool. Versioned independently (`1.0.0`).
- **`test_oud_ldif_core.py`** — 14 dedicated unit tests for the new module
  (parsing basics, line folding, base64/URL decoding, comments, blank-line
  handling, DN/cn case normalisation), including a URL-reference test case
  not previously covered. Combined test count across the repo: 47.

### Changed
- **`oud_lb_diagram.py`** now imports `parse_ldif`, `first`, `cn_of` from
  `oud_ldif_core` instead of defining them locally. It requires
  `oud_ldif_core.py` to be present in the same directory (hard dependency —
  fails fast with a clear error if missing, since parsing is impossible
  without it). No behavioural change: verified byte-for-byte identical
  output against v1.7.0 across all test configs.
- **`oud_config_type.py`** now imports `parse_ldif`, `first` from
  `oud_ldif_core` instead of `oud_lb_diagram`. This removes the previous
  dependency direction where the classifier reached into the diagram tool
  just to get the parser (noted as a known limitation in the 1.5.0 entry
  below) — the two tools are now siblings built on the same shared core
  rather than one depending on the other.
- `test_oud_lb_diagram.py`'s existing parser-related tests are unchanged
  and still pass: `oud_lb_diagram.py` re-exports the imported names, so
  `from oud_lb_diagram import parse_ldif` continues to work exactly as
  before.

### Notes
- This closes out the last "Ecosystem" backlog item needed before E3
  (`oud_backend_report.py`, a companion tool for plain OUD Directory Server
  configs) can be started on solid footing.

---

## [1.7.0] - 2026-07-02

### Added
- **`--anonymize` flag (F3)** — replaces real backend IPs with placeholders
  from RFC 5737 documentation ranges (`198.51.100.0/24`, `203.0.113.0/24`,
  `192.0.2.0/24` — safe to publish, never routable). Mapping is applied at
  the model level (`model['extensions']`) before rendering, so both the
  workflow tree and the backend servers table show the same placeholder
  consistently. The mapping is deterministic (sorted by DN) and stable:
  the same real IP always maps to the same placeholder, even if referenced
  by multiple proxy WEs. Prints a one-line confirmation
  (`[+] --anonymize: replaced N unique backend IP(s) ...`) to stdout, same
  as other status lines — never written into a file targeted by `--output`.
  Combines freely with `--output` and `--no-tree`.
- **3 new unit tests** covering `anonymize_model()`: basic replacement,
  determinism across repeated runs, and stable mapping when the same real
  IP is shared by two different extension entries.

### Notes
- No change in behaviour when `--anonymize` is not passed — verified
  byte-for-byte identical output against v1.6.0.

---

## [1.6.0] - 2026-07-02

### Added
- **`test_oud_lb_diagram.py` (C3)** — basic unit test suite (30 tests,
  standard library `unittest`, no external dependencies). Covers LDIF
  parsing (line folding, base64, comments, blank-line separation, DN/attr
  case normalisation), small utilities (`cn_of`, classifiers, `algo_type`),
  formatters (`fmt_weights`, `fmt_priorities`), each `_extract_*` function
  in isolation, a full `extract_model()` integration test against a small
  synthetic proxy config, and `find_duplicate_cn_warnings()` (B5).
  Run with `python3 -m unittest test_oud_lb_diagram.py -v`.

### Fixed
- **Base64 value decoding never actually triggered (regression from 1.2.0,
  caught by the new test suite).** The separator-detection logic compared
  the position of `'::'`/`':<'` against the position of the first `':'` —
  but since both start with `:`, that position is always identical, so the
  condition never fired and the base64/URL branches were unreachable in
  practice. Every `attr:: <b64>` line was silently misparsed as plain text
  containing a stray leading `:`. Rewritten to inspect the character
  immediately following the first colon instead of comparing substring
  positions. No change in behaviour for configs without base64/URL values
  (verified byte-for-byte identical output on the real test config).

---

## [1.5.2] - 2026-07-02

### Changed
- **Code quality (no behaviour change).** Split the monolithic
  `extract_model()` into focused, independently readable extractors (C1):
  `_extract_extensions()`, `_extract_proxy_we()`, `_extract_workflows()`,
  `_extract_network_groups()`, `_extract_lb_we()` (with helpers
  `_extract_route_algorithm()` and `_extract_routes()`). `extract_model()`
  now only orchestrates calls to these and assembles the result dict.
  Verified byte-for-byte identical output against v1.5.1 on all test configs.

---

## [1.5.1] - 2026-07-02

### Fixed
- **Silent B6 warning (bug in the original B4 implementation)** — a network
  group with no `ds-cfg-workflow` at all (empty string) produced no warning,
  because the check `if wf_dn and wf_dn not in model['workflows']`
  short-circuits on an empty string and never reaches the "not in workflows"
  branch. Split into two explicit cases: empty `ds-cfg-workflow` now warns
  directly (`"has no workflow configured"`), and a non-empty but unresolved
  reference still warns as before (`"references unknown workflow"`).

---

## [1.5.0] - 2026-07-02

### Added
- **New tool: `oud_config_type.py` (E1)** — generic OUD instance classifier.
  Inspects `ds-cfg-java-class` and objectClass patterns to determine whether
  a config is an OUD Proxy, OUD Directory Server, a Hybrid (both proxy-LB
  and a real local data backend present), or inconclusive. Reports evidence
  (matching DNs) for every signal so the classification can be checked by
  a human. Can be run standalone: `python oud_config_type.py <config.ldif>`.
  Distinguishes system/internal local backends (schema, tasks, monitor,
  backup, trust store) from genuine user-data backends
  (`ds-cfg-db-local-backend-workflow-element` with
  `ds-cfg-is-private-backend` not `true`) to avoid false "Hybrid" positives.
- **Early scope warning (B7)** — `oud_lb_diagram.py` now calls into
  `oud_config_type.py` (soft dependency — degrades silently if that file
  isn't present alongside it) and prints a `[WARN]` up front if the loaded
  config doesn't look like an OUD Proxy instance, since the diagram would
  otherwise come out empty or misleading on an unsupported config type.

### Notes
- `oud_config_type.py` currently imports `parse_ldif`/`first` from
  `oud_lb_diagram.py`; both files must be kept in the same directory.
  A future refactor (BACKLOG item E2) will extract a standalone
  `oud_ldif_core.py` module so this dependency direction goes away.

---

## [1.4.0] - 2026-07-02

### Added
- **Duplicate CN detection (B5)** — warns when two distinct entries (proxy WE,
  LB WE, or extension) share the same `cn` under different parents. Routing
  and rendering were always correct (full DN used as the lookup key), but
  identical labels in the diagram could mislead a human reader; this makes
  the ambiguity explicit via `[WARN] duplicate ... cn "..." used by N distinct
  entries ...` with both DNs listed.

### Changed
- **Workflow tree is now a boxed section (O2)** — previously printed
  unframed below its header box; the full tree body is now captured and
  rendered inside the same frame style as every other section
  (network groups, backend servers, legend).
- **Tree width now counts toward the box width (O1)** — as a consequence of
  the above, deeply indented branches are no longer silently excluded from
  the width calculation; the frame now sizes itself to fit the tree content
  too (still bounded by `MIN_W`/`MAX_W`).

---

## [1.3.1] - 2026-07-02

### Changed
- **Code quality (no behaviour change).** Java class name fragments
  (`LoadBalancingWorkflowElement`, `ProxyLdapWorkflowElement`,
  `LDAPServerExtension`, algorithm type fragments) extracted to named
  constants (`JC_*`, `ALGO_LABELS`) instead of inline string literals.
- **Code quality (no behaviour change).** Backend servers table column
  widths (`Extension`, `WE`, `IP Address`, `Port`, `SSL`, `Policy`, `Pool`)
  extracted to named constants (`COL_*`), now defined once and shared
  between the header row and data rows — previously duplicated literals
  that could silently drift out of sync.

---

## [1.3.0] - 2026-07-02

### Added
- `--output <file>` flag — writes the diagram to a file instead of stdout.
  Parse summary and warnings still print to stdout even when `--output` is used.
- `--no-tree` flag — skips the workflow tree section(s), printing only network
  groups, backend servers table, and legend. Useful for a quick backend inventory.
- Both flags can be combined: `--output report.txt --no-tree`.
- Minimal hand-rolled argument parser (`parse_args()`), no external dependencies.

### Fixed
- **Backend servers table separator** — the dashed line under the column
  header now stretches to the full dynamic box width instead of a fixed
  length tied to the header text. Implemented via a `Section.add_separator()`
  sentinel rendered at print time.
- **Asymmetric box padding** — the box width calculation previously left a
  2-space margin on the left but only 1 space on the right for the widest
  line in a section (e.g. the `use-client-identity` column in the backend
  table), making right borders look ragged/overflowing. Width is now
  computed to guarantee a symmetric 2-space margin on both sides.

### Changed
- `print_diagram()`, `print_section()`, `print_header()` and `render_tree()`
  now accept an optional `file=` parameter for output redirection.
- Unknown CLI flags now produce a clear `[ERROR] Unknown option: ...` and exit
  with status 1, instead of being silently ignored or misread as a config path.

---

## [1.2.0] - 2026-07-02

### Fixed
- **RFC 4511 line folding** — continuation lines (starting with a single space)
  are now correctly joined before parsing, preventing truncated values.
- **base64-encoded values** (`attr:: <b64>`) are now decoded to UTF-8;
  binary values fall back to hex representation instead of being silently ignored.
- **URL references** (`attr:< <url>`) are now recognised and stored as-is.
- **Case-insensitive DN lookup** — all entry keys and DN references from
  attributes are normalised to lowercase, eliminating silent mismatches on
  configs with mixed-case DNs.
- **O(1) algorithm lookup** — `cn=algorithm,<dn>` is now resolved via direct
  dict lookup instead of a full scan of all entries.

### Added
- **Parse warnings** — `parse_ldif()` now returns a `(entries, warnings)` tuple;
  warnings are printed to stdout before the diagram.
- **Unresolved DN warnings** (B4) — `[WARN]` lines are emitted for any
  `ds-cfg-workflow-element` or `ds-cfg-ldap-server-extension` reference that
  cannot be resolved in the parsed entries.

### Changed
- `parse_ldif()` return signature changed from `entries` to `(entries, warnings)`.
- Entry CN display now always reads from the `cn` attribute value (preserving
  original casing) rather than extracting from the lowercased DN key.

## [1.1.0] - 2026-06-30

### Added
- `--version` / `-v` flag to print the script version and exit.
- `__version__` constant in the script header.

### Changed
- **Dynamic diagram width.** The diagram frame width is no longer a fixed
  constant (`W = 92`); it is now computed from the actual content of every
  boxed section (network groups, workflow tree headers, backend servers
  table, legend), so frames always fit the content without being needlessly
  wide or truncating long lines.
  - Added `MIN_W = 60` (minimum width) and `MAX_W = 200` (safety cap) to
    bound the computed width.
- **Refactored rendering into a `Section` model.** Boxed sections are now
  built as `Section` objects (title + body lines) before being measured and
  printed, replacing the previous approach of printing fixed-width boxes
  directly. This required splitting the old monolithic `print_diagram()`
  into:
  - `build_network_groups_section()`
  - `build_workflow_header_sections()`
  - `build_backend_servers_section()`
  - `build_legend_section()`
  - `print_section()` / `print_header()` for rendering
  - `print_diagram()` now only orchestrates width calculation and printing.

### Notes
- The workflow tree body (the recursive `render_tree()` output) is still
  printed unframed, as before — only the surrounding boxed sections adapt
  to the new dynamic width.
- No changes to LDIF parsing, model extraction, or routing logic.

---

## [1.0.0] - 2026-06-30

### Added
- Initial generic release.
- LDIF parser (standard library only, no external dependencies).
- Dynamic, depth-agnostic exploration of the OUD workflow element tree
  (no hardcoded assumptions about branch names or hierarchy depth).
- Support for `PROPORTIONAL`, `FAILOVER`, and `ROUND-ROBIN` load-balancing
  algorithms.
- Per-operation **weights** display for proportional routes
  (e.g. `add/modify/delete:1  search/bind:0`).
- Per-operation **priorities** display for failover routes
  (e.g. `all:1` or `search/bind:1  add/modify:2`), replacing the earlier
  single-priority assumption.
- `switch-back: ON` flag display for failover algorithms.
- Backend resolution: proxy workflow element → LDAP server extension → IP,
  port, SSL port, SSL policy, connection pool size, credential mode.
- Network groups summary table.
- Backend servers summary table.
- Text legend explaining diagram notation.

---

## [0.1.0] - 2026-06-30 (superseded)

### Added
- First working version, tailored to a single specific OUD config
  structure (3 fixed hierarchy levels: `LB_MS → LB-Master/LB-Slave → FO_x`).
- Hardcoded detection of WRITE vs READ branch based on weight pattern.
- Fixed-width (90-column) box rendering.

### Limitations (addressed in 1.0.0)
- Assumed exactly 2 branches (WRITE/READ) identified by weight pattern.
- Assumed a fixed 3-level hierarchy; did not generalize to other depths.
- Assumed a single priority value per route (`ds-cfg-search-priority` used
  as representative for all operations), which could be incorrect if
  priorities differ per operation type.
- Relied on hardcoded Java class name matching without fallback.
