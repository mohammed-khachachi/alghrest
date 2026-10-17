import { terminalResearch, type TerminalResearch } from './terminalResearch';
import { compareResearch, priorSnapshot, type ResearchSnapshot } from './researchJournal';
import { terminalDataStatus } from './terminalDataStatus';
import { summaryNumber } from './terminalSummary';
import { terminalSymbol } from './terminalBridge';
import { qualityAnalysis } from './terminalQuality';

export type BatchEvent<T> = { symbol: string; phase: 'loading' | 'skipped' }
  | { symbol: string; phase: 'done'; value: T }
  | { symbol: string; phase: 'error'; error: string };

/** Two bounded workers; a failed item cannot abort other symbols. Stop drains in-flight work. */
export async function watchlistBatch<T>(symbols: string[], load: (symbol: string) => Promise<T>,
  notify: (event: BatchEvent<T>) => void, stopped: () => boolean = () => false) {
  if (symbols.length > 50 || new Set(symbols).size !== symbols.length
    || symbols.some(s => terminalSymbol(s) !== s)) throw new Error('قائمة رموز غير صالحة.');
  let cursor = 0;
  async function worker() {
    while (cursor < symbols.length) {
      const symbol = symbols[cursor++];
      if (stopped()) { notify({symbol, phase: 'skipped'}); continue; }
      notify({symbol, phase: 'loading'});
      let event: BatchEvent<T>;
      try { event = {symbol, phase: 'done', value: await load(symbol)}; }
      catch { event = {symbol, phase: 'error', error: 'تعذر الحصول على قراءة صالحة. أعد المحاولة لهذا الرمز.'}; }
      notify(event);
    }
  }
  await Promise.all([worker(), worker()]);
}

export type OverviewEntry = {
  history: ResearchSnapshot[] | null; historyError: string; reading: TerminalResearch | null;
  phase: 'idle' | 'queued' | 'loading' | 'done' | 'error' | 'skipped'; error: string;
};
export function emptyOverviewEntry(): OverviewEntry {
  return {history: null, historyError: '', reading: null, phase: 'idle', error: ''};
}
const trends = {above_averages: 'ترتيب صاعد', below_averages: 'ترتيب هابط', mixed: 'مختلط', insufficient: 'غير كافٍ'};

export function overviewReading(symbol: string, entry: OverviewEntry, now: number) {
  const live = entry.reading && terminalResearch(entry.reading, symbol, now);
  const saved = entry.history?.find(s => s.report.symbol === symbol) ?? null;
  const report = live || saved?.report || null;
  const previous = report ? priorSnapshot(entry.history ?? [], report) : null;
  const comparison = report && previous ? compareResearch(report, previous.report) : null;
  const a = report ? qualityAnalysis(report) : null;
  const status = report ? terminalDataStatus(report, now) : [];
  return {
    report, previous, comparison, status,
    origin: live ? 'قراءة حالية' : saved ? 'لقطة محفوظة' : 'لا توجد قراءة',
    expired: !!entry.reading && !live,
    trend: a ? trends[a.trend] : 'غير متاح',
    momentum: a?.rsi14_simple == null ? 'غير متاح' : summaryNumber(a.rsi14_simple),
    volatility: a?.atr14_simple == null ? 'غير متاح' : `${summaryNumber(a.atr14_simple)} (${summaryNumber(Number(a.atr14_simple) / Number(a.last_close) * 100)}%)`,
    newHeadlines: comparison?.newsAvailable ? comparison.added.length : null,
    changed: comparison?.rows.filter(r => r.changed).length ?? null,
  };
}
