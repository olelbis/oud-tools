# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

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
