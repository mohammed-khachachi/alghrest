import {afterEach,expect,it,vi} from 'vitest';
import * as binance from './binance.js';
import * as nasdaq from './nasdaq.js';
import * as fred from './fred.js';
afterEach(()=>vi.unstubAllGlobals());
it('labels Binance window close separately from an unknown last-trade clock',async()=>{
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:true,json:async()=>({lastPrice:'100',closeTime:1792152000000})}));
  const q=await binance.quote('BTC');expect(q.time).toBeNull();
  expect(q.providerClock).toEqual({value:new Date(1792152000000).toISOString(),basis:'ticker_window_close'});
});
it('preserves Nasdaq ET text without guessing an offset',async()=>{
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:true,json:async()=>({data:{primaryData:{lastSalePrice:'$100',lastTradeTimestamp:'Oct 16, 2026 3:57 PM ET'}}})}));
  const q=await nasdaq.quote('CLOCKTEST');expect(q.time).toBeNull();
  expect(q.providerClock).toEqual({value:'Oct 16, 2026 3:57 PM ET',basis:'provider_text_unconverted'});
});
it('never turns missing FRED cells into a zero price and requests a bounded fetch',async()=>{
  const fetchMock=vi.fn().mockResolvedValue({ok:true,text:async()=>'DATE,VIXCLS\n2026-10-15,\n2026-10-14,.\n2026-10-13,18.5\n'});vi.stubGlobal('fetch',fetchMock);
  expect(await fred.series('VIXCLS')).toEqual([{date:'2026-10-13',value:18.5}]);
  expect(fetchMock.mock.calls[0][1].signal).toBeInstanceOf(AbortSignal);
});
