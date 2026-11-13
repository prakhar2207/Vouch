import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { resolveApiBaseUrl } from "./api";

describe("Environment API URL Isolation", () => {
  it("routes localhost to local Django API", () => {
    assert.equal(resolveApiBaseUrl({ hostname: "localhost", envApiUrl: "" }), "http://localhost:8000");
    assert.equal(resolveApiBaseUrl({ hostname: "127.0.0.1", envApiUrl: "" }), "http://localhost:8000");
  });

  it("routes staging/preview web hosts away from production API when NEXT_PUBLIC_API_URL is unset", () => {
    assert.equal(
      resolveApiBaseUrl({ hostname: "srilekh-staging.vercel.app", envApiUrl: "" }),
      "https://vouch-u3u7.onrender.com"
    );
    assert.equal(
      resolveApiBaseUrl({ hostname: "staging.srilekh.com", envApiUrl: "" }),
      "https://vouch-u3u7.onrender.com"
    );
  });

  it("fails closed if staging context explicitly attempts to target production API", () => {
    assert.throws(
      () =>
        resolveApiBaseUrl({
          appEnv: "staging",
          hostname: "staging.srilekh.com",
          envApiUrl: "https://api.srilekh.com",
        }),
      /API Isolation/
    );
    assert.throws(
      () =>
        resolveApiBaseUrl({
          appEnv: "staging",
          envApiUrl: "https://vouch-api-752s.onrender.com",
        }),
      /API Isolation/
    );
  });

  it("routes official production domains and native APK builds to production API", () => {
    assert.equal(resolveApiBaseUrl({ hostname: "srilekh.com", envApiUrl: "" }), "https://api.srilekh.com");
    assert.equal(resolveApiBaseUrl({ native: true, envApiUrl: "" }), "https://api.srilekh.com");
  });
});
