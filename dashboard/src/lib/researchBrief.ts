import { accessHeaders } from './access';

const MAX_PDF_BYTES = 12 * 1024 * 1024;

/** Download bytes only from the authenticated local API; no token in a URL. */
export async function researchBriefPDF(fetcher: typeof fetch = fetch): Promise<{blob: Blob; filename: string}> {
  const response = await fetcher('/assistant-api/research-brief.pdf', {
    headers: accessHeaders('advisory'), signal: AbortSignal.timeout(60000),
  });
  if (!response.ok) {
    const value: unknown = await response.json().catch(() => null);
    const message = value && typeof value === 'object' && 'detail' in value && typeof value.detail === 'string'
      ? value.detail : 'تعذر إنشاء التقرير. تحقق من قائمة المتابعة وأعد المحاولة.';
    throw new Error(message);
  }
  if (response.headers.get('Content-Type')?.split(';')[0].trim() !== 'application/pdf')
    throw new Error('لم يُرجع الخادم ملف PDF صالحًا.');
  const filename = response.headers.get('Content-Disposition')?.match(/filename="(ALGHREST-research-\d{4}-\d{2}-\d{2}\.pdf)"/)?.[1];
  if (!filename || !response.body) throw new Error('بيانات ملف التقرير غير صالحة.');
  const reader = response.body.getReader();
  const chunks: BlobPart[] = [];
  let size = 0;
  try {
    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > MAX_PDF_BYTES) throw new Error('تجاوز التقرير الحجم المسموح للتنزيل.');
      chunks.push(value);
    }
  } catch (error) { await reader.cancel().catch(() => {}); throw error; }
  finally { reader.releaseLock(); }
  const blob = new Blob(chunks, {type:'application/pdf'});
  if (await blob.slice(0,5).text() !== '%PDF-') throw new Error('محتوى التقرير لا يطابق PDF.');
  return {blob, filename};
}
