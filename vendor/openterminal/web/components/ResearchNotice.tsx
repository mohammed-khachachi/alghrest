'use client';
import { tr, useLanguage } from '../i18n';

export default function ResearchNotice() {
  useLanguage();
  return <div role="status" style={{padding:'8px 12px',background:'#241b08',color:'#fcd34d',fontSize:12,flexShrink:0}}>
    {tr('ALGHREST Research · Public prices may be delayed or indicative. Portfolio entries are a separate manual journal.')}{' '}
    <a href="http://127.0.0.1:5173/assistant" target="_top" style={{textDecoration:'underline'}}>{tr('Return to ALGHREST')}</a>
  </div>;
}
