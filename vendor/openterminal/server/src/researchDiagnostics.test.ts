import {afterEach,expect,it,vi} from 'vitest';
import {diagnosticSnapshot,researchAttempt} from './researchDiagnostics.js';
afterEach(()=>vi.useRealTimers());
it('keeps successful request time on failure and strips raw provider secrets',async()=>{
  await researchAttempt('DIAG','history','yahoo',async()=>[1]);
  const original=diagnosticSnapshot('DIAG').observations[0].last_success;
  await expect(researchAttempt('DIAG','history','yahoo',async()=>{throw new Error('https://example.org?token=SECRET 429')})).rejects.toThrow();
  const result=diagnosticSnapshot('DIAG');
  expect(result.observations[0]).toMatchObject({state:'unavailable',last_success:original,failure:'upstream_http',http_status:429});
  expect(JSON.stringify(result)).not.toContain('SECRET');
  await researchAttempt('DIAG','history','yahoo',async()=>[2]);
  expect(diagnosticSnapshot('DIAG').observations[0]).toMatchObject({state:'available',failure:'upstream_http'});
});
it('times out, coalesces concurrent loads and ignores late completion',async()=>{
  vi.useFakeTimers();let resolve!:(v:number[])=>void;
  const load=vi.fn(()=>new Promise<number[]>(r=>{resolve=r}));
  const first=researchAttempt('SLOW','history','fred',load,20);
  const second=researchAttempt('SLOW','history','fred',load,20);
  const assertions=Promise.all([expect(first).rejects.toThrow(),expect(second).rejects.toThrow()]);
  await vi.advanceTimersByTimeAsync(21);await assertions;
  resolve([1]);await Promise.resolve();
  expect(load).toHaveBeenCalledTimes(1);
  expect(diagnosticSnapshot('SLOW').observations[0]).toMatchObject({state:'unavailable',failure:'timeout',last_success:null});
});
it('isolates symbols and rejects empty or missing quote prices',async()=>{
  await expect(researchAttempt('EMPTY','history','yahoo',async()=>[])).rejects.toThrow();
  await expect(researchAttempt('EMPTY','quotes','nasdaq',async()=>({price:null}))).rejects.toThrow();
  expect(diagnosticSnapshot('UNOBSERVED').observations).toEqual([]);
});
it('records an empty news response as a successful request, without claiming headline coverage',async()=>{
  await expect(researchAttempt('NEWS','news','yahoo-rss',async()=>[])).resolves.toEqual([]);
  expect(diagnosticSnapshot('NEWS').observations[0]).toMatchObject({state:'available',feed:'news',provider:'yahoo-rss'});
});
it('does not coalesce two different history ranges into the same candle series',async()=>{
  const load=vi.fn().mockResolvedValue([1]);
  await Promise.all([researchAttempt('RANGES','history','yahoo',load,100,'1D'),researchAttempt('RANGES','history','yahoo',load,100,'6M')]);
  expect(load).toHaveBeenCalledTimes(2);
});
