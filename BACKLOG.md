# Backlog — oud-tools

Priority: H=High / M=Medium / L=Low

---

## Bug / Robustness

| # | P | Item |
|---|---|------|
| B1 | ~~H~~ | ~~LDIF line continuation (lines starting with space per RFC 4511)~~ → **done 1.2.0** |
| B2 | ~~H~~ | ~~base64 values (`attr:: dmFsdWU=`) silently ignored~~ → **done 1.2.0** |
| B3 | ~~M~~ | ~~DN comparison is case-sensitive in places — normalise to lower consistently~~ → **done 1.2.0** |
| B4 | ~~M~~ | ~~Warn if `ds-cfg-workflow-element` points to an unresolved DN~~ → **done 1.2.0** |
| B5 | ~~M~~ | ~~DN collision if two WEs share the same CN on different branches~~ → **done 1.4.0 (warning added)** |
| B6 | L | Network group without workflow shows `base-dn:?` — add explicit warning |
| B7 | M | Detect and warn early if config has no proxy/LB workflow elements (see E1 for broader approach) |

---

## Ecosystem (longer-term)

| # | P | Item |
|---|---|------|
| E1 | M | `oud_config_type.py` — generic OUD instance classifier (Proxy / Directory Server / Replication Gateway / Global Index Catalog) based on `ds-cfg-java-class` patterns. Feeds B7 and P3. |
| E2 | L | Extract shared `oud_ldif_core.py` (parse_ldif, DN utils, first/cn_of) out of `oud_lb_diagram.py` so multiple tools can reuse the same parsing layer |
| E3 | L | `oud_backend_report.py` — companion tool for plain OUD Directory Server configs (local backends, indexes, replication), mirroring what `oud_lb_diagram.py` does for proxy configs |

---

## Output

| # | P | Item |
|---|---|------|
| O1 | ~~M~~ | ~~Deep tree branches can exceed `MAX_W` — account for indentation in width calc~~ → **done 1.4.0** |
| O2 | ~~M~~ | ~~Workflow tree body unframed — consider consistent boxing with other sections~~ → **done 1.4.0** |
| O3 | L | Highlight disabled WEs (`ds-cfg-enabled: false`) more visibly (e.g. `[DISABLED]` in red or `!!`) |

---

## Features

| # | P | Item |
|---|---|------|
| F1 | ~~M~~ | ~~`--output <file>` flag to save diagram to disk~~ → **done 1.3.0** |
| F2 | ~~M~~ | ~~`--no-tree` flag to print only backend table (quick summary mode)~~ → **done 1.3.0** |
| F3 | L | `--anonymize` flag to mask IPs in output |
| F4 | L | JSON/YAML output mode for machine-readable consumption |

---

## Code Quality

| # | P | Item |
|---|---|------|
| C1 | M | Split `extract_model()` into focused functions (one per object type) |
| C2 | ~~L~~ | ~~Move Java class name fragments to named constants~~ → **done 1.3.1** |
| C4 | ~~M~~ | ~~Backend table column widths are magic numbers duplicated between header and data row~~ → **done 1.3.1** |
| C3 | L | Add basic unit tests for parser and model extraction |

---

## Project / Repo

| # | P | Item |
|---|---|------|
| P3 | L | **Planned, not started.** Second tool: `oud_config_lint.py` — validator/linter for OUD proxy configs. Scope TBD: candidate checks = orphan/broken DN references (reuses existing parser), SSL/timeout/pool-size best practices, disabled-but-referenced WEs, unbalanced failover priorities. |

---

## Done

| # | Version | Item |
|---|---------|------|
| D1 | 1.0.0 | Generic tree exploration (any depth, no hardcoded structure) |
| D2 | 1.0.0 | Per-operation weights and priorities |
| D3 | 1.0.0 | Backend servers summary table |
| D4 | 1.1.0 | Dynamic diagram width (MIN_W / MAX_W) |
| D6 | 1.2.0 | RFC 4511 line folding (B1) |
| D7 | 1.2.0 | base64 and URL value decoding (B2) |
| D8 | 1.2.0 | Case-insensitive DN normalisation (B3) |
| D9 | 1.2.0 | Warn on unresolved DN references (B4) |
| P1 | 1.2.0 | README updated with v1.2.0 parser fixes |
| P2 | 1.2.0 | Release notes drafted for v1.2.0 |
| D10 | 1.3.0 | `--output <file>` flag (F1) |
| D11 | 1.3.0 | `--no-tree` flag (F2) |
| D12 | 1.3.1 | Java class fragments extracted to named constants (C2) |
| D13 | 1.3.1 | Backend table column widths extracted to named constants (C4) |
| D14 | 1.4.0 | Duplicate CN detection/warning (B5) |
| D15 | 1.4.0 | Tree width counted in box width calc (O1) |
| D16 | 1.4.0 | Workflow tree rendered as boxed section (O2) |
