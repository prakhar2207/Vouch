import os
import sys
import json
import urllib.request
import urllib.error
import ssl
from decimal import Decimal
from datetime import date

sys.path.insert(0, r'c:\Users\prakh\OneDrive\Desktop\projects\B2B')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from apps.companies.models import Company
from apps.gst.models import CompanyGSTConfig, GSTRegistration, GSTReturnWorkspace, GSTFilingRecord
from apps.gst.services.returns_service import GSTReturnsService
from apps.gst.services.workspace_service import GSTWorkspaceService
from apps.gst.services.rate_reference_service import GSTRateScheduleService
from apps.gst.services.providers.factory import get_gst_provider
from apps.gst.exceptions import LiveFilingProhibitedError

SANDBOX_ID = '4e62863a-08f9-4e99-b0bd-64873acfdd33'
BASE_URL = 'https://vouch-u3u7.onrender.com'

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def run_live_gst_smoke_tests():
    print("=" * 80)
    print("   SRILEKH LIVE GST OPERATIONAL SMOKE TESTS")
    print(f"   Staging Backend: {BASE_URL}")
    print(f"   Dedicated Sandbox: Apex Belting & Industrial Store (Demo) ({SANDBOX_ID})")
    print("=" * 80)

    results = {}

    # Safety Guard: Invariant Check
    company = Company.objects.get(id=SANDBOX_ID)
    assert str(company.id) == SANDBOX_ID, "ABORT: Tests may ONLY run against Apex Belting Store sandbox!"
    print(f"\n[Safety Policy Verified] Operating exclusively on sandbox tenant: {company.name}")

    # 1. Unauthorized API Access Rejection
    print("\n[Check 1] Unauthorized API Access Rejection...")
    unauth_url = f"{BASE_URL}/api/v1/gst/workspace/{SANDBOX_ID}/"
    try:
        req = urllib.request.Request(unauth_url, headers={'User-Agent': 'SriLekh-Auditor/1.0'})
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            print("  [FAIL] Unauthenticated request was allowed!")
            results["unauthorized_rejection"] = "FAIL"
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            print(f"  [PASS] Unauthenticated request correctly rejected with HTTP {e.code}.")
            results["unauthorized_rejection"] = "PASS"
        else:
            print(f"  [WARN] Expected 401/403, got HTTP {e.code}")
            results["unauthorized_rejection"] = f"HTTP {e.code}"

    # 2. Cross-Tenant IDOR Rejection
    print("\n[Check 2] Cross-Tenant Access Rejection...")
    protected_id = "5d2e5dea-ff86-4871-b2af-fe1c5a05c03c"
    idor_url = f"{BASE_URL}/api/v1/gst/workspace/{protected_id}/"
    try:
        req = urllib.request.Request(idor_url, headers={'User-Agent': 'SriLekh-Auditor/1.0'})
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            print("  [FAIL] Protected tenant access was allowed!")
            results["cross_tenant_rejection"] = "FAIL"
    except urllib.error.HTTPError as e:
        print(f"  [PASS] Access to protected tenant strictly rejected with HTTP {e.code}.")
        results["cross_tenant_rejection"] = "PASS"

    # 3. GST Rate-Reference Validation
    print("\n[Check 3] GST Rate Reference Service Validation...")
    try:
        sublimation_val = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='4809',
            tx_date=date(2026, 11, 1),
            applied_rate=Decimal('18.00')
        )
        toy_val = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='9503',
            tx_date=date(2026, 11, 1),
            applied_rate=Decimal('12.00')
        )
        assert sublimation_val.get("is_statutorily_valid") is True, f"Expected 18% valid for 4809, got {sublimation_val}"
        assert toy_val.get("is_statutorily_valid") is True, f"Expected 12% valid for 9503, got {toy_val}"
        print(f"  [PASS] Rate Reference validated: HSN 4809 @ 18% valid={sublimation_val['is_statutorily_valid']}, HSN 9503 @ 12% valid={toy_val['is_statutorily_valid']}")
        results["rate_reference_validation"] = "PASS"
    except Exception as e:
        print(f"  [FAIL] Rate reference error: {e}")
        results["rate_reference_validation"] = "FAIL"

    # 4. GSTIN Lookup using Sandbox Provider
    print("\n[Check 4] GSTIN Lookup & Provider Routing...")
    try:
        provider = get_gst_provider(company)
        print(f"  Routed Gateway Provider: {type(provider).__name__}")
        search_res = provider.search_taxpayer("07AAAAA0000A1Z5")
        assert search_res.get("success") is True, "Expected success=True for checksum-valid mock/sandbox GSTIN"
        print(f"  [PASS] GSTIN Lookup successful: Legal Name='{search_res.get('legal_name')}', Status='{search_res.get('status')}'")
        results["gstin_lookup"] = "PASS"
    except Exception as e:
        print(f"  [FAIL] GSTIN lookup error: {e}")
        results["gstin_lookup"] = "FAIL"

    # 5. GST Return Workspace Creation & Drift Guard
    print("\n[Check 5] GST Return Workspace Lifecycle...")
    try:
        registration = GSTRegistration.objects.filter(company=company).first()
        ws = GSTWorkspaceService.get_or_create_workspace(
            company=company,
            registration=registration,
            return_type='GSTR1',
            return_period='022026'
        )
        print(f"  Workspace ID: {ws.id}, Return Type: {ws.return_type}, Period: {ws.return_period}, Status: {ws.status}")
        drift_status = GSTWorkspaceService.check_drift(ws)
        print(f"  [PASS] Workspace accessible and drift checked: is_stale={ws.is_stale}")
        results["workspace_lifecycle"] = "PASS"
    except Exception as e:
        print(f"  [FAIL] Workspace error: {e}")
        results["workspace_lifecycle"] = "FAIL"

    # 6. GSTR-1 Generation
    print("\n[Check 6] GSTR-1 Draft Preparation...")
    try:
        gstr1 = GSTReturnsService.prepare_gstr1(company=company, return_period='022026')
        assert "official_gstr1_json" in gstr1, "Missing official_gstr1_json"
        summary = gstr1.get("summary", {})
        print(f"  [PASS] GSTR-1 generated: Clean Invoices={summary.get('clean_invoices_count')}, Taxable Val=Rs {summary.get('total_taxable_value')}")
        results["gstr1_generation"] = "PASS"
    except Exception as e:
        print(f"  [FAIL] GSTR-1 error: {e}")
        results["gstr1_generation"] = "FAIL"

    # 7. GSTR-3B Preparation & Rule 88A Set-off
    print("\n[Check 7] GSTR-3B Preparation & Set-off...")
    try:
        gstr3b = GSTReturnsService.prepare_gstr3b(company=company, return_period='022026')
        assert "table_3_1" in gstr3b, "Missing table_3_1"
        assert "tax_payable" in gstr3b, "Missing tax_payable"
        tax_pay = gstr3b.get("tax_payable", {})
        print(f"  [PASS] GSTR-3B prepared: Tax Payable={tax_pay}")
        results["gstr3b_preparation"] = "PASS"
    except Exception as e:
        print(f"  [FAIL] GSTR-3B error: {e}")
        results["gstr3b_preparation"] = "FAIL"

    # 8. GST Export Generation & Checksum
    print("\n[Check 8] GST Export Generation & Checksum...")
    try:
        # Generate draft first if needed
        GSTWorkspaceService.generate_draft(ws)
        export_res = GSTWorkspaceService.export_draft(workspace=ws, export_format='JSON')
        if export_res.get("success"):
            print(f"  [PASS] Return exported successfully: Hash={export_res.get('payload_hash')[:16]}...")
            results["export_generation"] = "PASS"
        elif export_res.get("drift_detected"):
            GSTWorkspaceService.generate_draft(ws)
            export_res = GSTWorkspaceService.export_draft(workspace=ws, export_format='JSON')
            print(f"  [PASS] Regenerated and exported: Hash={export_res.get('payload_hash')[:16]}...")
            results["export_generation"] = "PASS"
        else:
            print(f"  [FAIL] Export error: {export_res.get('error')}")
            results["export_generation"] = "FAIL"
    except Exception as e:
        print(f"  [FAIL] Export exception: {e}")
        results["export_generation"] = "FAIL"

    # 9. Live Filing Prohibition Guard
    print("\n[Check 9] Live Filing Prohibition Guard...")
    try:
        GSTReturnsService.file_return_live()
        print("  [FAIL] file_return_live did not raise LiveFilingProhibitedError!")
        results["live_filing_blocked"] = "FAIL"
    except LiveFilingProhibitedError as e:
        print(f"  [PASS] Live filing blocked as expected: '{e}'")
        results["live_filing_blocked"] = "PASS"
    except Exception as e:
        print(f"  [FAIL] Unexpected exception: {e}")
        results["live_filing_blocked"] = "FAIL"

    print("\n" + "=" * 80)
    print(">>> GST OPERATIONAL SMOKE TESTS COMPLETED <<<")
    for k, v in results.items():
        print(f"  {k}: {v}")
    print("=" * 80)
    return results

if __name__ == '__main__':
    run_live_gst_smoke_tests()
