import test from 'node:test';
import assert from 'node:assert/strict';
import type { TerminalResearch } from '../src/lib/terminalResearch';
import { terminalSummary, researchHeadlines, headlineMentionsSymbol, headlineReadingCue, summaryNumber } from '../src/lib/terminalSummary';

function fixture(): TerminalResearch {
  const stamp = '2026-10-15T12:00:00Z';
  return {
    schema_version: 'openterminal-research-v1', symbol: 'AAPL', requested_range: '6M', assessed_at: stamp,
    quote: {symbol: 'AAPL', name: 'Apple Inc. Common Stock', price: '999', change_percent: '2', currency: 'USD', provider: 'nasdaq', market_time: null},
    analysis: {count: 60, first_time: '2026-08-15T12:00:00Z', last_time: '2026-10-14T12:00:00Z', last_close: '100', sma20: '80', sma50: '70', rsi14_simple: '60', atr14_simple: '2', recent20_low: '70', recent20_high: '105', trend: 'above_averages', history_provider: 'nasdaq', interval: 'UNVERIFIED', interval_basis: 'UNVERIFIED', history_fetched_at: stamp, history_cache_state: 'cached'},
    headlines: [], sources: ['quotes', 'news', 'history'].map(kind => ({kind: kind as 'quotes' | 'news' | 'history', state: 'available', received_at: stamp, response_sha256: 'a'.repeat(64), reasons: []})),
    freshness: 'UNKNOWN', event_risk: 'UNKNOWN', trade_permitted: false, execution_enabled: false,
  };
}
test('trend explains the actual ordering and distance using historical close, not current quote', () => {
  const row = terminalSummary(fixture())[0];
  assert(row.explanation.includes('يميل للصعود'));
  assert(row.evidence.includes('25%'));
  assert(!row.evidence.includes('999'));
});
test('falling, mixed and equal averages do not reuse an optimistic trend label', () => {
  for (const [close, fast, slow, expected] of [['60','70','80','يميل للهبوط'], ['75','80','70','مختلطة'], ['80','80','80','مختلطة']]) {
    const r = fixture(); Object.assign(r.analysis!, {last_close: close, sma20: fast, sma50: slow});
    assert(terminalSummary(r)[0].explanation.includes(expected));
  }
});
test('short history retains available momentum while withholding the 50-candle trend', () => {
  const r = fixture(); Object.assign(r.analysis!, {count: 20, sma50: null});
  const rows = terminalSummary(r);
  assert(rows[0].explanation.includes('50 شمعة'));
  assert(rows[1].evidence.includes('60'));
});
test('missing history cannot turn a quote into a trend or volatility assessment', () => {
  const r = fixture(); r.analysis = null;
  assert(terminalSummary(r).every(row => row.explanation.includes('لا تتوفر')));
});
test('RSI boundaries describe gain/loss balance without reversal predictions', () => {
  for (const [rsi, expected] of [['0','يميل للهبوط'], ['49','يميل للهبوط'], ['50','لم يتغير'], ['51','يميل للصعود'], ['100','يميل للصعود']]) {
    const r = fixture(); r.analysis!.rsi14_simple = rsi;
    const row = terminalSummary(r)[1];
    assert(row.explanation.includes(expected));
    assert(row.evidence.includes('ليست توقعًا'));
  }
});
test('ATR percentage uses same-series historical close and preserves zero', () => {
  const r = fixture();
  assert(terminalSummary(r)[2].explanation.includes('2%'));
  r.analysis!.atr14_simple = '0';
  assert(terminalSummary(r)[2].explanation.includes('0%'));
  assert(terminalSummary(r)[2].evidence.includes('لا توجد مقارنة تاريخية'));
});
test('missing RSI and ATR remain missing and tiny nonzero figures are not rounded to zero', () => {
  const r = fixture(); r.analysis!.atr14_simple = r.analysis!.rsi14_simple = null;
  assert(terminalSummary(r)[1].evidence.includes('غير متاح'));
  assert(terminalSummary(r)[2].evidence.includes('غير متاح'));
  assert.notEqual(summaryNumber('0.0000000123'), summaryNumber(0));
});
test('headlines prioritize explicit identity then publication time and preserve original sources', () => {
  const r = fixture();
  r.headlines = ['Market moves', 'Apple earnings', 'AAPL product launch', 'Other news'].map((title,i) => ({title, url: `https://example.org/${i}`, publisher: 'Fixture Publisher', published_at: `2026-10-15T0${i}:00:00Z`}));
  const before = JSON.stringify(r.headlines);
  const news = researchHeadlines(r);
  assert.equal(news.matching, 2);
  assert.deepEqual(news.selected.map(h => h.title), ['AAPL product launch', 'Apple earnings', 'Other news']);
  assert.equal(news.selected[0].url, 'https://example.org/2');
  assert.equal(JSON.stringify(r.headlines), before);
});
test('title matching avoids substrings and ordinary lowercase words for short tickers', () => {
  const r = fixture();
  assert(headlineMentionsSymbol('Apple reports earnings', r));
  assert(!headlineMentionsSymbol('Pineapple demand', r));
  assert(!headlineMentionsSymbol('XAAPLX results', r));
  r.symbol = 'A'; r.quote = null;
  assert(!headlineMentionsSymbol('a market update', r));
  assert(headlineMentionsSymbol('$A results', r));
  r.symbol = 'M&M.NS';
  assert(headlineMentionsSymbol('M&M.NS earnings', r));
});
test('unknown identity and dates do not manufacture relevance or publication time', () => {
  const r = fixture(); r.quote = null;
  r.headlines = [{title: 'General market news', url: 'https://example.org/news', publisher: 'Fixture', published_at: null}];
  const news = researchHeadlines(r);
  assert.equal(news.matching, 0);
  assert.equal(news.selected[0].published_at, null);
  r.headlines = []; assert.equal(researchHeadlines(r).selected.length, 0);
});
test('headline reading cues distinguish reported topics from unverified article contents', () => {
  assert(headlineReadingCue('Apple earnings preview').includes('الفترة'));
  assert(headlineReadingCue('Apple product launch').includes('توقعات'));
  assert(headlineReadingCue('Analyst raises price target').includes('ليس نتيجة محققة'));
  assert(headlineReadingCue('MSFT forecasts a further 25% upside').includes('ليس نتيجة محققة'));
  assert(headlineReadingCue('Fund cuts holdings').includes('تاريخ الإفصاح'));
  assert(headlineReadingCue('General news').includes('لا يكفي العنوان'));
});
