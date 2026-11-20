import json
import urllib.request
import urllib.error
import ssl
import sys

BASE_URL = "https://vouch-u3u7.onrender.com"

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

TENANT_A_ID = "c2771ca4-31bd-47d2-b98c-c1be119f40a1" # Precision Agro Tools Pvt Ltd
USER_A_EMAIL = "owner_msme-plt-01@staging.srilekh.internal"
PASSWORD = "PilotSecurePass123!"

TENANT_B_ID = "cd788d07-ae29-4af9-89d2-c5a4f32378cf" # Garodia Bearing & Power Transmission
USER_B_EMAIL = "owner_msme-plt-02@staging.srilekh.internal"

def get_auth_token(email, password):
    login_url = f"{BASE_URL}/api/v1/auth/login/"
    payload = json.dumps({"email": email, "password": password}).encode('utf-8')
    req = urllib.request.Request(
        login_url,
        data=payload,
        headers={'Content-Type': 'application/json', 'User-Agent': 'SriLekh-Auditor/1.0'}
    )
    with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
        data = json.loads(resp.read().decode('utf-8'))
        return data["access"]

def make_request(method, path, token, body=None):
    url = f"{BASE_URL}{path}"
    headers = {
        'Authorization': f'Bearer {token}',
        'User-Agent': 'SriLekh-Auditor/1.0'
    }
    data = None
    if body is not None:
        data = json.dumps(body).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
            content = resp.read().decode('utf-8')
            return resp.status, content
    except urllib.error.HTTPError as e:
        content = e.read().decode('utf-8')
        return e.code, content

def run_phase2_tests():
    print("=" * 80)
    print("PHASE 2: AUTHENTICATED TENANT ISOLATION AUDIT")
    print("=" * 80)
    
    print("\n1. Authenticating as Tenant A User:", USER_A_EMAIL)
    token_A = get_auth_token(USER_A_EMAIL, PASSWORD)
    print("   [PASS] Authenticated successfully. Token obtained.")
    
    print("\n2. Authenticating as Tenant B User:", USER_B_EMAIL)
    token_B = get_auth_token(USER_B_EMAIL, PASSWORD)
    print("   [PASS] Authenticated successfully. Token obtained.")

    results = []

    # Direction 1: User A accessing Tenant A (Allowed) vs Tenant B (Blocked)
    print("\n--- Testing Direction 1: User A accessing Tenant A (Authorized) ---")
    status_own, _ = make_request("GET", f"/api/v1/gst/overview/{TENANT_A_ID}/", token_A)
    print(f"  GET /api/v1/gst/overview/Tenant_A: HTTP {status_own}")
    assert status_own == 200, f"Expected 200 for own tenant, got {status_own}"

    print("\n--- Testing Direction 1: User A attempting to access Tenant B (Must be 403 Forbidden) ---")
    cross_tests_A_to_B = [
        ("GET", f"/api/v1/gst/overview/{TENANT_B_ID}/", None, "Overview Dashboard"),
        ("GET", f"/api/v1/gst/workspace/{TENANT_B_ID}/", None, "Workspace Status"),
        ("GET", f"/api/v1/gst/registrations/{TENANT_B_ID}/", None, "Registrations List"),
        ("GET", f"/api/v1/gst/returns/gstr1/{TENANT_B_ID}/", None, "GSTR-1 Returns"),
        ("GET", f"/api/v1/gst/returns/gstr3b/{TENANT_B_ID}/", None, "GSTR-3B Returns"),
        ("GET", f"/api/v1/gst/workspace/{TENANT_B_ID}/export/?period=082026&return_type=GSTR1", None, "Workspace Export"),
        ("POST", f"/api/v1/gst/workspace/{TENANT_B_ID}/init-period/", {"period": "082026", "return_type": "GSTR1"}, "Init Period (Write)"),
        ("POST", f"/api/v1/gst/registrations/{TENANT_B_ID}/", {"gstin": "27AAACB1234B1Z2", "trade_name": "Injected Corp"}, "Create Registration (Write)"),
        ("DELETE", f"/api/v1/gst/registrations/{TENANT_B_ID}/11111111-1111-1111-1111-111111111111/", None, "Delete Registration (Delete)"),
    ]

    for method, path, body, desc in cross_tests_A_to_B:
        status, resp_body = make_request(method, path, token_A, body)
        passed = (status == 403)
        print(f"  [{'PASS' if passed else 'FAIL'}] {desc} ({method} {path}) -> HTTP {status}")
        results.append((f"User A -> Tenant B {desc}", status, passed, resp_body[:120]))

    # Direction 2: User B accessing Tenant B (Allowed) vs Tenant A (Blocked)
    print("\n--- Testing Direction 2: User B accessing Tenant B (Authorized) ---")
    status_own_B, _ = make_request("GET", f"/api/v1/gst/overview/{TENANT_B_ID}/", token_B)
    print(f"  GET /api/v1/gst/overview/Tenant_B: HTTP {status_own_B}")
    assert status_own_B == 200, f"Expected 200 for own tenant, got {status_own_B}"

    print("\n--- Testing Direction 2: User B attempting to access Tenant A (Must be 403 Forbidden) ---")
    cross_tests_B_to_A = [
        ("GET", f"/api/v1/gst/overview/{TENANT_A_ID}/", None, "Overview Dashboard"),
        ("GET", f"/api/v1/gst/workspace/{TENANT_A_ID}/", None, "Workspace Status"),
        ("GET", f"/api/v1/gst/registrations/{TENANT_A_ID}/", None, "Registrations List"),
        ("GET", f"/api/v1/gst/returns/gstr1/{TENANT_A_ID}/", None, "GSTR-1 Returns"),
        ("GET", f"/api/v1/gst/returns/gstr3b/{TENANT_A_ID}/", None, "GSTR-3B Returns"),
        ("GET", f"/api/v1/gst/workspace/{TENANT_A_ID}/export/?period=082026&return_type=GSTR1", None, "Workspace Export"),
        ("POST", f"/api/v1/gst/workspace/{TENANT_A_ID}/init-period/", {"period": "082026", "return_type": "GSTR1"}, "Init Period (Write)"),
        ("POST", f"/api/v1/gst/registrations/{TENANT_A_ID}/", {"gstin": "27AAACB1234B1Z2", "trade_name": "Injected Corp"}, "Create Registration (Write)"),
        ("DELETE", f"/api/v1/gst/registrations/{TENANT_A_ID}/11111111-1111-1111-1111-111111111111/", None, "Delete Registration (Delete)"),
    ]

    for method, path, body, desc in cross_tests_B_to_A:
        status, resp_body = make_request(method, path, token_B, body)
        passed = (status == 403)
        print(f"  [{'PASS' if passed else 'FAIL'}] {desc} ({method} {path}) -> HTTP {status}")
        results.append((f"User B -> Tenant A {desc}", status, passed, resp_body[:120]))

    # Test non-existent tenant (Must be 403 Forbidden or 404 Not Found)
    print("\n--- Testing Non-Existent Company Access (Must be 403 Forbidden or 404 Not Found) ---")
    fake_cid = "00000000-0000-0000-0000-000000000000"
    status_fake, resp_fake = make_request("GET", f"/api/v1/gst/overview/{fake_cid}/", token_A)
    passed_fake = (status_fake in (403, 404))
    print(f"  [{'PASS' if passed_fake else 'FAIL'}] Non-existent tenant -> HTTP {status_fake}")
    results.append(("User A -> Non-existent Tenant Overview", status_fake, passed_fake, resp_fake[:120]))

    print("\n" + "=" * 80)
    print("PHASE 2 SUMMARY:")
    all_passed = all(r[2] for r in results)
    print(f"Total Cross-Tenant Authorization Checks: {len(results)}")
    print(f"Passed: {sum(1 for r in results if r[2])} / {len(results)}")
    print(f"Overall Phase 2 Status: {'PASS' if all_passed else 'FAIL'}")
    print("=" * 80)

if __name__ == '__main__':
    run_phase2_tests()
