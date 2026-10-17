/** Bounded, process-local observations. Never log raw errors, URLs, headers or tokens. */
export type Feed = 'quotes' | 'history' | 'news';
export type Provider = 'nasdaq' | 'yahoo' | 'yahoo-chart' | 'stooq' | 'binance' | 'fred' | 'yahoo-rss' | 'google-rss';
export type ProviderClock = { value: string; basis: 'provider_text_unconverted' | 'ticker_window_close' | 'daily_close_date' };
type Observation = { symbol:string; feed:Feed; provider:Provider; state:'available'|'unavailable';
  last_attempt:string; last_success:string|null; last_failure:string|null;
  failure:'timeout'|'upstream_http'|'empty_response'|'provider_error'|null; http_status:number|null;
  clock:ProviderClock|null };
const started_at = new Date().toISOString();
const observations = new Map<string,Observation>();
const pending = new Map<string,Promise<unknown>>();
const MAX_ENTRIES = 400;

export function diagnosticSnapshot(symbol:string) {
  return {schema_version:'research-diagnostics-v1' as const, symbol, assessed_at:new Date().toISOString(),
    started_at, scope:'process_memory' as const,
    observations:[...observations.values()].filter(o=>o.symbol===symbol).map(o=>({...o}))};
}

/** Coalesce concurrent identical loads. A timeout records once; late results cannot overwrite it. */
export async function researchAttempt<T>(symbol:string, feed:Feed, provider:Provider, load:()=>Promise<T>, timeoutMs=4000, requestKey=""):Promise<T> {
  const key = `${symbol}:${feed}:${provider}`;
  const pendingKey=`${key}:${requestKey}`;
  const existing=pending.get(pendingKey);
  if(existing) return existing as Promise<T>;
  const task=(async()=>{
    let timer:ReturnType<typeof setTimeout>|undefined;
    const prior=observations.get(key);
    const row:Observation={symbol,feed,provider,state:'unavailable',last_attempt:new Date().toISOString(),
      last_success:prior?.last_success??null,last_failure:prior?.last_failure??null,
      failure:prior?.failure??null,http_status:prior?.http_status??null,clock:prior?.clock??null};
    try {
      const value=await Promise.race([Promise.resolve().then(load),new Promise<never>((_,reject)=>{
        timer=setTimeout(()=>reject(new DOMException('Provider timed out','TimeoutError')),timeoutMs);
      })]);
      const candidate=value as any;
      if(value==null || (feed!=="news" && Array.isArray(value)&&!value.length) || (feed==='quotes' && !Array.isArray(value) && !(Number(candidate.price)>0)))
        throw new Error('empty_response');
      row.state='available';row.last_success=new Date().toISOString();
      // Retain the last failure even after recovery: state describes the last attempt.
      row.clock=candidate.providerClock??null;
      return value;
    } catch(error) {
      const e=error instanceof Error?error:new Error();
      row.last_failure=new Date().toISOString();
      const code=e.message.match(/\b([45]\d{2})\b/)?.[1];
      row.http_status=code?Number(code):null;
      row.failure=['TimeoutError','AbortError'].includes(e.name)?'timeout':code?'upstream_http':e.message==='empty_response'||e.message.includes('empty history')?'empty_response':'provider_error';
      throw error;
    } finally {
      if(timer) clearTimeout(timer);
      observations.delete(key);observations.set(key,row);
      if(observations.size>MAX_ENTRIES) observations.delete(observations.keys().next().value!);
    }
  })();
  pending.set(pendingKey,task);
  try{return await task;} finally{if(pending.get(pendingKey)===task) pending.delete(pendingKey);}
}
