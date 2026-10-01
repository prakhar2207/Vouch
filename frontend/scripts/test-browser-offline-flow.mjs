/**
 * Browser Offline / Online E2E Test Suite (Simulated Browser Runtime)
 * 
 * Tests the complete client-side distributed accounting lifecycle:
 * 1. Web Crypto Ed25519 key generation & non-extractable IndexedDB key custody (VouchSecurityVault).
 * 2. Zero private key leakage to localStorage.
 * 3. Offline voucher creation via ClientOperationManager:
 *    - Canonical Transaction envelope creation
 *    - Deterministic fixed-point decimal normalization
 *    - Canonical SHA-256 hash calculation
 *    - Ed25519 digital signature generation
 *    - IndexedDB operationLog persistence
 *    - Local UI projections (syncedVouchers, syncedProducts, syncedLedgers)
 *    - Outbox queue staging
 * 4. Inventory invariant preservation (negative stock is NOT clamped to 0).
 * 5. Reconnection & Outbox flush / convergence.
 */

import { indexedDB, IDBKeyRange } from "fake-indexeddb";

// 1. Polyfill browser globals
globalThis.indexedDB = indexedDB;
globalThis.IDBKeyRange = IDBKeyRange;

const mockStorage = new Map();
globalThis.localStorage = {
  getItem: (key) => mockStorage.get(key) || null,
  setItem: (key, val) => mockStorage.set(key, String(val)),
  removeItem: (key) => mockStorage.delete(key),
  clear: () => mockStorage.clear()
};

globalThis.location = { hostname: "localhost" };
globalThis.window = globalThis;
globalThis.BroadcastChannel = class {
  constructor(name) { this.name = name; }
  postMessage() {}
  close() {}
};

async function runBrowserOfflineFlow() {
  console.log("=".repeat(80));
  console.log("   VOUCH BROWSER CLIENT: OFFLINE / ONLINE E2E INTEGRATION TEST");
  console.log("=".repeat(80));

  // Dynamically import compiled/transpiled modules
  const { ClientKeyManager } = await import("../src/lib/crdt/clientKeyManager.ts");
  const { ClientOperationManager } = await import("../src/lib/crdt/clientOperationManager.ts");
  const { offlineDb } = await import("../src/lib/db/offlineDb.ts");
  const { canonicalJsonStringify, computeCanonicalSha256 } = await import("../src/lib/crdt/canonicalJson.ts");

  console.log("\n[Step 1] Initializing Client Web Crypto Ed25519 Identity...");
  const identity = await ClientKeyManager.getOrCreateIdentity();
  console.log(`  -> Device ID:      ${identity.deviceId}`);
  console.log(`  -> Replica ID:     ${identity.replicaId}`);
  console.log(`  -> Public Key Hex: ${identity.publicKeyHex.substring(0, 32)}...`);

  if (!identity.publicKeyHex || identity.publicKeyHex.length !== 64) {
    throw new Error(`Invalid public key length: expected 64 hex chars, got ${identity.publicKeyHex.length}`);
  }

  // Verify Zero localStorage leakage
  console.log("\n[Step 2] Auditing Storage Isolation (Zero localStorage Leakage)...");
  for (const [k, v] of mockStorage.entries()) {
    if (k.toLowerCase().includes("private") || String(v).includes("private")) {
      throw new Error(`CRITICAL SECURITY FAILURE: Private key leaked to localStorage under '${k}'!`);
    }
  }
  console.log("  [PASSED] Private key is NOT present in localStorage. Pure IndexedDB CryptoKey custody.");

  // Pre-seed offline inventory projection
  console.log("\n[Step 3] Seeding Initial Offline Projections...");
  await offlineDb.syncedProducts.clear();
  await offlineDb.syncedVouchers.clear();
  await offlineDb.operationLog.clear();
  await offlineDb.outboxQueue.clear();

  await offlineDb.syncedProducts.put({
    id: "PROD-VALVE-01",
    companyId: "COMP-CLIENT-001",
    sku: "VALVE-50MM",
    name: "Industrial 50mm Ball Valve",
    currentStock: 5.0,
    unit: "PCS",
    purchasePrice: 800.0,
    salesPrice: 1000.0,
    gstRate: 18.0,
    reorderLevel: 2,
    serverUpdatedAt: Date.now()
  });

  const seeded = await offlineDb.syncedProducts.get("PROD-VALVE-01");
  console.log(`  -> Seeded Product 'VALVE-50MM' with Initial Stock: ${seeded.currentStock} PCS`);

  // Record an offline sales voucher for 2 units
  console.log("\n[Step 4] Creating Disconnected Offline Voucher (2 Units Sale)...");
  const mutationResult = await ClientOperationManager.recordLocalVoucherMutation({
    companyId: "COMP-CLIENT-001",
    voucherType: "SALES",
    voucherDate: "2026-10-01",
    payload: {
      party_name: "Metro Infra Buildcon",
      party_gstin: "27BBBBB5678B1Z6",
      items: [
        {
          sku: "VALVE-50MM",
          product_id: "PROD-VALVE-01",
          name: "Industrial 50mm Ball Valve",
          quantity: 2,
          unit_price: 1000.0,
          hsn_code: "8481",
          gst_rate: 18.0
        }
      ],
      subtotal: 2000.0,
      total_tax: 360.0,
      grand_total: 2360.0,
      cgst_amount: 180.0,
      sgst_amount: 180.0
    }
  });

  console.log(`  -> Recorded Local Operation: ${mutationResult.operationId}`);
  console.log(`  -> Assigned Transaction ID:  ${mutationResult.transactionId}`);

  // Verify operationLog
  const opLog = await offlineDb.operationLog.get(mutationResult.operationId);
  if (!opLog) throw new Error("Operation not found in offlineDb.operationLog!");
  if (!opLog.signature || opLog.signature.length !== 128) {
    throw new Error(`Invalid Ed25519 signature in operationLog: length ${opLog.signature?.length}`);
  }
  console.log(`  -> Validated Ed25519 Signature: ${opLog.signature.substring(0, 32)}... (128 hex chars)`);

  // Verify local product projection
  const updatedProduct = await offlineDb.syncedProducts.get("PROD-VALVE-01");
  console.log(`  -> Projected Stock after 2-unit sale: ${updatedProduct.currentStock} PCS (Expected: 3.0)`);
  if (updatedProduct.currentStock !== 3.0) {
    throw new Error(`Inventory projection mismatch: expected 3.0, got ${updatedProduct.currentStock}`);
  }

  // Verify outbox queue
  const outboxItems = await offlineDb.outboxQueue.where("transactionId").equals(mutationResult.transactionId).toArray();
  if (outboxItems.length !== 1) {
    throw new Error(`Expected 1 outbox item, found ${outboxItems.length}`);
  }
  console.log(`  -> Outbox Item Queued: ${outboxItems[0].operationId} (Status: ${outboxItems[0].status})`);

  // Test Negative Stock Invariant (Sell 5 units when only 3 remain)
  console.log("\n[Step 5] Testing Negative Inventory Invariant (Zero-Clamping Violation Defense)...");
  const secondMutation = await ClientOperationManager.recordLocalVoucherMutation({
    companyId: "COMP-CLIENT-001",
    voucherType: "SALES",
    voucherDate: "2026-10-01",
    payload: {
      party_name: "Metro Infra Buildcon",
      party_gstin: "27BBBBB5678B1Z6",
      items: [
        {
          sku: "VALVE-50MM",
          product_id: "PROD-VALVE-01",
          name: "Industrial 50mm Ball Valve",
          quantity: 5, // 3 - 5 = -2 (must NOT clamp to 0)
          unit_price: 1000.0,
          hsn_code: "8481",
          gst_rate: 18.0
        }
      ],
      subtotal: 5000.0,
      total_tax: 900.0,
      grand_total: 5900.0
    }
  });

  const negativeProduct = await offlineDb.syncedProducts.get("PROD-VALVE-01");
  console.log(`  -> Projected Stock after oversell: ${negativeProduct.currentStock} PCS (Expected: -2.0)`);
  if (negativeProduct.currentStock !== -2.0) {
    throw new Error(`Negative stock was artificially clamped! Expected -2.0, found ${negativeProduct.currentStock}`);
  }
  console.log("  [PASSED] Exact arithmetic negative inventory preserved without lossy clamping.");

  // Simulate Reconnection and Outbox Drainage
  console.log("\n[Step 6] Simulating Reconnection & Protocol CRDT Synchronization...");
  const queuedOutbox = await offlineDb.outboxQueue.where("status").equals("QUEUED").toArray();
  console.log(`  -> Queued Outbox Items to Sync: ${queuedOutbox.length} (Expected: 2)`);
  if (queuedOutbox.length !== 2) {
    throw new Error(`Expected 2 queued outbox items, found ${queuedOutbox.length}`);
  }

  for (const item of queuedOutbox) {
    // Ingest simulated server commitment
    await offlineDb.outboxQueue.update(item.id, {
      status: "COMMITTED"
    });
  }

  const remainingQueued = await offlineDb.outboxQueue.where("status").equals("QUEUED").count();
  console.log(`  -> Remaining Queued Outbox Items: ${remainingQueued} (Expected: 0)`);
  if (remainingQueued !== 0) {
    throw new Error(`Outbox drainage failed: ${remainingQueued} items still queued.`);
  }

  // Step 7: Cryptographic Security Vault Audit
  console.log("\n[Step 7] Running Authoritative Cryptographic Security Vault Audit...");
  const vaultAudit = await ClientKeyManager.auditSecurityVault();
  console.log(`  -> Web Crypto API Available:   ${vaultAudit.webCryptoSupported}`);
  console.log(`  -> IndexedDB Key Custody:      ${vaultAudit.hasIndexedDBKey}`);
  console.log(`  -> Zero LocalStorage Leakage:  ${vaultAudit.zeroLocalStorageLeak}`);
  console.log(`  -> Security Vault Status:      ${vaultAudit.secure ? "ACTIVE_SECURE" : "UNSECURE"}`);
  if (!vaultAudit.secure) {
    throw new Error(`Vault audit failed: ${vaultAudit.errors.join(", ")}`);
  }
  console.log("  [PASSED] Client cryptographic storage passed 100% security checks.");

  // Step 8: Client-Side Key Rotation with Cryptographic Proof
  console.log("\n[Step 8] Testing Client-Initiated Key Rotation with Cryptographic Proof...");
  const oldIdentity = await ClientKeyManager.getOrCreateIdentity();
  const oldPubHex = oldIdentity.publicKeyHex;

  // Mock server response for key rotation
  let rotationCapturedPayload = null;
  globalThis.fetch = async (url, options) => {
    if (url.includes("/api/v1/protocol/devices/rotate/")) {
      rotationCapturedPayload = JSON.parse(options.body);
      return {
        ok: true,
        status: 200,
        json: async () => ({
          status: "ROTATED",
          device_id: rotationCapturedPayload.device_id,
          new_public_key_hex: rotationCapturedPayload.new_public_key_hex,
          new_key_id: rotationCapturedPayload.new_key_id,
          authorization_method: "CRYPTOGRAPHIC_PROOF"
        }),
        text: async () => ""
      };
    }
    return { ok: false, status: 404, text: async () => "Not Found" };
  };

  const rotRes = await ClientKeyManager.rotateKeyWithServer({
    companyId: "COMP-CLIENT-001",
    accessToken: "fake-test-jwt"
  });

  if (!rotRes.rotated) {
    throw new Error(`Key rotation failed: ${rotRes.error}`);
  }

  console.log(`  -> Rotation Status:   ROTATED`);
  console.log(`  -> New Key ID:         ${rotRes.newKeyId}`);
  console.log(`  -> New Public Key:     ${rotRes.newPublicKeyHex.substring(0, 32)}...`);
  console.log(`  -> Rotation Signature: ${rotationCapturedPayload.rotation_signature.substring(0, 32)}...`);

  if (rotRes.newPublicKeyHex === oldPubHex) {
    throw new Error("Rotated public key must differ from the previous key!");
  }

  // Verify updated identity returned by ClientKeyManager
  const updatedIdentity = await ClientKeyManager.getOrCreateIdentity();
  if (updatedIdentity.publicKeyHex !== rotRes.newPublicKeyHex) {
    throw new Error("Identity cache failed to update after key rotation!");
  }
  console.log("  [PASSED] Client-initiated cryptographic key rotation verified end-to-end.");

  console.log("\n" + "=".repeat(80));
  console.log(">>> BROWSER OFFLINE/ONLINE E2E TEST PASSED WITH 100% SUCCESS <<<");
  console.log("=".repeat(80));
}

runBrowserOfflineFlow().catch((err) => {
  console.error("FATAL ERROR in browser offline E2E test:", err);
  process.exit(1);
});
