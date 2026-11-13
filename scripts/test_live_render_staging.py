import sys
import time
import json
import urllib.request
import urllib.error
import ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


def _http_get_with_cold_wake(url, timeout=90, retries=2):
    last_err = None
    for attempt in range(retries + 1):
        t0 = time.perf_counter()
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'SriLekh-Auditor/1.0'})
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                elapsed = round((time.perf_counter() - t0) * 1000, 1)
                return resp.status, resp.read().decode('utf-8'), elapsed
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(2)
    raise last_err


def test_live_staging(base_url, timeout=90, expected_commit=None, check_cors=True):
    base_url = base_url.rstrip('/')
    print("=" * 80)
    print(f"   LIVE RENDER STAGING VERIFICATION: {base_url}")
    print(f"   Timeout per probe: {timeout} seconds (with cold-wake retry)")
    print("=" * 80)

    # 1. Environment & Database Isolation Health
    env_url = f"{base_url}/api/v1/health/environment/"
    print(f"\n[Probe 1] Checking Environment Identity at {env_url}...")
    try:
        status_code, raw_body, elapsed_ms = _http_get_with_cold_wake(env_url, timeout=timeout, retries=2)
        data = json.loads(raw_body)
        print("  Response:", json.dumps(data, indent=2))
        assert status_code == 200, f"Expected 200, got {status_code}"
        assert data.get('status') == 'healthy', f"Expected status 'healthy', got {data.get('status')}"

        db_info = data.get('database', {})
        db_target = db_info.get('sanitized_target')
        assert db_target == 'neondb_staging', f"CRITICAL SECURITY DEFECT: Expected target 'neondb_staging', got '{db_target}'"
        assert db_info.get('is_isolated') is True, "CRITICAL SECURITY DEFECT: Database isolation guard reported is_isolated=False!"
        assert db_info.get('engine') == 'postgresql', f"Expected PostgreSQL engine, got {db_info.get('engine')}"

        mig_info = data.get('migrations', {})
        assert mig_info.get('status') == 'up_to_date', f"Unapplied migrations detected: {mig_info}"
        assert mig_info.get('unapplied_count') == 0, f"Non-zero unapplied migrations: {mig_info}"

        commit_sha = data.get('commit', '')
        if expected_commit:
            assert commit_sha.startswith(expected_commit[:8]), (
                f"Commit mismatch: expected prefix '{expected_commit[:8]}', got '{commit_sha}'"
            )

        print(f"  Live Deployed Commit: {commit_sha} (elapsed: {elapsed_ms}ms)")
        print(f"  Live Database Target: {db_target} (Isolated: {db_info.get('is_isolated')}, Fingerprint: {db_info.get('identity_fingerprint')})")
        print(f"  Live Environment Setting: {data.get('environment')}")
        print("  [PASSED] Staging environment identity, database target, and isolation guard verified live.")
    except urllib.error.HTTPError as e:
        print(f"  [FAILED] HTTP {e.code}: {e.read().decode('utf-8', errors='ignore')}")
        return False
    except Exception as e:
        print(f"  [FAILED] Connection error: {e}")
        return False

    # 2. General Health Endpoint
    health_url = f"{base_url}/api/health/"
    print(f"\n[Probe 2] Checking General Health at {health_url}...")
    try:
        st, body, h_ms = _http_get_with_cold_wake(health_url, timeout=timeout, retries=1)
        data = json.loads(body)
        print("  Response:", json.dumps(data, indent=2))
        print(f"  [PASSED] Health endpoint returned HTTP {st} in {h_ms}ms")
    except Exception as e:
        print(f"  [FAILED] Health endpoint error: {e}")
        return False

    # 2b. CORS Preflight Verification for Vercel Frontend
    if check_cors:
        cors_url = f"{base_url}/api/v1/accounting/vouchers/"
        print(f"\n[Probe 2b] Checking CORS Preflight for https://vouch-pi-one.vercel.app at {cors_url}...")
        try:
            req = urllib.request.Request(
                cors_url,
                method='OPTIONS',
                headers={
                    'Origin': 'https://vouch-pi-one.vercel.app',
                    'Access-Control-Request-Method': 'POST',
                    'Access-Control-Request-Headers': 'authorization,content-type,x-idempotency-key',
                    'User-Agent': 'SriLekh-Auditor/1.0',
                },
            )
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                acao = resp.headers.get('Access-Control-Allow-Origin')
                assert resp.status == 200, f"Unexpected CORS preflight status: {resp.status}"
                assert acao == 'https://vouch-pi-one.vercel.app', f"Unexpected ACAO header: {acao}"
                print(f"  [PASSED] CORS preflight verified: ACAO={acao}")
        except Exception as e:
            print(f"  [FAILED] CORS preflight error: {e}")
            return False

    # 3. Live Password Login (Staging DB Verification)
    login_url = f"{base_url}/api/v1/auth/login/"
    print(f"\n[Probe 3] Testing Live Password Login at {login_url}...")
    token = None
    try:
        payload = json.dumps({"email": "owner_msme-plt-01@staging.srilekh.internal", "password": "PilotSecurePass123!"}).encode('utf-8')
        req = urllib.request.Request(
            login_url,
            data=payload,
            headers={'Content-Type': 'application/json', 'User-Agent': 'SriLekh-Auditor/1.0'}
        )
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            print(f"  Status: HTTP {resp.status}")
            assert resp.status == 200, f"Login failed with {resp.status}"
            assert "access" in data, "JWT access token missing!"
            token = data["access"]
            print(f"  User: {data.get('user', {}).get('email')}")
            print(f"  Role: {data.get('user', {}).get('role')}")
            print("  [PASSED] Live authentication against staging DB successful. JWT issued.")
    except urllib.error.HTTPError as e:
        print(f"  [FAILED] HTTP {e.code}: {e.read().decode('utf-8', errors='ignore')}")
        return False
    except Exception as e:
        print(f"  [FAILED] Login probe error: {e}")
        return False

    # 4. Live Tenant Ledger & Financial Statements Verification
    print(f"\n[Probe 4] Checking Live Tenant Accounting & IDOR Guard...")
    try:
        pilot_cid = "c2771ca4-31bd-47d2-b98c-c1be119f40a1"  # Precision Agro Tools Pvt Ltd
        bs_url = f"{base_url}/api/v1/accounting/reports/balance-sheet/?company_id={pilot_cid}"
        req_bs = urllib.request.Request(
            bs_url,
            headers={'Authorization': f'Bearer {token}', 'User-Agent': 'SriLekh-Auditor/1.0'}
        )
        with urllib.request.urlopen(req_bs, timeout=timeout, context=ctx) as resp_bs:
            bs_data = json.loads(resp_bs.read().decode('utf-8'))
            assert resp_bs.status == 200, f"Expected 200, got {resp_bs.status}"
            report = bs_data.get('data', {})
            assert report.get('is_balanced') is True, "Live Balance Sheet not balanced!"
            assert str(report.get('difference')) == "0.00", f"Non-zero variance: {report.get('difference')}"
            print(f"  Tenant: {report.get('company_name')}")
            print(f"  Balance Sheet Equilibrium: Assets Rs {report.get('assets', {}).get('total_assets')} == Liab Rs {report.get('liabilities_and_equity', {}).get('total_liabilities')} (Diff: Rs {report.get('difference')})")
            print("  [PASSED] Live financial statements balanced with zero variance.")

        forbidden_cid = "cd788d07-ae29-4af9-89d2-c5a4f32378cf"  # Garodia Bearing
        idor_url = f"{base_url}/api/v1/accounting/reports/balance-sheet/?company_id={forbidden_cid}"
        req_idor = urllib.request.Request(
            idor_url,
            headers={'Authorization': f'Bearer {token}', 'User-Agent': 'SriLekh-Auditor/1.0'}
        )
        try:
            with urllib.request.urlopen(req_idor, timeout=timeout, context=ctx) as resp_idor:
                print(f"  [FAILED] CRITICAL SECURITY DEFECT: Unauthorized cross-tenant access allowed (HTTP {resp_idor.status})!")
                return False
        except urllib.error.HTTPError as err:
            assert err.code == 403, f"Expected HTTP 403 Forbidden for cross-tenant IDOR, got {err.code}"
            print(f"  Cross-tenant access attempt returned: HTTP {err.code} Forbidden")
            print("  [PASSED] Public API strictly rejected cross-tenant IDOR traversal.")

    except Exception as e:
        print(f"  [FAILED] Probe 4 error: {e}")
        return False

    print("\n" + "=" * 80)
    print(">>> LIVE RENDER STAGING VERIFICATION PASSED (100%) <<<")
    print("=" * 80)
    return True


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Live Render Staging Verification Probe")
    parser.add_argument("url", nargs="?", help="Base URL of the Render deployment")
    parser.add_argument("--base-url", dest="base_url", help="Base URL of the Render deployment")
    parser.add_argument("--expected-commit", dest="expected_commit", default=None, help="Expected 8-char deployed commit prefix")
    parser.add_argument("--timeout", type=int, default=90, help="HTTP timeout per attempt in seconds")
    args = parser.parse_args()

    target_url = args.base_url or args.url
    if not target_url:
        print("Usage: python scripts/test_live_render_staging.py <RENDER_URL> or --base-url <RENDER_URL>")
        sys.exit(1)

    success = test_live_staging(target_url, timeout=args.timeout, expected_commit=args.expected_commit)
    sys.exit(0 if success else 1)
