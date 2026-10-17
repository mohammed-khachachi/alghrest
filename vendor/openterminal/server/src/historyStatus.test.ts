import { afterEach, describe, expect, it, vi } from "vitest";
import { historyResponse, historySeries } from "./historyStatus.js";

const candles = [{time:1,open:10,high:11,low:9,close:10,volume:5}];
afterEach(()=>vi.useRealTimers());
describe('history provenance',()=>{
  it('keeps the original fetch time and provider through cache hits and failed refreshes',async()=>{
    vi.useFakeTimers(); vi.setSystemTime(new Date('2026-10-15T12:00:00Z'));
    const load = vi.fn().mockResolvedValue({candles,provider:'yahoo',interval:'1d'});
    const first = await historyResponse('CACHE-TEST','6M',20000,load);
    expect(first.metadata.cache_state).toBe('fetched');
    vi.advanceTimersByTime(10000);
    const hit = await historyResponse('CACHE-TEST','6M',20000,load);
    expect(hit.metadata.cache_state).toBe('cached');
    expect(hit.metadata.fetched_at).toBe(first.metadata.fetched_at);
    expect(load).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(11000); load.mockRejectedValueOnce(new Error('offline'));
    const stale = await historyResponse('CACHE-TEST','6M',20000,load);
    expect(stale.metadata).toMatchObject({cache_state:'stale',provider:'yahoo',interval:'1d',fetched_at:first.metadata.fetched_at});
    expect(stale.candles).toEqual(candles);
    const recovered = await historyResponse('CACHE-TEST','6M',20000,load);
    expect(recovered.metadata.cache_state).toBe('fetched');
    expect(recovered.metadata.fetched_at).not.toBe(first.metadata.fetched_at);
  });
  it('does not invent data or metadata when no prior history exists',async()=>{
    await expect(historyResponse('MISSING-TEST','6M',20000,async()=>{throw new Error('offline');})).rejects.toThrow('offline');
  });
  it('rejects empty provider results so fallback can continue',async()=>{
    await expect(historySeries('nasdaq',null,async()=>[])).rejects.toThrow('empty history');
    const result = await historySeries('nasdaq',null,async()=>candles);
    expect(result.interval).toBeNull();
  });
});
