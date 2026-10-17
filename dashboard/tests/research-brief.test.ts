import test from 'node:test';
import assert from 'node:assert/strict';
import { researchBriefPDF } from '../src/lib/researchBrief';
import { setAccessToken } from '../src/lib/access';

const headers={'Content-Type':'application/pdf','Content-Disposition':'attachment; filename="ALGHREST-research-2026-10-16.pdf"'};
const pdf=()=>new Response('%PDF-1.7\nfixture\n%%EOF',{headers});
test('download uses authenticated local endpoint and original server filename',async()=>{
  setAccessToken('advisory','SYNTHETIC_TEST_TOKEN');
  const value=await researchBriefPDF(async (input,options)=>{
    assert.equal(input,'/assistant-api/research-brief.pdf');
    assert(!String(input).includes('TOKEN'));
    assert.equal(new Headers(options?.headers).get('Authorization'),'Bearer SYNTHETIC_TEST_TOKEN');
    assert(options?.signal);return pdf();
  });
  assert.equal(value.filename,'ALGHREST-research-2026-10-16.pdf');
  assert((await value.blob.text()).startsWith('%PDF-'));
  setAccessToken('advisory','');
});
test('server errors remain errors instead of becoming downloadable PDFs',async()=>{
  await assert.rejects(researchBriefPDF(async()=>new Response(JSON.stringify({detail:'No saved watchlist'}),{status:409,headers:{'Content-Type':'application/json'}})),/No saved watchlist/);
});
test('wrong MIME type and non-PDF content are rejected',async()=>{
  await assert.rejects(researchBriefPDF(async()=>new Response('html',{headers:{...headers,'Content-Type':'text/html'}})));
  await assert.rejects(researchBriefPDF(async()=>new Response('not pdf',{headers})));
});
test('unsafe or missing attachment filename is rejected',async()=>{
  for(const disposition of ['attachment; filename="../../bad.pdf"','inline','attachment; filename="x.html"'])
    await assert.rejects(researchBriefPDF(async()=>new Response('%PDF-1.7',{headers:{...headers,'Content-Disposition':disposition}})));
});
test('oversized streamed response is cancelled and not offered as a report',async()=>{
  let cancelled=false;
  const body=new ReadableStream<Uint8Array>({pull(controller){controller.enqueue(new Uint8Array(1024*1024));},cancel(){cancelled=true;}});
  await assert.rejects(researchBriefPDF(async()=>new Response(body,{headers})),/الحجم/);
  assert(cancelled);
});
test('network failure propagates for a retry without fabricating a report',async()=>{
  await assert.rejects(researchBriefPDF(async()=>{throw new Error('offline');}),/offline/);
});
