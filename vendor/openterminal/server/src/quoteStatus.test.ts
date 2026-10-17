import { afterEach, expect, it, vi } from 'vitest';
import type { Request, Response } from 'express';
import { marketRouter } from './routes/market.js';
import * as nasdaq from './providers/nasdaq.js';
import * as yahoo from './providers/yahoo.js';
import * as stooq from './providers/stooq.js';
import { observedQuote, servedQuote } from './quoteStatus.js';
const handler=(marketRouter as any).stack.find((l:any)=>l.route?.path==='/quotes').route.stack[0].handle;
const row={symbol:'QUOTE-OBS',price:100,source:'nasdaq',marketState:'Closed',pe:1} as yahoo.Quote;
afterEach(()=>{vi.restoreAllMocks();vi.useRealTimers();});
async function request(metadata?:string) {
  const res={json:vi.fn(),status:vi.fn().mockReturnThis()} as unknown as Response;
  await handler({query:{symbols:'QUOTE-OBS',metadata}} as unknown as Request,res,()=>{});
  return vi.mocked(res.json).mock.calls[0][0];
}
it('preserves the quote clock over cache hits and failed refreshes, with old array clients unchanged',async()=>{
  vi.useFakeTimers();vi.setSystemTime(new Date('2026-10-16T12:00:00Z'));
  vi.spyOn(nasdaq,'quote').mockResolvedValue(row);
  const first=(await request('1'))[0];
  expect(first.observation).toMatchObject({cache_state:'fetched',market_state_basis:'provider'});
  vi.advanceTimersByTime(500);
  expect((await request())[0]).toEqual(row);
  expect((await request('1'))[0].observation).toEqual({...first.observation,cache_state:'cached'});
  vi.advanceTimersByTime(600);vi.mocked(nasdaq.quote).mockRejectedValue(new Error('offline'));
  vi.spyOn(yahoo,'quotes').mockRejectedValue(new Error('offline'));vi.spyOn(yahoo,'quoteFromChart').mockRejectedValue(new Error('offline'));vi.spyOn(stooq,'quote').mockRejectedValue(new Error('offline'));
  expect((await request('1'))[0].observation).toEqual({...first.observation,cache_state:'stale'});
  vi.mocked(nasdaq.quote).mockResolvedValue(row);
  const recovered=(await request('1'))[0];
  expect(recovered.observation.cache_state).toBe('fetched');expect(recovered.observation.fetched_at).not.toBe(first.observation.fetched_at);
});
it('does not certify a hardcoded Binance Open state or invent clocks on legacy cache entries',()=>{
  expect(observedQuote({...row,source:'binance',marketState:'Open'}).observation?.market_state_basis).toBe('UNVERIFIED');
  expect(servedQuote(row,'stale').observation).toBeUndefined();
});
