import test from 'node:test';
import assert from 'node:assert/strict';
import type { TerminalResearch } from '../src/lib/terminalResearch';
import { terminalResearch } from '../src/lib/terminalResearch';
import { compareResearch, researchSnapshot, researchHistory, researchWatchlist, priorSnapshot } from '../src/lib/researchJournal';

const now = Date.parse('2026-10-15T12:00:00Z');
function report(offset = 0): TerminalResearch {
  const stamp = new Date(now + offset).toISOString();
  return {
    schema_version: 'openterminal-research-v1', symbol: 'AAPL', requested_range: '6M', assessed_at: stamp,
    quote: null, analysis: {count: 60, first_time: '2026-08-01T00:00:00Z', last_time: '2026-10-14T00:00:00Z', last_close: '100', sma20: '90', sma50: '80', rsi14_simple: '60', atr14_simple: '2', recent20_low: '70', recent20_high: '105', trend: 'above_averages', history_provider: 'yahoo', interval: '1d', interval_basis: 'provider_request', history_fetched_at: stamp, history_cache_state: 'fetched'},
    headlines: [], sources: (['quotes','history','news'] as const).map(kind => ({kind, state: 'available', received_at: stamp, response_sha256: 'a'.repeat(64), reasons: []})),
    freshness: 'UNKNOWN', event_risk: 'UNKNOWN', trade_permitted: false, execution_enabled: false,
  };
}
function saved(index = 1, offset = 0) {return {schema_version: 'research-snapshot-v1', id: index.toString(16).padStart(32,'0'), saved_at: new Date(now + offset).toISOString(), report: report(offset)};}
const headline = (title: string, url = 'https://example.org/story') => ({title,url,publisher: 'Fixture',published_at: '2026-10-14T10:00:00Z'});

test('historic snapshot remains readable while the same report expires as live research', () => {
  assert.equal(terminalResearch(report(),'AAPL',now+86400000),null);
  assert.equal(researchSnapshot(saved(),'AAPL',now+86400000).report.assessed_at, report().assessed_at);
});
test('snapshot refuses forged clocks, flags and wrong symbols', () => {
  for (const value of [saved(1,10000), {...saved(),report:{...report(),execution_enabled:true}}, {...saved(),saved_at:'2026-10-14T12:00:00Z'}, {...saved(),saved_at:'2026-10-15T12:02:00Z'}])
    assert.throws(() => researchSnapshot(value,'AAPL',now));
  assert.throws(() => researchSnapshot(saved(),'MSFT',now));
});
test('history rejects duplicates, mixed identities and out-of-order results', () => {
  assert.throws(() => researchHistory([saved(),saved()],'AAPL',now));
  assert.throws(() => researchHistory([saved(),saved(2,1000)],'AAPL',now+1000));
  assert.throws(() => researchHistory([{...saved(),report:{...report(),symbol:'MSFT'}}],'AAPL',now));
});
test('watchlist validates arbitrary terminal symbols and bounded unique records', () => {
  assert.equal(researchWatchlist([{symbol:'M&M.NS',snapshots:0,latest_saved_at:null}])[0].symbol,'M&M.NS');
  assert.throws(() => researchWatchlist([{symbol:'..',snapshots:0,latest_saved_at:null}]));
  const row={symbol:'AAPL',snapshots:0,latest_saved_at:null};
  assert.throws(() => researchWatchlist([row,row]));
});
test('comparison highlights trend, RSI and ATR changes with supporting numbers', () => {
  const old=report(), next=report(1000);
  Object.assign(next.analysis!,{trend:'mixed',rsi14_simple:'55',atr14_simple:'3'});
  const c=compareResearch(next,old);
  assert(c.comparable);
  assert.equal(c.rows.find(r=>r.label==='الاتجاه')!.changed,true);
  assert(c.rows.find(r=>r.label==='الزخم · RSI 14')!.note!.includes('-5'));
  assert.equal(c.rows.find(r=>r.label==='التذبذب · ATR 14')!.after,'3');
});
test('equivalent decimal text is unchanged and zero is not missing', () => {
  const old=report(),next=report(1000);old.analysis!.atr14_simple='0';next.analysis!.atr14_simple='0.00';
  const row=compareResearch(next,old).rows.find(r=>r.label==='التذبذب · ATR 14')!;
  assert.equal(row.changed,false);assert.equal(row.after,'0');
});
test('provider or unknown timeframe suppresses numerical delta without hiding separate values', () => {
  for (const changes of [{history_provider:'nasdaq'}, {interval:'UNVERIFIED',interval_basis:'UNVERIFIED'}]) {
    const next=report(1000);Object.assign(next.analysis!,changes);
    const c=compareResearch(next,report());assert.equal(c.comparable,false);
    assert(c.rows.find(r=>r.label==='الزخم · RSI 14')!.note!.includes('لا نحسب فرقًا'));
  }
});
test('missing history is a data loss, never a zero or directional market change', () => {
  const next=report(1000);next.analysis=null;next.sources[1].state='unavailable';next.sources[1].response_sha256=null;
  const c=compareResearch(next,report());
  assert.equal(c.rows.find(r=>r.label==='الإغلاق التاريخي')!.after,'غير متاح');
  assert.equal(c.rows.find(r=>r.label==='توفر الشموع')!.after,'غير متاح');
  assert.equal(c.comparable,false);
});
test('headlines distinguish added, no longer returned and edited URLs', () => {
  const old=report(),next=report(1000);
  old.headlines=[headline('Old title'),headline('Dropped','https://example.org/old')];
  next.headlines=[headline('Updated title'),headline('Added','https://example.org/new')];
  const c=compareResearch(next,old);
  assert.deepEqual(c.added.map(h=>h.title),['Added']);
  assert.deepEqual(c.removed.map(h=>h.title),['Dropped']);
  assert.deepEqual(c.updated.map(h=>h.title),['Updated title']);
});
test('news feed failure does not imply that every story disappeared', () => {
  const old=report(),next=report(1000);old.headlines=[headline('Keep')];next.sources[2].state='unavailable';
  const c=compareResearch(next,old);assert.equal(c.newsAvailable,false);assert.deepEqual(c.removed,[]);
});
test('symbol identity and assessment ordering are required for comparison', () => {
  assert.throws(()=>compareResearch({...report(),symbol:'MSFT'},report()));
  assert.throws(()=>compareResearch(report(),report(1000)));
});
test('baseline skips the same assessment and picks only an older snapshot of the symbol', () => {
  const records=researchHistory([saved(2,1000),saved()],'AAPL',now+2000);
  assert.equal(priorSnapshot(records,report(1000))!.id,saved().id);
  assert.equal(priorSnapshot(records,report()),null);
  assert.equal(priorSnapshot(records,{...report(2000),symbol:'MSFT'}),null);
});
test('stale cache transition is highlighted without changing the historical fetch clock', () => {
  const next=report(1000);next.analysis!.history_cache_state='stale';next.analysis!.history_fetched_at=report().analysis!.history_fetched_at;
  const row=compareResearch(next,report()).rows.find(r=>r.label==='حالة نسخة الشموع')!;
  assert(row.changed);assert(row.after.includes('تعثر'));
});
