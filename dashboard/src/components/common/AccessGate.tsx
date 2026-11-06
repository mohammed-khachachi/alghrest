import { LanguageSwitch } from '../../i18n';

import { useLanguage, languageDirection, tr } from "../../i18n";
import { useState, type FormEvent } from 'react';
import { setAccessToken, type AccessScope } from '@/lib/access';

export function AccessGate({ scope, onReady }: { scope: AccessScope; onReady: () => void }) {
  useLanguage();
  const [token, setToken] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function connect(event: FormEvent) {
    event.preventDefault();
    setBusy(true); setError('');
    try {
      const response = await fetch(scope === 'api' ? '/api/symbols' : '/assistant-api/health', {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        signal: AbortSignal.timeout(10000),
      });
      if (!response.ok) throw new Error(response.status === 503 ? 'لم يُضبط مفتاح الوصول على الخادم.' : 'تعذر الدخول. تحقق من المفتاح والخدمة.');
      setAccessToken(scope, token); setToken(''); onReady();
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'تعذر الاتصال.'); }
    finally { setBusy(false); }
  }
  return <main dir={languageDirection()} className="min-h-screen bg-bg-dark text-white flex items-center justify-center p-6">
    <form onSubmit={connect} className="w-full max-w-md space-y-4">
      <div className="flex justify-end"><LanguageSwitch /></div>
      <h1 className="text-xl">{tr(scope === 'api' ? 'الدخول إلى لوحة التداول' : 'الدخول إلى المساعد')}</h1>
      <label className="block" htmlFor="access-token">{tr("مفتاح الوصول")}</label>
      <input id="access-token" dir="ltr" type="password" autoComplete="off" value={token} onChange={e => setToken(e.target.value)} className="w-full rounded bg-slate-800 p-3" />
      <p className="text-sm text-slate-400">{tr("يبقى المفتاح في ذاكرة الصفحة فقط. لكل خدمة مفتاح مستقل. خادم العرض التجريبي يقبل اتصالًا دون مفتاح.")}</p>
      {error && <p role="alert" className="text-red-400">{tr(error)}</p>}
      <button disabled={busy} className="rounded bg-blue-700 px-5 py-3 disabled:opacity-50">{tr(busy ? 'جارٍ التحقق…' : 'اتصال')}</button>
    </form>
  </main>;
}
