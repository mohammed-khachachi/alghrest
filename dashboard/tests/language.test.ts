import test from 'node:test';
import { readdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import assert from 'node:assert/strict';
import { formatMessage, getLanguage, initializeLanguage, languageDirection, languageMessage, LANGUAGE_KEY, setLanguage, subscribeLanguage, tr, translateText } from '../src/i18n/core';
import { translateText as terminalTranslate } from '../../vendor/openterminal/web/i18n/core';
import dashboardMessages from '../src/i18n/messages.json';
import terminalMessages from '../../vendor/openterminal/web/i18n/messages.json';

test('shared bilingual entries stay identical while TCP25 copy stays dashboard-only', () => {
  for (const [key, pair] of Object.entries(terminalMessages)) assert.deepEqual(dashboardMessages[key as keyof typeof dashboardMessages], pair, key);
  const additions = Object.keys(dashboardMessages).filter(key => !(key in terminalMessages));
  assert.equal(additions.length, 15);
  for (const key of additions) {
    const pair = dashboardMessages[key as keyof typeof dashboardMessages];
    assert(pair.some(value => /TCP25|10 Micro|aggregate MES/.test(value)), key);
  }
  assert(Object.keys(dashboardMessages).length > 1400);
  for (const [key, pair] of Object.entries(dashboardMessages)) {
    assert.equal(pair.length, 2, key);
    assert(pair.every(value => value.trim().length > 0), key);
    const placeholders = (value: string) => [...value.matchAll(/\{(\d+)\}/g)].map(match => match[1]).sort();
    assert.deepEqual(placeholders(pair[0]), placeholders(pair[1]), key);
  }
});

test('known interface text switches in both directions, including research limitations', () => {
  assert.equal(translateText('مفتاح الوصول', 'en'), 'Access key');
  assert.equal(translateText('Overview', 'ar'), 'نظرة عامة');
  assert.equal(translateText('WATCHLIST', 'ar'), 'قائمة المتابعة');
  assert.equal(terminalTranslate('Return to ALGHREST', 'ar'), 'العودة إلى ALGHREST');
  assert.match(translateText('تحليل وصفي للبيانات المتاحة، دون تنفيذ أوامر. المؤشرات والأخبار لا تثبت فرصة رابحة أو اكتمال تغطية الأحداث.', 'en'), /without order execution.*do not establish/);
  assert.equal(translateText(' مفتاح الوصول ', 'en'), ' Access key ');
});

test('templates preserve numbers and symbols and can switch an already displayed result back', () => {
  setLanguage('en');
  const original = 'التحليل: BTC-USD · الشارت: AAPL';
  const english = tr(original);
  assert.equal(english, 'Analysis: BTC-USD · Chart: AAPL');
  setLanguage('ar');
  assert.equal(tr(english), original);
  setLanguage('en');
  assert.equal(formatMessage('اكتملت الاستعادة: أُضيفت {0} لقطة و{1} رموز؛ {2} لقطة موجودة دون تغيير.', [12, 3, 4]), 'Restore complete: added 12 snapshots and 3 symbols; 4 existing snapshots unchanged.');
  assert.equal(translateText('غير متاح · غير معلوم', 'en'), 'Unavailable · Unknown');
  const sourceValue = 'Original  source\nOverview · AAPL  \n';
  for (const translate of [translateText, terminalTranslate]) {
    assert.equal(translate(`Review declared: ${sourceValue}`, 'ar'), `مراجعة معلنة: ${sourceValue}`);
    assert.equal(translate(`مراجعة معلنة: ${sourceValue}`, 'en'), `Review declared: ${sourceValue}`);
    assert.equal(translate(sourceValue, 'ar'), sourceValue);
  }
});

test('unknown source prose, user notes, financial values and non-text objects remain intact', () => {
  setLanguage('en');
  for (const value of ['AAPL', 'MESZ26', '1234.5600', 'User note: keep  2 spaces', 'User note · Overview', 'عنوان خبر أصلي غير موجود في القاموس', 'constructor', '__proto__']) assert.equal(tr(value), value);
  const payload = { symbol: 'AAPL', execution_enabled: false, title: 'BUY' };
  assert.equal(tr(payload), payload);
  assert.equal(tr(50000), 50000);
  assert.equal(tr(null), null);
});

test('language messages accept only a known language and the exact two-field contract', () => {
  assert.equal(languageMessage({type:'alghrest:language',language:'en'}, 'alghrest:language'), 'en');
  assert.equal(languageMessage({type:'openterminal:language',language:'ar'}, 'openterminal:language'), 'ar');
  for (const data of [null, [], {type:'alghrest:language',language:'fr'}, {type:'other',language:'en'}, {type:'alghrest:language',language:'en',token:'test-only'}]) assert.equal(languageMessage(data, 'alghrest:language'), null);
});

test('saved language, document direction and subscriptions work without storing authentication', () => {
  const saved = new Map([[LANGUAGE_KEY, 'en']]);
  const html = {lang:'',dir:''};
  const events = new Map<string, (event: {key:string;newValue:string}) => void>();
  Object.defineProperty(globalThis, 'window', {configurable:true,value:{localStorage:{getItem:(key:string)=>saved.get(key),setItem:(key:string,value:string)=>saved.set(key,value)},addEventListener:(name:string, callback:(event:{key:string;newValue:string})=>void)=>events.set(name,callback)}});
  Object.defineProperty(globalThis, 'document', {configurable:true,value:{documentElement:html}});
  try {
    setLanguage('ar'); saved.set(LANGUAGE_KEY, 'en');
    let notifications=0;const unsubscribe=subscribeLanguage(()=>notifications++);
    initializeLanguage();
    assert.equal(getLanguage(),'en');assert.equal(html.lang,'en');assert.equal(html.dir,'ltr');
    setLanguage('ar'); assert.equal(languageDirection(),'rtl');assert.equal(html.dir,'rtl');
    assert.equal(saved.get(LANGUAGE_KEY),'ar');assert.equal(saved.size,1);
    assert.equal(notifications,2);
    events.get('storage')?.({key:LANGUAGE_KEY,newValue:'en'});
    assert.equal(getLanguage(),'en');assert.equal(html.dir,'ltr');
    unsubscribe();setLanguage('ar');assert.equal(notifications,3);
    Object.defineProperty(window,'localStorage',{get(){throw new Error('Storage blocked');}});
    assert.doesNotThrow(()=>setLanguage('en'));
    assert.equal(getLanguage(),'en');
  } finally { Reflect.deleteProperty(globalThis,'window');Reflect.deleteProperty(globalThis,'document'); }
});


test('translated select labels never replace stored enum values', () => {
  const walk = (directory: string): string[] => readdirSync(directory, {withFileTypes: true}).flatMap(entry => {
    const path = resolve(directory, entry.name);
    return entry.isDirectory() ? walk(path) : path.endsWith('.tsx') ? [path] : [];
  });
  // The test workflow runs from the repository root, as do the existing source audits.
  for (const file of [...walk(resolve('dashboard/src')), ...walk(resolve('vendor/openterminal/web/components'))]) {
    const source = readFileSync(file, 'utf8');
    for (const match of source.matchAll(/<option\b([^>]*)>([\s\S]*?)<\/option>/g)) {
      if (match[2].includes('tr(')) assert.match(match[1], /\bvalue=/, `${file}: translated option requires a stable value`);
    }
  }
});


test('TCP25 worksheet limits and retirement copy translate without changing historical limits', () => {
  const text = 'TCP25: $25,000 / $1,750 / $550 daily / $1,500 EOD. One Mini OR ten Micros, never both; this branch supports Micros only. Firm eligibility BLOCKED; qualified contracts 0.';
  const arabic = translateText(text, 'ar');
  assert.notEqual(arabic, text);
  for (const amount of ['$25,000', '$1,750', '$550', '$1,500']) assert(arabic.includes(amount));
  assert.equal(translateText(arabic, 'en'), text);
  assert.equal(translateText('10 عقد Micro', 'en'), '10 Micro contracts');
  assert.equal(translateText('20 عقد Micro', 'en'), '20 Micro contracts');
});


test('generated TCP25 notes translate from real serialized fixtures while user text stays original', () => {
  const raw = readFileSync(resolve('artifacts/earn2trade-tcp25-readiness/personal-worksheet-v2/synthetic-tcp25-status-v2.json'), 'utf8');
  const fixture = JSON.parse(raw);
  for (const note of [fixture.result.clock.note, fixture.result.note]) {
    const english = translateText(note, 'en');
    assert.notEqual(english, note);
    assert.equal(translateText(english, 'ar'), note);
  }
  const clock = translateText(fixture.result.clock.note, 'en');
  assert.match(clock, /15:50 Chicago/);
  assert.match(clock, /CME/);
  assert.equal(JSON.stringify(fixture), JSON.stringify(JSON.parse(raw)));
  const source = readFileSync(resolve('dashboard/src/components/advisory/EvaluationPanel.tsx'), 'utf8');
  assert(source.includes('{tr(status.clock.note)}'));
  assert(source.includes('{tr(status.note)}'));
  assert(source.includes('{s.notes}'));
  assert.doesNotMatch(source, /\{tr\(s\.notes\)\}/);
});

test('all explicit TCP25 validation errors have bilingual display messages', () => {
  const source = readFileSync(resolve('dashboard/src/lib/tcp25Personal.ts'), 'utf8');
  const errors = [...source.matchAll(/throw new Error\('([^']+)'\)/g)].map(match => match[1]);
  assert(errors.length >= 10);
  for (const error of errors) {
    const arabic = translateText(error, 'ar');
    const english = translateText(error, 'en');
    assert.notEqual(arabic, english, error);
    assert.equal(translateText(arabic, 'en'), english, error);
    assert.equal(translateText(english, 'ar'), arabic, error);
  }
  // Error.message avoids an untranslatable "Error: " prefix in the rendered catalog key.
  for (const file of ['components/advisory/EvaluationPanel.tsx', 'pages/ManualAssistant.tsx']) {
    const ui = readFileSync(resolve('dashboard/src', file), 'utf8');
    assert.doesNotMatch(ui, /setError\(String\(e\)\)/, file);
    assert(ui.includes('e instanceof Error ? e.message : String(e)'), file);
  }
});

test('dated breach labels translate independently without changing session dates', () => {
  const codes = ['daily_loss:2026-10-19', 'drawdown_boundary:2026-10-20'];
  const before = structuredClone(codes);
  for (const language of ['en', 'ar'] as const) {
    const labels = codes.map(code => translateText(code, language));
    assert.notEqual(labels[0], codes[0]);
    assert.notEqual(labels[1], codes[1]);
    assert(labels[0].includes('2026-10-19'));
    assert(labels[1].includes('2026-10-20'));
  }
  assert.deepEqual(codes, before);
});
