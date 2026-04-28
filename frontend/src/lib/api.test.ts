import { describe, expect, it } from "vitest";

import { resolveApiBaseUrl } from "@/lib/api";

describe("resolveApiBaseUrl", () => {
  it("keeps the configured loopback host when it already matches the browser host", () => {
    expect(resolveApiBaseUrl("http://127.0.0.1:8100", "127.0.0.1")).toBe("http://127.0.0.1:8100");
  });

  it("aligns the API loopback host with localhost when the browser uses localhost", () => {
    expect(resolveApiBaseUrl("http://127.0.0.1:8100", "localhost")).toBe("http://localhost:8100");
  });

  it("aligns the API loopback host with 127.0.0.1 when the browser uses 127.0.0.1", () => {
    expect(resolveApiBaseUrl("http://localhost:8100", "127.0.0.1")).toBe("http://127.0.0.1:8100");
  });

  it("leaves non-loopback API hosts unchanged", () => {
    expect(resolveApiBaseUrl("https://api.example.com", "localhost")).toBe("https://api.example.com");
  });
});
