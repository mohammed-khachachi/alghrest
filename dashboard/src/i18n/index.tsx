'use client';
import { useEffect, useSyncExternalStore } from 'react';
import { getLanguage, initializeLanguage, setLanguage, subscribeLanguage } from './core';
export { tr, formatMessage, languageDirection, currentLocale } from './core';

export function useLanguage() {
  const language = useSyncExternalStore(subscribeLanguage, getLanguage, () => 'ar' as const);
  useEffect(initializeLanguage, []);
  return language;
}

export function LanguageSwitch() {
  const language = useLanguage();
  return <label dir="ltr" className="inline-flex shrink-0 items-center gap-2 rounded border border-white/20 px-2 py-1 text-xs text-white" style={{background:'#111827'}}>
    <span aria-hidden="true">🌐</span>
    <select aria-label="Language / اللغة" value={language} onChange={event => { const next = event.target.value as 'en' | 'ar'; setLanguage(next); window.dispatchEvent(new CustomEvent('alghrest:language-choice', {detail: next})); }} style={{background:'#111827',color:'white'}}>
      <option value="ar">العربية</option>
      <option value="en">English</option>
    </select>
  </label>;
}
