import { afterEach, expect, it, vi } from "vitest";
import type { Request, Response } from "express";

afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); vi.restoreAllMocks(); vi.resetModules(); });

it("serves futures candles when Yahoo rejects a browser User-Agent from a server", async () => {
  vi.stubEnv("YAHOO_USER_AGENT", "");
  vi.stubGlobal("fetch", vi.fn(async (input: string, options?: RequestInit) => {
    const url = new URL(input);
    if (url.hostname === "query1.finance.yahoo.com" && url.pathname.includes("/v8/finance/chart/")) {
      if (new Headers(options?.headers).has("User-Agent")) return new Response("Too Many Requests", { status: 429 });
      return Response.json({ chart: { result: [{ timestamp: [1780000000], indicators: { quote: [{ open: [10], high: [12], low: [9], close: [11], volume: [100] }] } }] } });
    }
    return new Response("Unavailable", { status: 503 });
  }));
  vi.spyOn(console, "error").mockImplementation(() => {});
  const { marketRouter } = await import("../routes/market.js");
  const handler = (marketRouter as any).stack.find((layer: any) => layer.route?.path === "/history/:symbol").route.stack[0].handle;
  const res = { json: vi.fn(), status: vi.fn().mockReturnThis() } as unknown as Response;
  await handler({ params: { symbol: "ES=F" }, query: { range: "1D", metadata: "1" } } as unknown as Request, res, () => {});
  expect(res.status).not.toHaveBeenCalled();
  expect(res.json).toHaveBeenCalledWith(expect.objectContaining({
    candles: [{ time: 1780000000, open: 10, high: 12, low: 9, close: 11, volume: 100 }],
    metadata: expect.objectContaining({ symbol: "ES=F", provider: "yahoo", interval: "5m" }),
  }));
});

it("preserves an operator's explicit User-Agent override", async () => {
  vi.stubEnv("YAHOO_USER_AGENT", "ResearchOperator/1.0");
  const fetchMock = vi.fn().mockResolvedValue(Response.json({ chart: { result: [{ timestamp: [], indicators: { quote: [{}] } }] } }));
  vi.stubGlobal("fetch", fetchMock);
  const { history } = await import("./yahoo.js");
  await history("ES=F", "1d", "5m");
  expect(new Headers(fetchMock.mock.calls[0][1].headers).get("User-Agent")).toBe("ResearchOperator/1.0");
});
