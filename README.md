# oud-tools

A command-line utility to parse Oracle Unified Directory (OUD) proxy configuration files and print a human-readable load-balancing architecture diagram.

---

## Requirements

- Python 3.6+
- No external dependencies (standard library only)

---

## Usage

```bash
python oud_lb_diagram.py <path-to-config.ldif>
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

---

## Example output

```
╔══════════════════════════════════════════════════════════════════════════════════════════╗
║                      OUD PROXY — LOAD BALANCING ARCHITECTURE                            ║
╚══════════════════════════════════════════════════════════════════════════════════════════╝

┌──────────────────────────────────────────────────────────────────────────────────────────┐
│  NETWORK GROUPS                                                                          │
├──────────────────────────────────────────────────────────────────────────────────────────┤
│  cn=network-group  priority:1  enabled:true  →  workflow:workflowLB  base-dn:dc=example,dc=com │
└──────────────────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────────────────┐
│  WORKFLOW TREE  —  workflowLB  —  base-dn: dc=example,dc=com                            │
└──────────────────────────────────────────────────────────────────────────────────────────┘

  └─ LB_MS  [PROPORTIONAL]
     ├─ LB_MS_routeR  weights: search/bind/compare/extended:1  add/modify/delete/modifydn:0
     │  └─ LB-Slave  [PROPORTIONAL]
     │     ├─ LB-Slave_S1  weights: search/bind/add/modify/delete/compare/modifydn/extended:1
     │     │  └─ FO_S1  [FAILOVER  switch-back:ON]
     │     │     ├─ FO_S1_routeS3  prio: all:1
     │     │     │  └─ proxy-we5  →  x.x.x.151  port:389  SSL:1636  (always)  cred:use-client-identity
     │     │     ├─ FO_S1_routeS4  prio: all:2
     │     │     │  └─ proxy-we6  →  x.x.x.152  port:389  SSL:1636  (always)  cred:use-client-identity
     │     │     ├─ FO_S1_routeS1  prio: all:3
     │     │     │  └─ proxy-we3  →  x.x.x.231  port:389  SSL:1636  (always)  cred:use-client-identity
     │     │     └─ FO_S1_routeS2  prio: all:4
     │     │        └─ proxy-we4  →  x.x.x.232  port:389  SSL:1636  (always)  cred:use-client-identity
     │     └─ LB-Slave_S2  weights: search/bind/add/modify/delete/compare/modifydn/extended:1
     │        └─ FO_S2  [FAILOVER  switch-back:ON]
     │           ├─ FO_S2_routeS4  prio: all:1
     │           │  └─ proxy-we6  →  x.x.x.152  port:389  SSL:1636  (always)  cred:use-client-identity
     │           └─ ...
     └─ LB_MS_routeW  weights: add/modify/delete/modifydn:1  search/bind/compare/extended:0
        └─ LB-Master  [PROPORTIONAL]
           └─ LB-Master_M  weights: all:1
              └─ FO_M  [FAILOVER  switch-back:ON]
                 ├─ FO_M_routeM2  prio: all:1
                 │  └─ proxy-we2  →  x.x.x.150  port:389  SSL:1636  (always)  cred:use-client-identity
                 └─ FO_M_routeM1  prio: all:2
                    └─ proxy-we1  →  x.x.x.230  port:389  SSL:1636  (always)  cred:use-client-identity
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

---

## Limitations

- Only parses `LDAPServerExtension` backends (OUD proxy mode)
- Local backends (JE/DB), replication domains, virtual ACIs and other config objects are ignored
- Tested on OUD 11g/12c proxy config format

---

## Files

| File | Description |
|---|---|
| `oud_lb_diagram.py` | Main script |
| `README.md` | This file |
