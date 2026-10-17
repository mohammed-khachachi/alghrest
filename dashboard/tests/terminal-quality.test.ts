import test from 'node:test';
import assert from 'node:assert/strict';
import { CandleQualitySchema, qualityAnalysis, qualityEvidence, qualityLabel, qualityReasons, type CandleQuality } from '../src/lib/terminalQuality';
import { terminalResearch, type TerminalResearch } from '../src/lib/terminalResearch';
import { terminalSummary } from '../src/lib/terminalSummary';
import { compareResearch, researchSnapshot } from '../src/lib/researchJournal';
import { emptyOverviewEntry, overviewReading } from '../src/lib/watchlistOverview';

const now = Date.parse('2026-10-16T12:00:00Z');
const stamp = new Date(now).toISOString();
function quality(): CandleQuality {
  return {schema_version:'candle-quality-v1',status:'usable',received_candles:80,invalid_candles:0,
    invalid_timestamps:0,duplicate_timestamps:0,out_of_order_pairs:0,future_timestamps:0,
    interval_seconds:3600,gap_count:0,missing_intervals:0,irregular_intervals:0,
    largest_gap_seconds:3600,continuity_basis:'continuous',reasons:[],
    trend:{allowed:true,reasons:[]},momentum:{allowed:true,reasons:[]},volatility:{allowed:true,reasons:[]}};
}
function fixture(): TerminalResearch {
  return {schema_version:'openterminal-research-v1',symbol:'BTC-USD',requested_range:'6M',assessed_at:stamp,
    quote:null,analysis:{count:80,first_time:'2026-10-13T04:00:00Z',last_time:'2026-10-16T11:00:00Z',
      last_close:'100',sma20:'90',sma50:'80',rsi14_simple:'60',atr14_simple:'2',recent20_low:'80',recent20_high:'110',
      trend:'above_averages',history_provider:'binance',interval:'1h',interval_basis:'provider_request',
      history_fetched_at:stamp,history_cache_state:'fetched'},data_quality:quality(),headlines:[],
    sources:[{kind:'quotes',state:'unavailable',received_at:stamp,response_sha256:null,reasons:[]},
      {kind:'news',state:'available',received_at:stamp,response_sha256:'a'.repeat(64),reasons:[]},
      {kind:'history',state:'available',received_at:stamp,response_sha256:'b'.repeat(64),reasons:[]}],
    freshness:'UNKNOWN',event_risk:'UNKNOWN',trade_permitted:false,execution_enabled:false};
}
function gapReport() {
  const r = fixture(), q = r.data_quality!;
  q.status='limited';q.reasons=['missing_intervals'];q.gap_count=q.missing_intervals=1;
  q.trend={allowed:false,reasons:['missing_intervals']};
  r.analysis!.sma20=r.analysis!.sma50=null;r.analysis!.trend='insufficient';
  return r;
}

test('quality counts are supported without claiming market freshness',()=>{
  const r=terminalResearch(fixture(),'BTC-USD',now)!;
  assert(r);assert.equal(qualityLabel(r.data_quality),'قابلة للاستخدام');
  assert.equal(r.freshness,'UNKNOWN');assert.equal(r.execution_enabled,false);
  assert.equal(qualityEvidence(r.data_quality!).find(([label])=>label==='أوقات مكررة')![1],'0');
});
test('unknown missing counts stay unknown rather than zero for session sources',()=>{
  const q=quality();q.status='limited';q.continuity_basis='session_unverified';q.reasons=['session_calendar_unverified'];
  q.missing_intervals=q.irregular_intervals=null;q.gap_count=2;
  assert(qualityEvidence(q).some(([label,value])=>label.includes('مفقودة') && value==='غير معلوم'));
  assert(qualityReasons(q).some(text=>text.includes('لا تثبت فقد')));
});
test('summary explains blocked trend while recent momentum and volatility remain descriptive',()=>{
  const r=gapReport();assert(terminalResearch(r,'BTC-USD',now));
  const rows=terminalSummary(r);
  assert(rows[0].explanation.includes('حُجب'));assert(rows[0].evidence.includes('مفقودة'));
  assert(rows[1].explanation.includes('يميل للصعود'));assert(rows[2].explanation.includes('2%'));
});
test('quality mask protects every metric consumer without mutating saved data',()=>{
  const r=gapReport();r.analysis!.sma20='90';r.analysis!.sma50='80';r.analysis!.trend='above_averages';
  const original=JSON.stringify(r);
  assert.equal(qualityAnalysis(r)!.sma50,null);
  assert(terminalSummary(r)[0].explanation.includes('حُجب'));
  assert.equal(JSON.stringify(r),original);
  assert.equal(terminalResearch(r,'BTC-USD',now),null);
});
test('watchlist and comparisons suppress a blocked trend rather than recovering raw metrics',()=>{
  const r=gapReport();
  const row=overviewReading('BTC-USD',{...emptyOverviewEntry(),reading:r},now);
  assert.equal(row.trend,'غير كافٍ');assert.equal(row.momentum,'60');
  const previous=fixture();previous.assessed_at='2026-10-16T11:59:00Z';
  const comparison=compareResearch(r,previous);
  assert.equal(comparison.rows.find(row=>row.label==='متوسط 50')!.after,'غير متاح');
  assert(comparison.rows.some(row=>row.label==='جودة الشموع' && row.changed));
});
test('missing and future timestamps cannot be declared usable, nor can blocked reasons allow conclusions',()=>{
  for(const key of ['invalid_timestamps','future_timestamps','duplicate_timestamps','out_of_order_pairs'] as const) {
    const q=quality();q[key]=1;assert.equal(CandleQualitySchema.safeParse(q).success,false);
  }
  const q=quality();q.trend.reasons=['missing_intervals'];assert.equal(CandleQualitySchema.safeParse(q).success,false);
  assert.equal(CandleQualitySchema.safeParse({...quality(),status:'limited'}).success,false);
});
test('quality/analysis counts, schema, and stale eligibility cannot contradict each other',()=>{
  const r=fixture();r.data_quality!.received_candles=79;assert.equal(terminalResearch(r,'BTC-USD',now),null);
  const q=quality();q.status='limited';q.reasons=['stale_cache'];assert.equal(CandleQualitySchema.safeParse(q).success,false);
  assert.equal(CandleQualitySchema.safeParse({...quality(),schema_version:'invented'}).success,false);
  assert.equal(CandleQualitySchema.safeParse({...quality(),received_candles:20}).success,false);
  assert.equal(CandleQualitySchema.safeParse({...quality(),continuity_basis:'session_unverified'}).success,false);
  const inconsistent=fixture();inconsistent.analysis!.history_provider='yahoo';
  assert.equal(terminalResearch(inconsistent,'BTC-USD',now),null);
});
test('old snapshots remain readable with an explicit unassessed label and original clocks',()=>{
  const r=fixture();delete r.data_quality;
  const original=JSON.stringify(r);
  const saved=researchSnapshot({schema_version:'research-snapshot-v1',id:'a'.repeat(32),saved_at:stamp,report:r},'BTC-USD',now+86400000);
  assert.equal(saved.report.data_quality,undefined);
  assert(qualityLabel(saved.report.data_quality).includes('لم تُفحص'));
  assert.equal(saved.report.assessed_at,stamp);assert.equal(JSON.stringify(r),original);
  assert(terminalSummary(saved.report)[0].explanation.includes('يميل للصعود'));
});
