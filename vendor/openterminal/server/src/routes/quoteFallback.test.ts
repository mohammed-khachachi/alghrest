import {afterEach,expect,it,vi} from 'vitest';
import type {Request,Response} from 'express';
import {marketRouter} from './market.js';
import * as nasdaq from '../providers/nasdaq.js';
import * as yahoo from '../providers/yahoo.js';
import * as stooq from '../providers/stooq.js';
afterEach(()=>vi.restoreAllMocks());
it('coalesces concurrent failed Yahoo batches without launching an unconsumed rejecting promise',async()=>{
 vi.spyOn(nasdaq,'quote').mockRejectedValue(new Error('offline'));
 const batch=vi.spyOn(yahoo,'quotes').mockRejectedValue(new Error('offline'));
 vi.spyOn(yahoo,'quoteFromChart').mockRejectedValue(new Error('offline'));
 vi.spyOn(stooq,'quote').mockRejectedValue(new Error('offline'));
 vi.spyOn(console,'error').mockImplementation(()=>{});
 const handler=(marketRouter as any).stack.find((l:any)=>l.route?.path==='/quotes').route.stack[0].handle;
 const response=()=>({json:vi.fn(),status:vi.fn().mockReturnThis()} as unknown as Response);
 const req={query:{symbols:'CONCURRENCY-TEST'}} as unknown as Request;
 await Promise.all([handler(req,response(),()=>{}),handler(req,response(),()=>{})]);
 expect(batch).toHaveBeenCalledTimes(1);
});
