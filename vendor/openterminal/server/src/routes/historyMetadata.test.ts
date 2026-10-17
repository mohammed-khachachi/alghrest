import { afterEach, expect, it, vi } from 'vitest';
import type { Request, Response } from 'express';
import { marketRouter } from './market.js';
import * as nasdaq from '../providers/nasdaq.js';
import * as yahoo from '../providers/yahoo.js';
import * as stooq from '../providers/stooq.js';
import * as binance from '../providers/binance.js';
const candles = [{time:1,open:10,high:11,low:9,close:10,volume:5}];
const handler = (marketRouter as any).stack.find((l:any)=>l.route?.path==='/history/:symbol').route.stack[0].handle;
afterEach(()=>vi.restoreAllMocks());
async function request(symbol:string,metadata?:string) {
  const res = {json:vi.fn(),status:vi.fn().mockReturnThis()} as unknown as Response;
  await handler({params:{symbol},query:{range:'6M',metadata}} as unknown as Request,res,()=>{});
  return vi.mocked(res.json).mock.calls[0][0];
}
it('keeps original arrays for chart clients and reports the actual Nasdaq provider without guessing a timeframe',async()=>{
  vi.spyOn(nasdaq,'history').mockResolvedValue(candles);
  expect(await request('NASDAQ-STATUS')).toEqual(candles);
  const result=await request('NASDAQ-STATUS','1');
  expect(result.candles).toEqual(candles);
  expect(result.metadata).toMatchObject({symbol:'NASDAQ-STATUS',provider:'nasdaq',interval:null,interval_basis:'UNVERIFIED',cache_state:'cached'});
});
it('reports Yahoo and its requested interval after empty Nasdaq data',async()=>{
  vi.spyOn(nasdaq,'history').mockResolvedValue([]);
  const yahooSpy=vi.spyOn(yahoo,'history').mockResolvedValue(candles);
  const result=await request('YAHOO-STATUS','1');
  expect(result.metadata).toMatchObject({provider:'yahoo',interval:'1d',interval_basis:'provider_request'});
  expect(yahooSpy).toHaveBeenCalledWith('YAHOO-STATUS','6mo','1d');
});
it('reports the daily Stooq fallback, rather than the failed provider',async()=>{
  vi.spyOn(nasdaq,'history').mockRejectedValue(new Error('offline'));
  vi.spyOn(yahoo,'history').mockRejectedValue(new Error('offline'));
  vi.spyOn(stooq,'history').mockResolvedValue(candles);
  expect((await request('STOOQ-STATUS','1')).metadata).toMatchObject({provider:'stooq',interval:'1d'});
});
it('uses the same Binance timeframe configuration as its actual history request',async()=>{
  vi.spyOn(binance,'history').mockResolvedValue(candles);
  expect((await request('BTC','1')).metadata).toMatchObject({provider:'binance',interval:'4h'});
  expect(binance.historySettings('6M').interval).toBe('4h');
});

it('uses actual Yahoo OHLC for VIX instead of manufacturing candles from FRED daily closes',async()=>{
  const spy=vi.spyOn(yahoo,'history').mockResolvedValue(candles);
  const result=await request('VIX','1');
  expect(result.metadata).toMatchObject({symbol:'VIX',provider:'yahoo',interval:'1d'});
  expect(spy).toHaveBeenCalledWith('^VIX','6mo','1d');
  expect(result.candles).toEqual(candles);
});
it('uses genuine Stooq candles when the VIX Yahoo route fails, retaining the requested alias',async()=>{
  vi.spyOn(yahoo,'history').mockRejectedValue(new Error('429'));
  const stooqSpy=vi.spyOn(stooq,'history').mockResolvedValue(candles);
  const result=await request('^VIX','1');
  expect(result.metadata).toMatchObject({symbol:'^VIX',provider:'stooq',interval:'1d'});
  expect(stooqSpy).toHaveBeenCalledWith('^VIX');
});
