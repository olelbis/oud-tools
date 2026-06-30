# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

---

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
