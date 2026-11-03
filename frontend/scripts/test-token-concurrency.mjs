/**
 * SriLekh PWA Cold Start Token Concurrency & Mutex Verification Test
 * 
 * Verifies that:
 * 1. Concurrent startup requests share a single refresh promise (P0 Mutex).
 * 2. Exactly ONE /api/v1/auth/refresh/ HTTP POST is fired under multi-request race.
 * 3. All callers receive the fresh token simultaneously without blacklisting collisions.
 * 4. Network errors / timeouts do NOT invalidate the local session.
 * 5. Explicit 401 clears tokens cleanly.
 */

import assert from "node:assert";

// Simulated browser storage & cookies
const localStorageMap = new Map();
const cookiesMap = new Map();

const localStorage = {
  getItem: (k) => localStorageMap.get(k) || null,
  setItem: (k, v) => localStorageMap.set(k, String(v)),
  removeItem: (k) => localStorageMap.delete(k),
  clear: () => localStorageMap.clear()
};

const Cookies = {
  get: (k) => cookiesMap.get(k) || null,
  set: (k, v) => cookiesMap.set(k, String(v)),
  remove: (k) => cookiesMap.delete(k)
};

// Helper: create simulated JWT
function createSimulatedToken(expiresInSeconds) {
  const header = Buffer.from(JSON.stringify({ alg: "HS256", typ: "JWT" })).toString("base64url");
  const payload = Buffer.from(
    JSON.stringify({
      exp: Math.floor(Date.now() / 1000) + expiresInSeconds,
      user_id: "user-test-123"
    })
  ).toString("base64url");
  return `${header}.${payload}.simulated_signature`;
}

function isTokenExpired(token) {
  if (!token) return true;
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return true;
    const payload = JSON.parse(Buffer.from(parts[1], "base64url").toString());
    return payload.exp * 1000 <= Date.now() + 10000;
  } catch {
    return true;
  }
}

function getAccessToken() {
  return Cookies.get("access_token") || localStorage.getItem("vouch_access_token") || undefined;
}

function getRefreshToken() {
  return Cookies.get("refresh_token") || localStorage.getItem("vouch_refresh_token") || undefined;
}

function setTokens(access, refresh) {
  Cookies.set("access_token", access);
  Cookies.set("refresh_token", refresh);
  localStorage.setItem("vouch_access_token", access);
  localStorage.setItem("vouch_refresh_token", refresh);
}

function removeTokens() {
  Cookies.remove("access_token");
  Cookies.remove("refresh_token");
  localStorage.removeItem("vouch_access_token");
  localStorage.removeItem("vouch_refresh_token");
}

// ---------------------------------------------------------------------------
// Simulated Refresh Manager matching frontend/src/utils/api.ts
// ---------------------------------------------------------------------------
let refreshCallCount = 0;
let mockNetworkLatencyMs = 50;
let mockServerFailMode = null; // null | 'network_error' | '401_invalid'

async function mockRefreshEndpoint(refreshToken) {
  refreshCallCount++;
  await new Promise((r) => setTimeout(r, mockNetworkLatencyMs));

  if (mockServerFailMode === "network_error") {
    const err = new Error("Network timeout (cold start)");
    err.code = "ECONNABORTED";
    throw err;
  }

  if (mockServerFailMode === "401_invalid") {
    const err = new Error("Token is blacklisted");
    err.response = { status: 401 };
    throw err;
  }

  return {
    access: createSimulatedToken(1800), // fresh 30m access token
    refresh: createSimulatedToken(86400 * 7), // rotated 7d refresh token
  };
}

let refreshPromise = null;

async function getValidAccessToken() {
  const token = getAccessToken();
  if (token && !isTokenExpired(token)) {
    return token;
  }

  const refreshToken = getRefreshToken();
  if (!refreshToken || isTokenExpired(refreshToken)) {
    return token || null;
  }

  // Mutex: If a refresh is already in-flight, await the exact same promise
  if (refreshPromise) {
    try {
      const refreshedToken = await refreshPromise;
      return refreshedToken || getAccessToken() || null;
    } catch {
      return getAccessToken() || null;
    }
  }

  refreshPromise = (async () => {
    try {
      const currentRefreshToken = getRefreshToken() || refreshToken;
      const res = await mockRefreshEndpoint(currentRefreshToken);
      const newAccess = res?.access;
      const newRefresh = res?.refresh || currentRefreshToken;
      if (newAccess) {
        setTokens(newAccess, newRefresh);
        return newAccess;
      }
      return null;
    } catch (err) {
      const isNetworkError =
        !err.response ||
        err.code === "ERR_NETWORK" ||
        err.code === "ECONNABORTED" ||
        err.message?.toLowerCase().includes("timeout");

      if (!isNetworkError && err.response && (err.response.status === 401 || err.response.status === 400)) {
        removeTokens();
      }
      return null;
    } finally {
      refreshPromise = null;
    }
  })();

  return await refreshPromise;
}

// ---------------------------------------------------------------------------
// TEST SUITE
// ---------------------------------------------------------------------------
async function runTests() {
  console.log("================================================================================");
  console.log("   SRILEKH PWA COLD START: TOKEN CONCURRENCY & DEDUPLICATION TEST");
  console.log("================================================================================");

  // Test 1: Active token returns immediately without network calls
  console.log("\n[Test 1] Fresh access token (<30m) returns synchronously without network...");
  setTokens(createSimulatedToken(1000), createSimulatedToken(86400));
  refreshCallCount = 0;
  const t1 = await getValidAccessToken();
  assert(t1, "Should return valid token");
  assert.strictEqual(refreshCallCount, 0, "Should NOT call refresh endpoint");
  console.log("  ✓ Passed: 0 network calls for fresh token");

  // Test 2: Expired access token triggers single refresh
  console.log("\n[Test 2] Expired access token with valid refresh token refreshes successfully...");
  setTokens(createSimulatedToken(-100), createSimulatedToken(86400)); // expired 100s ago
  refreshCallCount = 0;
  const t2 = await getValidAccessToken();
  assert(t2, "Should return new access token");
  assert(!isTokenExpired(t2), "New access token should be fresh");
  assert.strictEqual(refreshCallCount, 1, "Should call refresh endpoint exactly once");
  console.log("  ✓ Passed: Refreshed token and rotated credentials");

  // Test 3: Concurrency Race Condition (The Morning Startup Scenario)
  console.log("\n[Test 3] 10 concurrent requests at morning startup (all with expired access token)...");
  setTokens(createSimulatedToken(-500), createSimulatedToken(86400)); // overnight expired
  refreshCallCount = 0;
  mockNetworkLatencyMs = 80; // simulate sleeping server wake delay

  // 10 concurrent requests firing simultaneously
  const results = await Promise.all([
    getValidAccessToken(), // e.g. CompanyContext
    getValidAccessToken(), // e.g. FinancialYearContext
    getValidAccessToken(), // e.g. useRole
    getValidAccessToken(), // e.g. sync-worker pull
    getValidAccessToken(), // e.g. dashboard forecast
    getValidAccessToken(), // e.g. health check
    getValidAccessToken(),
    getValidAccessToken(),
    getValidAccessToken(),
    getValidAccessToken()
  ]);

  assert.strictEqual(refreshCallCount, 1, `CRITICAL: Expected exactly 1 network call, got ${refreshCallCount}`);
  for (let i = 0; i < results.length; i++) {
    assert(results[i], `Caller ${i} must receive fresh token`);
    assert.strictEqual(results[i], results[0], `Caller ${i} token must match caller 0`);
  }
  console.log(`  ✓ Passed: 10 parallel callers resolved through 1 single network POST (0 blacklisting race)`);

  // Test 4: Sleeping Render Cold Start Timeout (Does NOT clear session)
  console.log("\n[Test 4] Network timeout during Render cold start preserves offline session...");
  const oldAccess = createSimulatedToken(-100);
  const oldRefresh = createSimulatedToken(86400 * 5);
  setTokens(oldAccess, oldRefresh);
  mockServerFailMode = "network_error";
  refreshCallCount = 0;

  const resTimeout = await getValidAccessToken();
  assert.strictEqual(resTimeout, null, "Should return null on network error");
  assert(localStorage.getItem("vouch_refresh_token"), "Refresh token MUST NOT be deleted on timeout");
  assert.strictEqual(localStorage.getItem("vouch_refresh_token"), oldRefresh, "Original refresh token must be preserved");
  console.log("  ✓ Passed: Session preserved in local storage across server timeouts");

  // Test 5: Explicit 401 Token Rejection
  console.log("\n[Test 5] Server explicit HTTP 401 (token blacklisted/expired) clears credentials...");
  setTokens(createSimulatedToken(-100), createSimulatedToken(86400));
  mockServerFailMode = "401_invalid";
  refreshCallCount = 0;

  const res401 = await getValidAccessToken();
  assert.strictEqual(res401, null, "Should return null on 401");
  assert.strictEqual(localStorage.getItem("vouch_access_token"), null, "Access token must be cleared");
  assert.strictEqual(localStorage.getItem("vouch_refresh_token"), null, "Refresh token must be cleared");
  console.log("  ✓ Passed: Genuine 401 removes credentials cleanly");

  console.log("\n" + "=".repeat(80));
  console.log("   ALL 5 COLD START CONCURRENCY & SESSION INVARIANTS VERIFIED CLEANLY!");
  console.log("=".repeat(80) + "\n");
}

runTests().catch((err) => {
  console.error("Test failed:", err);
  process.exit(1);
});
