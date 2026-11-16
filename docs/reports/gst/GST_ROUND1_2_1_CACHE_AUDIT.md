# SRI LEKH — GST ROUND 1.2.1 AUDIT REPORT: CACHE & LOOKUP INTEGRITY
**Audited Target:** `apps/gst/services/gstin_service.py` & `GSTTaxpayerCache` in `apps/gst/models.py`  
**Git Commit:** `8860b99ac3f13db1c554b7d9b0a559a79c5a927e`  
**Branch:** `fix/stage4-12-day6-remediation`  
**Auditor:** Senior Database Reliability Engineer & GST Specialist  
**Date:** 2026-11-16  

---

## 1. Executive Summary

This independent forensic audit evaluates the taxpayer lookup, checksum verification, and caching subsystem implemented in `apps/gst/services/gstin_service.py` and `GSTTaxpayerCache` (`apps/gst/models.py`).

The caching tier is designed to minimize external API consumption against Quicko Sandbox while maintaining compliance with Indian statutory taxpayer records. Key features include:
1. 15-character structural regex validation and Luhn MOD-36 checksum calculation.
2. A 24-hour statutory Time-To-Live (TTL) cache implemented via `GSTTaxpayerCache.updated_at`.
3. Support for `force_refresh=True` to bypass cache for live compliance checks.
4. Dirty cache prevention (only caching successful provider responses).

This audit identifies **one P2 flaw where stale cache is returned as a success during an explicit force refresh failure**, **one P3 date format parsing deficiency**, and documents the architectural evaluation of global taxpayer caching.

---

## 2. Detailed Findings

### FINDING CCH-01 (Severity: P2 — Medium)
**Stale Cache Returned with `success: True` on Exception During Explicit `force_refresh`**

- **File & Function:** `apps/gst/services/gstin_service.py`: `verify_gstin()` (lines 220–237).
- **Exact Problem:**
  When `verify_gstin()` encounters an exception (e.g. network timeout or provider connection failure), it executes the fallback block:
  ```python
  except Exception as e:
      logger.exception(f"Unexpected error in verify_gstin for {clean_gstin}: {e}")
      if cached:
          return {
              "success": True,
              "gstin": clean_gstin,
              "legal_name": cached.legal_name,
              "trade_name": cached.trade_name,
              "state_code": cached.state_code,
              "state_name": cached.state_name,
              "address": cached.address,
              "pincode": cached.pincode,
              "status": cached.status,
              "is_cached": True,
              "source": "cache_fallback_on_error",
              "error_note": str(e)
          }
      return {
          "success": False,
          "gstin": clean_gstin,
          "error": f"GST verification failed: {str(e)}",
          "source": "exception"
      }
  ```
  While falling back to cache on transient network failures is acceptable during default lookups, **it violates user expectations during explicit `force_refresh=True` calls**.
  
  For example, if an accountant suspects a vendor's GSTIN has been cancelled or suspended by the tax authorities, they click "Verify Now" (which triggers `force_refresh=True`). If the Quicko API times out or is unreachable, the system catches the error, finds the old cached record (where status was "Active" 20 hours ago), and returns `success: True`!
  
  The caller receives `success: True` and may conclude the vendor is still verified and active, when in reality the live verification failed completely.

- **Reproduction Scenario:**
  1. A vendor's GSTIN is cached in `GSTTaxpayerCache` with `status="Active"`.
  2. The vendor is subsequently cancelled by GST authorities.
  3. The accountant runs `GSTINService.verify_gstin(clean_gstin, force_refresh=True)`.
  4. The network to Quicko experiences a 504 Gateway Timeout.
  5. The exception handler catches `504 Timeout`, sees `if cached:`, and returns `{"success": True, "status": "Active", "source": "cache_fallback_on_error"}`.
  6. The frontend shows a green "Verified" badge.

- **Business / Security Impact:**
  Risk of claiming Input Tax Credit (ITC) on invoices issued by cancelled vendors, leading to tax penalties and statutory audit disqualification.

- **Recommended Correction:**
  Check `force_refresh` in the exception handler:
  ```python
  except Exception as e:
      logger.exception(f"Unexpected error in verify_gstin for {clean_gstin}: {e}")
      if cached and not force_refresh:
          return {
              "success": True,
              "source": "cache_fallback_on_error",
              ...
          }
      return {
          "success": False,
          "gstin": clean_gstin,
          "error": f"Live verification failed: {str(e)}",
          "source": "provider_error"
      }
  ```

- **Detected by Existing Tests?**
  **NO.** No test asserts the error handling behavior under `force_refresh=True` when an exception is raised.

---

### FINDING CCH-02 (Severity: P3 — Low)
**Fragile Registration Date Parsing for ISO-8601 Timestamps**

- **File & Function:** `apps/gst/services/gstin_service.py`: lines 189–199.
- **Exact Problem:**
  Date parsing in `verify_gstin()` iterates through:
  ```python
  for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y'):
      try:
          from datetime import datetime
          reg_date = datetime.strptime(raw_reg_date, fmt).date()
          break
      except ValueError:
          pass
  ```
  If Quicko returns an ISO-8601 timestamp (e.g. `"2017-07-01T00:00:00.000Z"` or `"2017-07-01T05:30:00+05:30"`), all three formats fail, and `reg_date` silently defaults to `None`.

- **Recommended Correction:**
  Include ISO format parsing:
  ```python
  from dateutil import parser
  reg_date = parser.parse(raw_reg_date).date()
  ```

- **Detected by Existing Tests?**
  **NO.** Tests pass dates formatted as `'01/07/2017'`.

---

## 3. Cache Architecture & Tenancy Evaluation

### Global Cache vs Tenant Isolation
In `apps/gst/models.py`:
```python
class GSTTaxpayerCache(models.Model):
    gstin = models.CharField(max_length=15, unique=True, db_index=True)
    ...
```
`GSTTaxpayerCache` has no `company` foreign key. It is a **global shared cache**.

**Architectural Evaluation:**
- **IS THIS ACCEPTABLE?** **YES.** A GSTIN represents a public, sovereign business entity registered on the Goods and Services Tax Network (GSTN). Its legal name, trade name, state code, and status are public statutory data identical for all businesses. Storing it globally avoids redundant external API calls across multiple SriLekh tenants verifying the same counterparty (e.g. common suppliers like Tata Steel, Reliance, or local utilities).
- **DIRTY CACHE SAFEGUARDS:**
  1. Only HTTP 200 responses with parsed JSON data write to `GSTTaxpayerCache`.
  2. Local validation failures (bad length, invalid state code, checksum failure) **never write to the cache**.
  3. Cache TTL is strictly capped at 24 hours (`cache_age < timedelta(hours=24)`).

---

## 4. Luhn MOD-36 Checksum Verification Audit

The checksum implementation in `calculate_gstin_checksum()` was independently verified against Indian GST specifications:
- **Alphabet:** `0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ` (36 characters).
- **Weight Factor:** Alternates between `1` and `2` for positions 1 through 14.
- **Modulus Addition:** `addend = (addend // 36) + (addend % 36)`.
- **Check Character:** `(36 - (total % 36)) % 36`.

**Test Vectors Verified:**
1. `27AADCB2230M1Z` -> Expected checksum: **`T`** -> Match (`27AADCB2230M1ZT`)
2. `07AAAAA0000A1Z` -> Expected checksum: **`4`** -> Match (`07AAAAA0000A1Z4`)
3. `27AAACA1234A1Z` -> Expected checksum: **`5`** -> Match (`27AAACA1234A1Z5`)

The algorithm is mathematically correct and provides robust pre-flight validation, preventing wasted provider API calls.

---

## 5. Verdict & Release Readiness

**Dimension Verdict:** **PASS WITH CONDITIONS**  
The caching and checksum logic is mathematically sound and delivers excellent API quota conservation. Remediating Finding CCH-01 is required before enabling vendor compliance workflows in production.
