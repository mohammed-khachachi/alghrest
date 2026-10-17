import {afterEach,expect,it,vi} from 'vitest';
import type {Request,Response} from 'express';
import {marketRouter} from './market.js';
import * as news from '../providers/news.js';
import {diagnosticSnapshot} from '../researchDiagnostics.js';
afterEach(()=>vi.restoreAllMocks());
it('retains the individual RSS failure when another news source succeeds',async()=>{
 vi.spyOn(news,'symbolNews').mockRejectedValue(new Error('rss 429 https://example.org?key=SECRET'));
 vi.spyOn(news,'topNews').mockResolvedValue([]);
 const handler=(marketRouter as any).stack.find((l:any)=>l.route?.path==='/news').route.stack[0].handle;
 const res={json:vi.fn(),status:vi.fn().mockReturnThis()} as unknown as Response;
 await handler({query:{symbol:'NEWS-DIAGNOSTIC'}} as unknown as Request,res,()=>{});
 expect(res.json).toHaveBeenCalledWith([]);
 const d=diagnosticSnapshot('NEWS-DIAGNOSTIC');
 expect(d.observations).toEqual(expect.arrayContaining([expect.objectContaining({provider:'yahoo-rss',state:'unavailable',failure:'upstream_http'}),expect.objectContaining({provider:'google-rss',state:'available'})]));
 expect(JSON.stringify(d)).not.toContain('SECRET');
});
