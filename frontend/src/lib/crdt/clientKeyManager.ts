/**
 * Client-Side Ed25519 Cryptographic Key & Device Identity Manager.
 * 
 * Provides native Web Crypto API asymmetric key generation, local private key persistence,
 * deterministic SHA-256 operation signing, and server-side device authorization binding.
 * 100% bit-for-bit interoperable with server-side Python `cryptography.hazmat.primitives.asymmetric.ed25519`.
 */

export interface DeviceIdentity {
  deviceId: string;
  replicaId: string;
  keyId: string;
  publicKeyHex: string;
}

export class ClientKeyManager {
  private static cachedPrivateKey: CryptoKey | null = null;
  private static cachedIdentity: DeviceIdentity | null = null;

  public static getDeviceId(): string {
    if (typeof window !== "undefined") {
      let id = localStorage.getItem("vouch_device_id");
      if (!id) {
        id = `DEV-${this.generateRandomHex(12).toUpperCase()}`;
        localStorage.setItem("vouch_device_id", id);
      }
      return id;
    }
    return "DEV-SSR-CLIENT";
  }

  public static getReplicaId(): string {
    if (typeof window !== "undefined") {
      let id = localStorage.getItem("vouch_protocol_replica_id");
      if (!id) {
        id = `REP-${this.generateRandomHex(8).toUpperCase()}`;
        localStorage.setItem("vouch_protocol_replica_id", id);
      }
      return id;
    }
    return "REP-SSR-CLIENT";
  }

  public static getKeyId(): string {
    if (typeof window !== "undefined") {
      let kid = localStorage.getItem("vouch_ed25519_key_id");
      if (!kid) {
        kid = `KID-${this.generateRandomHex(12).toUpperCase()}`;
        localStorage.setItem("vouch_ed25519_key_id", kid);
      }
      return kid;
    }
    return "KID-SSR-KEY";
  }

  /**
   * Retrieves or initializes the cryptographic Ed25519 keypair for this physical device.
   */
  public static async getOrCreateIdentity(): Promise<DeviceIdentity> {
    if (this.cachedIdentity && this.cachedPrivateKey) {
      return this.cachedIdentity;
    }

    const deviceId = this.getDeviceId();
    const replicaId = this.getReplicaId();
    const keyId = this.getKeyId();

    if (typeof window === "undefined" || !window.crypto || !window.crypto.subtle) {
      return {
        deviceId,
        replicaId,
        keyId,
        publicKeyHex: "00".repeat(32)
      };
    }

    const storedPubHex = localStorage.getItem("vouch_ed25519_pub_hex");
    const storedPrivJwk = localStorage.getItem("vouch_ed25519_priv_jwk");

    if (storedPubHex && storedPrivJwk) {
      try {
        const jwk = JSON.parse(storedPrivJwk);
        const privKey = await window.crypto.subtle.importKey(
          "jwk",
          jwk,
          { name: "Ed25519" },
          true,
          ["sign"]
        );
        this.cachedPrivateKey = privKey;
        this.cachedIdentity = {
          deviceId,
          replicaId,
          keyId,
          publicKeyHex: storedPubHex
        };
        return this.cachedIdentity;
      } catch (err) {
        console.warn("Failed to load existing Ed25519 keypair, generating a fresh one:", err);
      }
    }

    // Generate fresh Ed25519 keypair using native Web Crypto
    try {
      const keyPair = await window.crypto.subtle.generateKey(
        { name: "Ed25519" },
        true,
        ["sign", "verify"]
      );

      // Export raw 32-byte public key as hex
      const rawPub = await window.crypto.subtle.exportKey("raw", keyPair.publicKey);
      const pubHex = Array.from(new Uint8Array(rawPub))
        .map(b => b.toString(16).padStart(2, "0"))
        .join("");

      // Export private key as JWK for durable local storage
      const privJwk = await window.crypto.subtle.exportKey("jwk", keyPair.privateKey);

      localStorage.setItem("vouch_ed25519_pub_hex", pubHex);
      localStorage.setItem("vouch_ed25519_priv_jwk", JSON.stringify(privJwk));

      this.cachedPrivateKey = keyPair.privateKey;
      this.cachedIdentity = {
        deviceId,
        replicaId,
        keyId,
        publicKeyHex: pubHex
      };
      return this.cachedIdentity;
    } catch (genErr) {
      console.error("Web Crypto Ed25519 generation error:", genErr);
      throw new Error(`Ed25519 key generation failed: ${genErr}`);
    }
  }

  /**
   * Signs a canonical payload hash using the device's persistent Ed25519 private key.
   * Produces a 64-byte (128 hex chars) digital signature.
   */
  public static async signPayloadHash(payloadHash: string): Promise<string> {
    await this.getOrCreateIdentity();
    if (!this.cachedPrivateKey || typeof window === "undefined") {
      throw new Error("Cannot sign: Private key is not available in current environment.");
    }

    const encoder = new TextEncoder();
    const dataToSign = encoder.encode(payloadHash);
    const sigBuffer = await window.crypto.subtle.sign(
      { name: "Ed25519" },
      this.cachedPrivateKey,
      dataToSign
    );

    const sigBytes = new Uint8Array(sigBuffer);
    return Array.from(sigBytes)
      .map(b => b.toString(16).padStart(2, "0"))
      .join("");
  }

  /**
   * Registers this device's public key with the server and binds it to the current Company.
   */
  public static async registerDeviceWithServer(params: {
    companyId: string;
    accessToken?: string;
    apiBaseUrl?: string;
    deviceName?: string;
  }): Promise<{ registered: boolean; error?: string }> {
    try {
      const identity = await this.getOrCreateIdentity();
      const baseUrl = params.apiBaseUrl || "";
      const url = `${baseUrl}/api/v1/protocol/devices/register/`;

      const headers: Record<string, string> = {
        "Content-Type": "application/json"
      };
      if (params.accessToken) {
        headers["Authorization"] = `Bearer ${params.accessToken}`;
      }

      const res = await fetch(url, {
        method: "POST",
        headers,
        body: JSON.stringify({
          device_id: identity.deviceId,
          replica_id: identity.replicaId,
          public_key_hex: identity.publicKeyHex,
          key_id: identity.keyId,
          device_name: params.deviceName || (typeof navigator !== "undefined" ? navigator.userAgent : "Web Client"),
          company_id: params.companyId
        })
      });

      if (!res.ok) {
        const errText = await res.text();
        return { registered: false, error: `HTTP ${res.status}: ${errText}` };
      }

      const resData = await res.json();
      return { registered: resData.status === "REGISTERED" };
    } catch (err: any) {
      return { registered: false, error: err?.message || "Device registration network error" };
    }
  }

  private static generateRandomHex(length: number): string {
    if (typeof window !== "undefined" && window.crypto && window.crypto.getRandomValues) {
      const bytes = new Uint8Array(Math.ceil(length / 2));
      window.crypto.getRandomValues(bytes);
      return Array.from(bytes).map(b => b.toString(16).padStart(2, "0")).join("").substring(0, length);
    }
    return Math.random().toString(36).substring(2, 2 + length);
  }
}
