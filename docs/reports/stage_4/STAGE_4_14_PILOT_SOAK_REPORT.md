# SRI LEKH — STAGE 4.14 SEVEN-DAY PILOT SOAK & COHORT MONITORING REPORT

**Environment:** `neondb_staging` + `https://vouch-u3u7.onrender.com`  
**Commit SHA:** `990a13bd` (`fix/stage4-12-day6-remediation`)  
**Database Fingerprint:** `6f4741bdaaf4` (`ep-silent-feather-b34egg28-pooler.c-4.ap-southeast-1.aws.neon.tech`, `is_isolated=True`, `Maa Annapurna Belting Store` absent)  
**Execution Timestamp:** `2026-11-12 13:55 IST` (`task-50261`)

---

## Executive Soak Status: **DAY 6/7 POINT-IN-TIME ACCOUNTING STATE `PASS` — 7-DAY CONTINUOUS LIVE WORKER SOAK `BLOCKED ON WORKER/REDIS`**

All 5 canonical synthetic pilot tenants show clean accounting equilibrium, zero ledger drift, zero outbox backlog, zero duplicate notifications, zero broken audit hash chains, and healthy API latencies (~212–359ms warm on Render). However, continuous multi-day worker monitoring requires provisioning live Redis + Celery Worker/Beat services on Render.

---

## 1. Live Operational Telemetry (`neondb_staging` & Render)

| Monitoring Dimension | Observed Metric | Verdict |
|---|---|---|
| API Error Rate (Stage 4.14 Live Audit) | `0` unexpected 5xx across health, auth, reports, sandbox writes, and IDOR checks | **PASS** |
| Live Render Warm Latency (`990a13bd`) | `/api/health/` `212.6ms`; `/api/v1/health/environment/` `358.4ms`; Agro Aging `246.5–260.7ms` | **PASS** *(Free-tier idle cold wake ~44s)* |
| Database Connection Usage (`pg_stat_activity`) | `1` active connection during snapshot check | **PASS** |
| Live Celery Worker Availability | `workers_online: 0`, `redis.status: "unreachable"`, `beat_schedule_active: false` | **FAIL (Action Required)** |
| Global Outbox Backlog | **`0` `PENDING`** | **PASS** |
| Dead-Letter Outbox Events | `9` historical Precision Agro pilot test rows (unchanged since Stage 4.12) | **PASS (Accounted)** |
| Duplicate Notifications | `0` (`outbox PROCESSED == EmailDeliveryLog SENT` across all 5 tenants) | **PASS** |
| Posted Equilibrium / Orphans | `0` unbalanced posted, `0` zero-entry posted, `0` orphan entries | **PASS** |
| FIFO Allocations | `0` negative/zero allocations | **PASS** |

---

## 2. Five-Tenant Synthetic Pilot Cohort Census (`auto_reconcile=False`)

| Metric | Garodia Bearing | Precision Agro Tools | Shree Radhe Hardware | Beta Engineering | Alpha Belts |
|---|---:|---:|---:|---:|---:|
| **Company UUID Prefix** | `cd788d07` | `c2771ca4` | `ce9c6000` | `434af258` | `75a4b5e7` |
| **Vouchers (`POSTED / DRAFT / REV`)** | `62 / 1 / 0` | `523 / 11 / 0` | `60 / 0 / 0` | `42 / 0 / 4` | `444 / 92 / 7` |
| **Trial Balance `Dr == Cr` (Rs)** | `678,241.20` | `1,694,738.70` | `505,813.79` | `287,835.00` | `831,328.66` |
| **`TB == Period TB`** | `True` | `True` | `True` | `True` | `True` |
| **Ledger Drift Discrepancies** | **`0`** | **`0`** | **`0`** | **`0`** | **`0`** |
| **Balance Sheet Balanced (`Assets`, Rs)** | `True` (`849,310.20`) | `True` (`1,845,954.26`) | `True` (`672,482.00`) | `True` (`417,193.00`) | `True` (`947,429.66`) |
| **P&L Net Profit (Rs)** | `163,014.80` | `1,116,043.40` | `158,006.35` | `81,775.73` | `587,016.50` |
| **Receivables / Payables Outst. (Rs)** | `332,339.0 / 3,540.0` | `1,331,995.1 / 4,725.74` | `314,131.0 / 4,838.0` | `275,835.0 / 12,000.0` | `690,149.0 / 42,102.0` |
| **Output CGST == SGST Cache (Rs)** | `20,551.74` | `100,802.67` | `19,772.54` | `19,808.86` | `15,543.76` |
| **Raw `qty * purchase_price` (Rs)** | `84,369.00` | `-207,216.82`* | `105,869.00` | `118,748.00` | `216,002.00` |
| **Inventory / Sync Events** | `90 / 1,082` | `515 / 8,144` | `87 / 1,035` | `60 / 734` | `86 / 4,203` |
| **Outbox (`PROC / SKIP / DL`)** | `55 / 1 / 0` | `82 / 391 / 9` | `54 / 0 / 0` | `36 / 0 / 0` | `376 / 5 / 0` |
| **Email Logs (`SENT / SKIP`)** | `55 / 1` | `82 / 391` | `54 / 0` | `36 / 0` | `376 / 5` |
| **`AuditLog` Count / Hash Breaks** | `73 / 0` | `559 / 0` | `68 / 0` | `52 / 0` | `468 / 0` |
| **Full Suite Latency (All 6 Reports, ms)** | `2,224.3` | `2,289.6` | `2,281.3` | `2,222.6` | `2,307.8` |

*\*Note on Precision Agro raw inventory valuation: High-volume Stage 4.9/4.11 stress-test sales oversold SKUs below zero quantity (`-207,216.82` raw cost sum), while `FinancialStatementsService` clamps negative per-SKU quantities to `0.00` for Balance Sheet stock valuation.*

---

## Remaining Limitations

1. Live Celery worker & Beat execution cannot be monitored over a 7-day soak on Render until Redis and paid Worker/Beat instances are provisioned.
2. Free-tier Render web dyno sleeps after inactivity (~44s cold wake), which triggers client timeouts if requests are not cold-wake tolerant or upgraded to an always-on plan.
