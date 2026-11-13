/* eslint-disable @typescript-eslint/no-explicit-any */
import { KeyVaultIDB } from "@/lib/crdt/clientKeyManager";

export const OFFLINE_ENVELOPE_VERSION = "AES-GCM-v1" as const;

export interface OfflineEncryptedEnvelope {
  __enc: typeof OFFLINE_ENVELOPE_VERSION;
  kid: string;
  iv: string; // Base64 96-bit IV
  ct: string; // Base64 ciphertext + GCM auth tag
}

export interface DecryptedWithWarningFlag {
  __decryptionError?: boolean;
}

/**
 * Only top-level indexed/primary key fields needed for Dexie `.where()` and sorting
 * remain outside the encrypted ciphertext envelope. Every sensitive financial amount,
 * party name, voucher number, GSTIN, narration, bank description, OCR result, and CRDT
 * payload is sealed inside `__enc`.
 */
export const OFFLINE_ENCRYPTED_TABLE_INDEX_FIELDS: Record<string, readonly string[]> = {
  vouchers: ["id", "localId", "voucherType", "status", "createdAt"],
  masters: ["key", "updatedAt"],
  ocrCache: ["fileHash", "cachedAt"],
  syncedVouchers: [
    "id",
    "companyId",
    "voucherType",
    "voucherDate",
    "dueDate",
    "status",
    "partyLedgerId",
    "serverUpdatedAt",
  ],
  syncedLedgers: ["id", "companyId", "ledgerType"],
  syncedProducts: ["id", "companyId", "sku", "currentStock"],
  syncMeta: ["companyId", "lastSyncAt", "syncStatus"],
  analyticsDaily: ["id", "companyId", "date"],
  analyticsParty: ["id", "companyId", "partyId"],
  syncedBankTransactions: [
    "id",
    "companyId",
    "bankLedgerId",
    "status",
    "transactionDate",
    "serverUpdatedAt",
  ],
  syncedPaymentAllocations: [
    "id",
    "companyId",
    "paymentVoucherId",
    "invoiceVoucherId",
  ],
  operationLog: [
    "operationId",
    "transactionId",
    "companyId",
    "userId",
    "replicaId",
    "operationType",
    "logicalTimestamp",
    "status",
    "createdAt",
  ],
  outboxQueue: [
    "id",
    "operationId",
    "transactionId",
    "companyId",
    "userId",
    "status",
    "retryCount",
    "nextRetryAt",
  ],
};

const ACTIVE_KEY_SLOT = "active_offline_db_key";
const textEncoder = new TextEncoder();
const textDecoder = new TextDecoder();

function bytesToBase64(bytes: Uint8Array): string {
  if (typeof Buffer !== "undefined") {
    return Buffer.from(bytes).toString("base64");
  }
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

function base64ToBytes(b64: string): Uint8Array {
  if (typeof Buffer !== "undefined") {
    return new Uint8Array(Buffer.from(b64, "base64"));
  }
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

function randomHex(byteLength: number): string {
  const buf = new Uint8Array(byteLength);
  globalThis.crypto.getRandomValues(buf);
  return Array.from(buf)
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function getSubtleCrypto(): SubtleCrypto | null {
  if (typeof globalThis === "undefined" || !globalThis.crypto?.subtle) {
    return null;
  }
  return globalThis.crypto.subtle;
}

export function isEncryptedEnvelope(val: unknown): val is OfflineEncryptedEnvelope {
  if (!val || typeof val !== "object") return false;
  const candidate = val as Record<string, unknown>;
  return (
    candidate.__enc === OFFLINE_ENVELOPE_VERSION &&
    typeof candidate.kid === "string" &&
    typeof candidate.iv === "string" &&
    typeof candidate.ct === "string"
  );
}

export class OfflineCryptoManager {
  private static activeKeyPromise: Promise<{ kid: string; key: CryptoKey }> | null = null;
  private static keyCache = new Map<string, CryptoKey>();

  public static clearInMemoryCache(): void {
    this.activeKeyPromise = null;
    this.keyCache.clear();
  }

  public static async getOrCreateActiveKey(): Promise<{ kid: string; key: CryptoKey }> {
    if (this.activeKeyPromise) {
      return this.activeKeyPromise;
    }

    const subtle = getSubtleCrypto();
    if (!subtle) {
      throw new Error("Web Crypto API (SubtleCrypto) is required for offline financial encryption.");
    }

    this.activeKeyPromise = (async () => {
      const existing = await KeyVaultIDB.getOfflineCryptoKey(ACTIVE_KEY_SLOT);
      if (existing?.key && existing?.kid) {
        this.keyCache.set(existing.kid, existing.key);
        return { kid: existing.kid, key: existing.key };
      }

      const generated = await subtle.generateKey(
        { name: "AES-GCM", length: 256 },
        false, // non-extractable: key bytes cannot be exported via exportKey() or persisted to localStorage
        ["encrypt", "decrypt"]
      );
      const kid = `OFFLINE-AES-${randomHex(8).toUpperCase()}`;
      const createdAt = Date.now();
      await KeyVaultIDB.saveOfflineCryptoKey(ACTIVE_KEY_SLOT, { kid, key: generated, createdAt });
      await KeyVaultIDB.saveOfflineCryptoKey(kid, { kid, key: generated, createdAt });
      this.keyCache.set(kid, generated);
      return { kid, key: generated };
    })();

    try {
      return await this.activeKeyPromise;
    } catch (err) {
      this.activeKeyPromise = null;
      throw err;
    }
  }

  public static async getKeyById(kid: string): Promise<CryptoKey | null> {
    const cached = this.keyCache.get(kid);
    if (cached) return cached;

    const record = await KeyVaultIDB.getOfflineCryptoKey(kid);
    if (record?.key) {
      this.keyCache.set(kid, record.key);
      return record.key;
    }

    const active = await this.getOrCreateActiveKey().catch(() => null);
    if (active && active.kid === kid) {
      return active.key;
    }
    return null;
  }

  /**
   * Generates a fresh 256-bit non-extractable AES-GCM key for subsequent writes while
   * retaining prior keys indexed by `kid` so queued offline operations still decrypt safely.
   */
  public static async rotateKey(): Promise<{ kid: string; previousKid?: string }> {
    const subtle = getSubtleCrypto();
    if (!subtle) {
      throw new Error("Web Crypto API (SubtleCrypto) is required for key rotation.");
    }
    const previous = await this.getOrCreateActiveKey().catch(() => null);
    const newKey = await subtle.generateKey(
      { name: "AES-GCM", length: 256 },
      false,
      ["encrypt", "decrypt"]
    );
    const newKid = `OFFLINE-AES-${randomHex(8).toUpperCase()}`;
    const createdAt = Date.now();
    await KeyVaultIDB.saveOfflineCryptoKey(newKid, { kid: newKid, key: newKey, createdAt });
    await KeyVaultIDB.saveOfflineCryptoKey(ACTIVE_KEY_SLOT, { kid: newKid, key: newKey, createdAt });
    this.keyCache.set(newKid, newKey);
    this.activeKeyPromise = Promise.resolve({ kid: newKid, key: newKey });
    return { kid: newKid, previousKid: previous?.kid };
  }
}

export function isEncryptedTable(tableName: string): boolean {
  return Object.prototype.hasOwnProperty.call(OFFLINE_ENCRYPTED_TABLE_INDEX_FIELDS, tableName);
}

/**
 * Seals all non-index fields of a record into an AES-GCM-256 encrypted envelope stored at `__enc`.
 * Already-sealed records pass through unchanged so pre-encrypted batch writes inside
 * multi-table transactions perform zero async WebCrypto awaits inside active IDB transactions.
 */
export async function encryptRecordForTable<T extends Record<string, any>>(
  tableName: string,
  record: T
): Promise<Record<string, any>> {
  if (!record || typeof record !== "object" || !isEncryptedTable(tableName)) {
    return record;
  }
  if (isEncryptedEnvelope((record as Record<string, unknown>).__enc)) {
    return record;
  }
  if (!getSubtleCrypto()) {
    return record;
  }

  const indexFields = OFFLINE_ENCRYPTED_TABLE_INDEX_FIELDS[tableName];
  const indexSet = new Set(indexFields);
  const outer: Record<string, any> = {};
  const secretPayload: Record<string, any> = {};

  for (const [k, v] of Object.entries(record)) {
    if (k === "__enc" || k === "__decryptionError") continue;
    if (indexSet.has(k)) {
      if (v !== undefined) {
        outer[k] = v;
      }
    } else if (v !== undefined) {
      secretPayload[k] = v;
    }
  }

  const { kid, key } = await OfflineCryptoManager.getOrCreateActiveKey();
  const iv = new Uint8Array(12);
  globalThis.crypto.getRandomValues(iv);
  const plaintextBytes = textEncoder.encode(JSON.stringify(secretPayload));
  const aad = textEncoder.encode(`srilekh:offline:${tableName}`);

  const cipherBuffer = await globalThis.crypto.subtle.encrypt(
    { name: "AES-GCM", iv, additionalData: aad },
    key,
    plaintextBytes
  );

  outer.__enc = {
    __enc: OFFLINE_ENVELOPE_VERSION,
    kid,
    iv: bytesToBase64(iv),
    ct: bytesToBase64(new Uint8Array(cipherBuffer)),
  } satisfies OfflineEncryptedEnvelope;

  return outer;
}

export async function encryptBatchForTable<T extends Record<string, any>>(
  tableName: string,
  records: readonly T[]
): Promise<Record<string, any>[]> {
  if (!isEncryptedTable(tableName) || !records.length) {
    return records as Record<string, any>[];
  }
  return Promise.all(records.map((item) => encryptRecordForTable(tableName, item)));
}

/**
 * Unseals an AES-GCM-256 encrypted IndexedDB record back into its full application shape.
 * - Backward compatibility: legacy unencrypted records (no `__enc`) pass through seamlessly.
 * - Non-destructive failure handling: if decryption fails or key is missing (e.g. wiped vault),
 *   never deletes the underlying row; flags `__decryptionError: true` so callers avoid losing
 *   queued offline accounting items while refusing to fabricate plaintext.
 */
export async function decryptRecordForTable<T extends Record<string, any>>(
  tableName: string,
  record: T | undefined
): Promise<T | undefined> {
  if (!record || typeof record !== "object" || !isEncryptedTable(tableName)) {
    return record;
  }

  const envelope = (record as Record<string, unknown>).__enc;
  if (!envelope) {
    // Staged backward compatibility for legacy pre-encryption records
    return record;
  }
  if (!isEncryptedEnvelope(envelope)) {
    return record;
  }

  const subtle = getSubtleCrypto();
  if (!subtle) {
    return { ...record, __decryptionError: true };
  }

  try {
    const key = await OfflineCryptoManager.getKeyById(envelope.kid);
    if (!key) {
      console.warn(`[offlineCrypto] Missing decryption key (${envelope.kid}) for table ${tableName}.`);
      const preserved: Record<string, any> = { ...record, __decryptionError: true };
      delete preserved.__enc;
      return preserved as T;
    }

    const ivBytes = base64ToBytes(envelope.iv);
    const ctBytes = base64ToBytes(envelope.ct);
    const iv = new Uint8Array(ivBytes.length);
    iv.set(ivBytes);
    const ct = new Uint8Array(ctBytes.length);
    ct.set(ctBytes);
    const aad = textEncoder.encode(`srilekh:offline:${tableName}`);

    const decryptedBuffer = await subtle.decrypt(
      { name: "AES-GCM", iv, additionalData: aad },
      key,
      ct
    );
    const secretPayload = JSON.parse(textDecoder.decode(new Uint8Array(decryptedBuffer)));

    const restored: Record<string, any> = {};
    for (const [k, v] of Object.entries(record)) {
      if (k === "__enc" || k === "__decryptionError") continue;
      restored[k] = v;
    }
    if (secretPayload && typeof secretPayload === "object") {
      Object.assign(restored, secretPayload);
    }
    return restored as T;
  } catch (err) {
    console.warn(`[offlineCrypto] Failed to decrypt ${tableName} record:`, err);
    const preserved: Record<string, any> = { ...record, __decryptionError: true };
    delete preserved.__enc;
    return preserved as T;
  }
}
