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
| B6 | ~~L~~ | ~~Network group without workflow shows `base-dn:?` — add explicit warning~~ → **done 1.5.1** |
| B7 | ~~M~~ | ~~Detect and warn early if config has no proxy/LB workflow elements~~ → **done 1.5.0 (via E1)** |

---

## Ecosystem (longer-term)

| # | P | Item |
|---|---|------|
| E1 | ~~M~~ | ~~`oud_config_type.py` — generic OUD instance classifier~~ → **done 1.5.0** (categories implemented: OUD Proxy / OUD Directory Server / Hybrid / Inconclusive; Replication Gateway and standalone Global Index Catalog reported as secondary features, not yet distinct primary categories — no confirmed class-name evidence for those as separate instance types) |
| E2 | ~~L~~ | ~~Extract shared `oud_ldif_core.py`~~ → **done 1.8.0** — parse_ldif/first/cn_of now shared; oud_config_type.py also migrated off oud_lb_diagram |
| E3 | ~~L~~ | ~~`oud_backend_report.py` — companion tool for plain OUD Directory Server configs~~ → **done (v1.1.0)** — backends, indexes, replication domains, `--anonymize`; tested against a real 380-entry DS config with 102 indexes; public test fixture `config_ds_test.ldif` added |

---

## Output

| # | P | Item |
|---|---|------|
| O1 | ~~M~~ | ~~Deep tree branches can exceed `MAX_W` — account for indentation in width calc~~ → **done 1.4.0** |
| O2 | ~~M~~ | ~~Workflow tree body unframed — consider consistent boxing with other sections~~ → **done 1.4.0** |
| O3 | ~~L~~ | ~~Highlight disabled WEs more visibly~~ → **done 1.9.0** — extended to proxy WE + extensions too, not just LB WE |

---

## Features

| # | P | Item |
|---|---|------|
| F1 | ~~M~~ | ~~`--output <file>` flag to save diagram to disk~~ → **done 1.3.0** |
| F2 | ~~M~~ | ~~`--no-tree` flag to print only backend table (quick summary mode)~~ → **done 1.3.0** |
| F3 | ~~L~~ | ~~`--anonymize` flag to mask IPs in output~~ → **done 1.7.0** |
| F4 | ~~L~~ | ~~JSON/YAML output mode~~ → **done 1.9.0 (JSON only** — YAML needs an external dependency, out of scope for this project)** |

---

## Code Quality

| # | P | Item |
|---|---|------|
| C1 | ~~M~~ | ~~Split `extract_model()` into focused functions (one per object type)~~ → **done 1.5.2** |
| C2 | ~~L~~ | ~~Move Java class name fragments to named constants~~ → **done 1.3.1** |
| C4 | ~~M~~ | ~~Backend table column widths are magic numbers duplicated between header and data row~~ → **done 1.3.1** |
| C3 | ~~L~~ | ~~Add basic unit tests for parser and model extraction~~ → **done 1.6.0** (also caught and fixed a real base64-decoding bug) |

---

## Project / Repo

| # | P | Item |
|---|---|------|
| P3 | ~~L~~ | ~~`oud_config_lint.py` — validator/linter for OUD proxy configs~~ → **done v1.0.0** — 9 rules across proxy + DS profiles, ERROR/WARNING/INFO severity, JSON output, CI-friendly exit code |

---

## Done

| # | Version | Item |
|---|---------|------|
| R1 | lint 1.1.0 | Review fix: exit code 2 + explicit message when zero rules run (was: false "clean" + exit 0) |
| R2 | lint 1.1.0 | Review fix: Finding.ref now shown in text report when it adds information |
| R3 | lint 1.1.0 | Review fix: P-ARCH-2 extended to disabled-but-reachable LB WEs |
| R4 | lint 1.1.0, report 1.1.1 | Review fix: unused `cn_of` imports removed |
| R5 | diagram 1.9.1, report 1.1.1 | Review fix: `⚠` (double-width glyph) → `!!` ASCII marker, width-safe |
| R6 | — | Review fix: CHANGELOG dates corrected to real work dates (1.6.0→07-08, 1.7-1.9→07-09, new tools→07-10) |
| R7 | — | Review fix: README stale example legend refreshed; lint exit-code table added |
| R8 | — | Review fix: orphan RELEASE_NOTES_backend_report_v1.0.0.md removed; retroactive notes for v1.9.0 and backend_report v1.1.0 added |
| R9 | — | Review fix: `check_changelog.py` guard added for the recurring lost-header bug (caught it 0 times on the new entry — first clean edit) |
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
| D17 | 1.5.0 | `oud_config_type.py` classifier tool (E1) |
| D18 | 1.5.0 | Early scope warning wired into oud_lb_diagram.py (B7) |
| D19 | 1.5.1 | Fixed silent B6 case: empty ds-cfg-workflow now warns explicitly |
| D20 | 1.5.2 | Split extract_model() into focused per-object extractors (C1) |
| D21 | 1.6.0 | Unit test suite (30 tests) added; caught & fixed real base64 parsing bug (C3) |
| D22 | 1.7.0 | `--anonymize` flag with deterministic IP masking (F3) |
| D23 | 1.8.0 | Extracted shared `oud_ldif_core.py`; oud_config_type.py migrated off oud_lb_diagram (E2) |
| D24 | 1.9.0 | Disabled WE/extension highlighting extended beyond LB WE (O3) |
| D25 | 1.9.0 | `--format json` output mode with stdout/stderr split (F4) |
| D26 | — | `oud_backend_report.py` v1.0.0 — companion tool for Directory Server configs (E3) |
| D27 | — | `oud_backend_report.py` v1.1.0 — added `--anonymize` (closed gap vs oud_lb_diagram.py); added public `config_ds_test.ldif` fixture |
| D28 | — | `oud_config_lint.py` v1.0.0 — validator/linter, 9 rules across both profiles (P3) |
