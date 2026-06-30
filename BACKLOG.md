# Backlog — oud-tools

Priority: H=High / M=Medium / L=Low

---

## Bug / Robustness

| # | P | Item |
|---|---|------|
| B1 | H | LDIF line continuation (lines starting with space per RFC 4511) |
| B2 | H | base64 values (`attr:: dmFsdWU=`) silently ignored |
| B3 | M | DN comparison is case-sensitive in places — normalise to lower consistently |
| B4 | M | Warn if `ds-cfg-workflow-element` points to an unresolved DN |
| B5 | M | DN collision if two WEs share the same CN on different branches |
| B6 | L | Network group without workflow shows `base-dn:?` — add explicit warning |

---

## Output

| # | P | Item |
|---|---|------|
| O1 | M | Deep tree branches can exceed `MAX_W` — account for indentation in width calc |
| O2 | M | Workflow tree body unframed — consider consistent boxing with other sections |
| O3 | L | Highlight disabled WEs (`ds-cfg-enabled: false`) more visibly (e.g. `[DISABLED]` in red or `!!`) |

---

## Features

| # | P | Item |
|---|---|------|
| F1 | M | `--output <file>` flag to save diagram to disk |
| F2 | M | `--no-tree` flag to print only backend table (quick summary mode) |
| F3 | L | `--anonymize` flag to mask IPs in output |
| F4 | L | JSON/YAML output mode for machine-readable consumption |

---

## Code Quality

| # | P | Item |
|---|---|------|
| C1 | M | Split `extract_model()` into focused functions (one per object type) |
| C2 | L | Move Java class name fragments to named constants |
| C3 | L | Add basic unit tests for parser and model extraction |

---

## Done

| # | Version | Item |
|---|---------|------|
| D1 | 1.0.0 | Generic tree exploration (any depth, no hardcoded structure) |
| D2 | 1.0.0 | Per-operation weights and priorities |
| D3 | 1.0.0 | Backend servers summary table |
| D4 | 1.1.0 | Dynamic diagram width (MIN_W / MAX_W) |
| D5 | 1.1.0 | `--version` flag |
