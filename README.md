# oud-tools

A command-line utility to parse Oracle Unified Directory (OUD) proxy configuration files and print a human-readable load-balancing architecture diagram.

---

## Scope

This tool targets **Oracle Unified Directory Proxy** (formerly Oracle Directory Server Enterprise Edition / Directory Proxy Server — "DPS") configurations specifically, identified by `com.sun.dps.server.workflowelement.*` Java classes (`ProxyLdapWorkflowElement`, `LoadBalancingWorkflowElement`, `LDAPServerExtension`).

It does **not** apply to a plain OUD Directory Server instance (one that stores data locally via a `db-local-backend-workflow-element` / JE backend rather than proxying to remote servers). Running it against such a config will produce an empty or near-empty diagram, since no proxy/LB workflow elements will be found.

| | OUD Directory Server | OUD Proxy |
|---|---|---|
| Data backend | Local (JE/DB) | None — routes to remote directories |
| Typical WE | `db-local-backend-workflow-element` | `proxy-ldap-workflow-element`, `load-balancing-workflow-element` |
| Java namespace | `org.opends.server.*` only | `org.opends.server.*` (shared base) + `com.sun.dps.server.workflowelement.*` |
| This tool | Not applicable | ✅ Supported |

---

## Requirements

- Python 3.6+
- No external dependencies (standard library only — `re`, `base64`, `collections`)

---

## Usage

```bash
python oud_lb_diagram.py <path-to-config.ldif>
python oud_lb_diagram.py --version                             # print version and exit
python oud_lb_diagram.py <config> --output <file>               # save diagram to file
python oud_lb_diagram.py <config> --no-tree                     # skip workflow tree(s), print only summary + backend table
python oud_lb_diagram.py <config> --output report.txt --no-tree  # combine both
```

If no argument is provided, the script looks for `config.ldif` in the current directory.

---

## What it does

The script reads the OUD proxy `config.ldif` file and:

1. **Parses all LDIF entries** — network groups, workflows, load-balancing workflow elements, proxy workflow elements, and backend extensions
2. **Builds the routing tree** dynamically, at any depth, without hardcoded assumptions on the architecture
3. **Prints a text diagram** showing:
   - The full workflow element hierarchy from entry point down to backend IPs
   - The load-balancing algorithm at each node (`PROPORTIONAL`, `FAILOVER`, `ROUND-ROBIN`)
   - Per-operation **weights** for proportional nodes (e.g. `add/modify/delete:1  search/bind:0`)
   - Per-operation **priorities** for failover nodes (e.g. `all:1` or `search/bind:1  add/modify:2`)
   - `switch-back: ON` flag where present
   - Backend IP, port, SSL port, SSL policy, connection pool size, credential mode
4. **Prints a backend servers table** summarising all proxy WEs and their resolved extensions
5. **Prints a legend** explaining the notation
6. **Adapts the diagram width** automatically to the longest line of content (with safety bounds), so the frame never looks cramped or needlessly wide
7. **Parses LDIF robustly** — handles RFC 4511 line folding (continuation lines), base64-encoded values, and case-insensitive DN references
8. **Warns on unresolved references** — flags any workflow-element or extension DN that cannot be resolved in the parsed config

---

## Example output

```
[+] Parsed 316 LDIF entries from: config_proxyoud_test.ldif
[+] Found: 2 network group(s)  1 workflow(s)  6 LB WE(s)  6 proxy WE(s)  6 backend extension(s)

╔═════════════════════════════════════════════════════════════════════════════════════════════════════════╗
║                                 OUD PROXY — LOAD BALANCING ARCHITECTURE                                 ║
╚═════════════════════════════════════════════════════════════════════════════════════════════════════════╝

┌─────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│  NETWORK GROUPS                                                                                         │
├─────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│  cn=network-group  priority:1  enabled:true  →  workflow:workflowLB  base-dn:dc=example,dc=com          │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│  WORKFLOW TREE  —  workflowLB  —  base-dn: dc=example,dc=com                                            │
├─────────────────────────────────────────────────────────────────────────────────────────────────────────┤
└─────────────────────────────────────────────────────────────────────────────────────────────────────────┘

  └─ LB_MS  [PROPORTIONAL]
     ├─ LB_MS_routeR  weights: search/bind/compare/extended:1  add/modify/delete/modifydn:0
     │  └─ LB-Slave  [PROPORTIONAL]
     │     ├─ LB-Slave_S1  weights: search/bind/add/modify/delete/compare/modifydn/extended:1
     │     │  └─ FO_S1  [FAILOVER  switch-back:ON]
     │     │     ├─ FO_S1_routeS3  prio: all:1
     │     │     │  └─ proxy-we5  →  198.51.100.21  port:389  SSL:1636  (always)  cred:use-client-identity
     │     │     ├─ FO_S1_routeS4  prio: all:2
     │     │     │  └─ proxy-we6  →  198.51.100.22  port:389  SSL:1636  (always)  cred:use-client-identity
     │     │     ├─ FO_S1_routeS1  prio: all:3
     │     │     │  └─ proxy-we3  →  198.51.100.11  port:389  SSL:1636  (always)  cred:use-client-identity
     │     │     └─ FO_S1_routeS2  prio: all:4
     │     │        └─ proxy-we4  →  198.51.100.12  port:389  SSL:1636  (always)  cred:use-client-identity
     │     └─ LB-Slave_S2  weights: search/bind/add/modify/delete/compare/modifydn/extended:1
     │        └─ FO_S2  [FAILOVER  switch-back:ON]
     │           ├─ FO_S2_routeS4  prio: all:1
     │           │  └─ proxy-we6  →  198.51.100.22  port:389  SSL:1636  (always)  cred:use-client-identity
     │           ├─ FO_S2_routeS3  prio: all:2
     │           │  └─ proxy-we5  →  198.51.100.21  port:389  SSL:1636  (always)  cred:use-client-identity
     │           ├─ FO_S2_routeS2  prio: all:3
     │           │  └─ proxy-we4  →  198.51.100.12  port:389  SSL:1636  (always)  cred:use-client-identity
     │           └─ FO_S2_routeS1  prio: all:4
     │              └─ proxy-we3  →  198.51.100.11  port:389  SSL:1636  (always)  cred:use-client-identity
     └─ LB_MS_routeW  weights: add/modify/delete/modifydn:1  search/bind/compare/extended:0
        └─ LB-Master  [PROPORTIONAL]
           └─ LB-Master_M  weights: search/bind/add/modify/delete/compare/modifydn/extended:1
              └─ FO_M  [FAILOVER  switch-back:ON]
                 ├─ FO_M_routeM2  prio: all:1
                 │  └─ proxy-we2  →  198.51.100.20  port:389  SSL:1636  (always)  cred:use-client-identity
                 └─ FO_M_routeM1  prio: all:2
                    └─ proxy-we1  →  198.51.100.10  port:389  SSL:1636  (always)  cred:use-client-identity

┌─────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│  BACKEND SERVERS                                                                                        │
├─────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│  Extension   WE              IP Address          Port    SSL     Policy    Pool     Cred-mode           │
│  proxy1      proxy-we1       198.51.100.10       389     1636    always    10000    use-client-identity │
│  proxy2      proxy-we2       198.51.100.20       389     1636    always    10000    use-client-identity │
│  proxy3      proxy-we3       198.51.100.11       389     1636    always    10000    use-client-identity │
│  proxy4      proxy-we4       198.51.100.12       389     1636    always    10000    use-client-identity │
│  proxy5      proxy-we5       198.51.100.21       389     1636    always    10000    use-client-identity │
│  proxy6      proxy-we6       198.51.100.22       389     1636    always    10000    use-client-identity │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│  LEGEND                                                                                                 │
├─────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│  PROPORTIONAL   Distributes traffic by weight per operation type.                                       │
│                 weights shown as  ops:value  —  e.g. add/modify/delete:1  search/bind:0                 │
│  FAILOVER       One active node at a time; lower [prio] = preferred.                                    │
│                 switch-back:ON = auto-restore to primary when it recovers.                              │
│  ROUND-ROBIN    Cycles through available routes in order.                                               │
│  └─ <node>      Leaf node = backend proxy WE resolved to IP:port.                                       │
│  cred-mode      How client credentials are forwarded to the backend.                                    │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

> Note: the diagram frame width above adapts automatically to the longest line in the loaded config (bounded between `MIN_W=60` and `MAX_W=200` columns) — your output may be narrower or wider depending on attribute lengths, DN depth, and IP formats.

If the config contains a network group without an associated workflow, or a workflow-element / extension reference that cannot be resolved, warnings are printed before the diagram:

```
[+] Parsed 316 LDIF entries from: config.ldif
[WARN] network-group "Network Group" references unknown workflow: 
[WARN] proxy-we "proxy-we7" references unknown extension: cn=proxy7,cn=extensions,cn=config
[+] Found: 2 network group(s)  1 workflow(s)  6 LB WE(s)  7 proxy WE(s)  6 backend extension(s)
```

---

## How to read the diagram

| Notation | Meaning |
|---|---|
| `[PROPORTIONAL]` | Traffic distributed by weight across routes |
| `[FAILOVER  switch-back:ON]` | One active node at a time; lower prio = preferred; auto-restore to primary |
| `weights: add/modify:1  search:0` | Operations with weight > 0 are routed here; 0 = blocked |
| `prio: all:1` | All operation types have the same priority on this route |
| `prio: search/bind:1  add/modify:2` | Per-operation priorities differ (route preferred for reads, backup for writes) |
| `→  x.x.x.151  port:389  SSL:1636` | Resolved backend IP and ports |
| `cred:use-client-identity` | Client credentials passed through as-is to the backend |

---

## Architecture notes

The script makes **no assumptions** about the number of levels, branch names, or routing semantics. It explores the tree generically and reports what is in the config. Semantic interpretation (e.g. which branch is WRITE vs READ) is left to the reader and can be inferred from the weights.

Supported load-balancing algorithm types:
- `PROPORTIONAL` — weight-based distribution per operation
- `FAILOVER` — single active node with priority-based fallback
- `ROUND-ROBIN` — sequential cycling (if present in config)

### Parser

The LDIF parser is RFC 4511 compliant:
- Continuation lines (starting with a single space) are folded into the previous logical line
- Base64-encoded values (`attr:: <b64>`) are decoded to UTF-8, with hex fallback for binary content
- URL references (`attr:< <url>`) are recognised and stored as-is
- All DNs (entry keys and cross-references) are normalised to lowercase for consistent lookup, regardless of the original casing in the config; display labels still use the original-case `cn` attribute value

---

## Limitations

- Only parses `LDAPServerExtension` backends (OUD proxy mode)
- Local backends (JE/DB), replication domains, virtual ACIs and other config objects are ignored
- Tested on OUD 11g/12c proxy config format

---

## Versioning

This project follows [Semantic Versioning](https://semver.org/). See [CHANGELOG.md](./CHANGELOG.md) for the full version history.

Check the installed version with:

```bash
python oud_lb_diagram.py --version
```

---

## Files

| File | Description |
|---|---|
| `oud_lb_diagram.py` | Main script |
| `README.md` | This file |
| `CHANGELOG.md` | Version history |
