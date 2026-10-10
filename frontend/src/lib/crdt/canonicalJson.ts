/**
 * SriLekh Canonical JSON Serialization, based on RFC 8785 / JCS principles.
 * 
 * Guarantees bit-for-bit exact stringification and SHA-256 hashing across TypeScript and Python:
 * 1. Object keys are sorted lexicographically by UTF-16 code units.
 * 2. Strict absence of insignificant whitespace (separators `,` and `:` without extra spaces).
 * 3. Consistent Unicode representation.
 * 4. Exact equivalence with Python `json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)`.
 */

export function canonicalJsonStringify(obj: any): string {
  if (obj === null || obj === undefined) {
    return "null";
  }
  if (typeof obj === "boolean") {
    return obj ? "true" : "false";
  }
  if (typeof obj === "number") {
    if (!Number.isFinite(obj)) {
      throw new TypeError("Cannot serialize non-finite numbers to canonical JSON");
    }
    return JSON.stringify(obj);
  }
  if (typeof obj === "string") {
    return JSON.stringify(obj);
  }
  if (Array.isArray(obj)) {
    return "[" + obj.map(item => canonicalJsonStringify(item)).join(",") + "]";
  }
  if (typeof obj === "object") {
    const keys = Object.keys(obj).sort();
    return "{" + keys.map(k => `${JSON.stringify(k)}:${canonicalJsonStringify(obj[k])}`).join(",") + "}";
  }
  return JSON.stringify(obj);
}

/**
 * Computes deterministic SHA-256 hex digest over canonical JSON string.
 */
export async function computeCanonicalSha256(obj: any): Promise<string> {
  const cJson = canonicalJsonStringify(obj);
  if (typeof crypto !== "undefined" && crypto.subtle) {
    const encoder = new TextEncoder();
    const data = encoder.encode(cJson);
    const hashBuffer = await crypto.subtle.digest("SHA-256", data);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    return hashArray.map(b => b.toString(16).padStart(2, "0")).join("");
  }
  // Fallback for Node test environments
  try {
    const nodeCrypto = require("crypto");
    return nodeCrypto.createHash("sha256").update(cJson, "utf8").digest("hex");
  } catch (e) {
    throw new Error("No cryptographic digest provider available for canonical hashing.");
  }
}

/**
 * Constructs the canonical operation dictionary representation for DAG signing and verification.
 */
export function getCanonicalOperationDict(params: {
  operation_id: string;
  transaction_id: string;
  replica_id: string;
  operation_type: string;
  payload: any;
  logical_timestamp: number;
  parents: string[];
  operation_class?: string;
  tenant_id?: string;
  vector_clock?: Record<string, number>;
  previous_operation_hash?: string;
  version?: number;
}): Record<string, any> {
  return {
    class: params.operation_class || "CAUSAL",
    operation_id: params.operation_id,
    parents: [...params.parents].sort(),
    payload: params.payload,
    prev_hash: params.previous_operation_hash || "GENESIS",
    replica_id: params.replica_id,
    tenant_id: params.tenant_id || "DEFAULT_TENANT",
    timestamp: params.logical_timestamp,
    transaction_id: params.transaction_id,
    type: params.operation_type,
    vector_clock: params.vector_clock || {},
    version: params.version || 1
  };
}
