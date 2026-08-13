import { describe, expect, it } from "vitest";
import { rejectCrossSiteRequest } from "./server-auth";

describe("rejectCrossSiteRequest", () => {
  it("accepts a same-origin state-changing request", () => {
    const request = new Request("http://localhost:3000/api/proxy/auth/session", {
      method: "POST",
      headers: { Origin: "http://localhost:3000", "Sec-Fetch-Site": "same-origin" },
    });

    expect(rejectCrossSiteRequest(request)).toBeNull();
  });

  it("rejects missing and cross-site origins", () => {
    const missing = new Request("http://localhost:3000/api/proxy/auth/session", {
      method: "POST",
    });
    const crossSite = new Request("http://localhost:3000/api/proxy/auth/session", {
      method: "POST",
      headers: { Origin: "https://attacker.example", "Sec-Fetch-Site": "cross-site" },
    });

    expect(rejectCrossSiteRequest(missing)?.status).toBe(403);
    expect(rejectCrossSiteRequest(crossSite)?.status).toBe(403);
  });

  it("fails closed when the configured origin is malformed", () => {
    const previous = process.env.FINSHIELD_ALLOWED_ORIGINS;
    process.env.FINSHIELD_ALLOWED_ORIGINS = "not a url";
    try {
      const request = new Request("http://localhost:3000/api/proxy/auth/session", {
        method: "POST",
        headers: { Origin: "http://localhost:3000" },
      });
      expect(rejectCrossSiteRequest(request)?.status).toBe(403);
    } finally {
      if (previous === undefined) delete process.env.FINSHIELD_ALLOWED_ORIGINS;
      else process.env.FINSHIELD_ALLOWED_ORIGINS = previous;
    }
  });
});
