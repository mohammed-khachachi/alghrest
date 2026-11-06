import { currentLocale } from '../i18n/core';
import type { TerminalResearch } from './terminalResearch';
import { qualityAnalysis, qualityReasonText } from './terminalQuality';

export type ResearchExplanation = { title: string; explanation: string; evidence: string };
export const summaryNumber = (value: string | number) => Number(value).toLocaleString(currentLocale(), {
  maximumSignificantDigits: 6,
});

/** Describes the validated snapshot only. No additional polling or model inference. */
export function terminalSummary(report: TerminalResearch): ResearchExplanation[] {
  const a = qualityAnalysis(report);
  const keys = ['trend', 'momentum', 'volatility'] as const;
  const titles = ['الاتجاه', 'الزخم', 'التذبذب'];
  function qualified(rows: ResearchExplanation[]) {
    return rows.map((row, index) => {
      const check = report.data_quality?.[keys[index]];
      return check && !check.allowed ? {...row,
        explanation: 'حُجب هذا الاستنتاج بسبب جودة بيانات الشموع.',
        evidence: check.reasons.map(r => qualityReasonText[r]).join(' '),
      } : row;
    });
  }
  if (!a) return qualified(titles.map(title => ({
    title, explanation: 'لا تتوفر شموع صالحة لهذه القراءة.', evidence: 'لا يمكن تكوين استنتاج من السعر وحده.',
  })));
  const n = summaryNumber;
  const close = Number(a.last_close);
  const trend: ResearchExplanation = {
    title: 'الاتجاه', explanation: 'البيانات غير كافية لمقارنة المتوسطين؛ نحتاج 50 شمعة.',
    evidence: `المتاح ${a.count} شمعة · الإغلاق الأخير ${n(close)}.`,
  };
  if (a.sma20 !== null && a.sma50 !== null) {
    const fast = Number(a.sma20), slow = Number(a.sma50);
    trend.explanation = close > fast && fast > slow
      ? 'ترتيب الأسعار يميل للصعود: الإغلاق أعلى من متوسط 20 شمعة، وهذا المتوسط أعلى من متوسط 50 شمعة.'
      : close < fast && fast < slow
        ? 'ترتيب الأسعار يميل للهبوط: الإغلاق أدنى من متوسط 20 شمعة، وهذا المتوسط أدنى من متوسط 50 شمعة.'
        : 'الصورة مختلطة: الإغلاق والمتوسطان لا يتفقان على ترتيب صاعد أو هابط.';
    trend.evidence = `الإغلاق ${n(close)} · متوسط 20: ${n(fast)} · متوسط 50: ${n(slow)} · المسافة عن متوسط 20: ${n((close / fast - 1) * 100)}%.`;
  }
  const momentum: ResearchExplanation = {
    title: 'الزخم', explanation: 'نحتاج 15 شمعة على الأقل لمقارنة آخر 14 تغيرًا في الإغلاق.',
    evidence: `المتاح ${a.count} شمعة · RSI غير متاح.`,
  };
  if (a.rsi14_simple !== null) {
    const rsi = Number(a.rsi14_simple);
    momentum.explanation = rsi > 50
      ? 'مجموع الارتفاعات أكبر من مجموع الانخفاضات في آخر 14 تغيرًا؛ الزخم يميل للصعود في هذه العينة.'
      : rsi < 50
        ? 'مجموع الانخفاضات أكبر من مجموع الارتفاعات في آخر 14 تغيرًا؛ الزخم يميل للهبوط في هذه العينة.'
        : 'الارتفاعات والانخفاضات متوازنة، أو لم يتغير الإغلاق؛ لا غلبة لاتجاه في هذه العينة.';
    momentum.evidence = `RSI 14 = ${n(rsi)} من 100 · متوسط بسيط · نقطة المقارنة 50. هذه قراءة للتغيرات الماضية وليست توقعًا للانعكاس.`;
  }
  const volatility: ResearchExplanation = {
    title: 'التذبذب', explanation: 'نحتاج 15 شمعة على الأقل لقياس متوسط الحركة خلال آخر 14 شمعة.',
    evidence: `المتاح ${a.count} شمعة · ATR غير متاح.`,
  };
  if (a.atr14_simple !== null) {
    const atr = Number(a.atr14_simple);
    volatility.explanation = `بلغ متوسط النطاق الحقيقي ${n(atr)} بوحدة سعر الشموع، أي ${n(atr / close * 100)}% من الإغلاق الأخير. يشمل نطاق الشمعة والفجوة عن الإغلاق السابق.`;
    volatility.evidence = `ATR 14 بمتوسط بسيط · الإغلاق ${n(close)}. لا توجد مقارنة تاريخية لتصنيفه مرتفعًا أو منخفضًا، ولا يدل على اتجاه الحركة.`;
  }
  return qualified([trend, momentum, volatility]);
}

function containsTerm(title: string, term: string, sensitive = false) {
  const escaped = term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return new RegExp(`(?:^|[^\\p{L}\\p{N}])${escaped}(?=$|[^\\p{L}\\p{N}])`, sensitive ? 'u' : 'iu').test(title);
}

/** Conservative title match, not a claim that an article was read or caused a move. */
export function headlineMentionsSymbol(title: string, report: TerminalResearch) {
  if (containsTerm(title, report.symbol, report.symbol.length <= 2)) return true;
  const name = report.quote?.name?.replace(/\b(common stock|ordinary shares|class [a-z]|incorporated|inc|corporation|corp|limited|ltd|plc|holdings)\b.*$/i, '').replace(/[.,\s]+$/g, '').trim();
  return !!name && name.length >= 3 && !/^(the|company|stock|index|fund|etf)$/i.test(name)
    && containsTerm(title, name);
}

export function researchHeadlines(report: TerminalResearch) {
  const ranked = report.headlines.map(headline => ({
    ...headline, mentionsSymbol: headlineMentionsSymbol(headline.title, report),
  })).sort((a, b) => Number(b.mentionsSymbol) - Number(a.mentionsSymbol)
    || (b.published_at ? Date.parse(b.published_at) : 0) - (a.published_at ? Date.parse(a.published_at) : 0));
  return { selected: ranked.slice(0, 3), matching: ranked.filter(h => h.mentionsSymbol).length };
}

/** A reading cue based on title words, not a summary of the unseen article. */
export function headlineReadingCue(title: string) {
  if (/\b(earnings|revenue|profit|results)\b|أرباح|إيرادات|نتائج مالية/i.test(title))
    return 'العنوان يشير إلى نتائج أو أداء مالي؛ التفاصيل المهمة هي الأرقام الفعلية والفترة التي تغطيها ومقارنتها بالتوقعات.';
  if (/\b(launch|unveil|product|iphone|release)\w*\b|إطلاق|منتج/i.test(title))
    return 'العنوان يشير إلى منتج أو إطلاق؛ تحقق من موعده وهل يتضمن أرقام مبيعات فعلية أم توقعات.';
  if (/\b(analyst|price target|upgrade|downgrade|prediction|forecast)\w*\b|سعر مستهدف|محللين|توقعات/i.test(title))
    return 'العنوان يتناول رأيًا أو توقعًا؛ راجع صاحبه وافتراضاته وتاريخه، فالتوقع ليس نتيجة محققة.';
  if (/\b(stake|holdings|shares|position)\b|حصة|ملكية/i.test(title))
    return 'العنوان قد يتناول ملكية أو حيازات؛ راجع تاريخ الإفصاح وتاريخ التغير، فقد لا يمثل نشاط اليوم.';
  return 'لا يكفي العنوان لاستخلاص نتيجة؛ افتح المصدر لمعرفة ما حدث وتاريخه والأرقام التي يستند إليها.';
}
