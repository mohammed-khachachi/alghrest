import { z } from 'zod';
import { accessHeaders } from './access';

export const MAX_BACKUP_BYTES=32*1024*1024;
const Result=z.object({sha256:z.string().regex(/^[a-f0-9]{64}$/),watches_in_file:z.number().int().min(0).max(50),
 snapshots_in_file:z.number().int().min(0).max(5000),watches_added:z.number().int().min(0).max(50),
 snapshots_added:z.number().int().min(0).max(5000),snapshots_unchanged:z.number().int().min(0).max(5000)}).strict();
export type RestoreResult=z.infer<typeof Result>;
export async function researchBackupDownload(fetcher:typeof fetch=fetch) {
 const response=await fetcher('/assistant-api/research-backup',{headers:accessHeaders('advisory'),signal:AbortSignal.timeout(60000)});
 if(!response.ok || response.headers.get('Content-Type')?.split(';')[0]!=='application/json') throw new Error('تعذر تنزيل نسخة البحث.');
 const reader=response.body?.getReader();if(!reader) throw new Error('ملف النسخة غير متاح.');
 let size=0;const chunks:BlobPart[]=[];
 try{while(true){const {done,value}=await reader.read();if(done)break;size+=value.byteLength;if(size>MAX_BACKUP_BYTES)throw new Error('تجاوزت النسخة حد 32 ميغابايت.');chunks.push(value);}}
 catch(error){await reader.cancel().catch(()=>{});throw error;}finally{reader.releaseLock();}
 const blob=new Blob(chunks,{type:'application/json'});
 return {blob,filename:`ALGHREST-research-backup-${new Date().toISOString().slice(0,10)}.json`};
}
export async function researchRestore(raw:string,preview:boolean,fetcher:typeof fetch=fetch):Promise<RestoreResult> {
 if(new TextEncoder().encode(raw).length>MAX_BACKUP_BYTES)throw new Error('تجاوز الملف حد 32 ميغابايت.');
 const response=await fetcher(`/assistant-api/research-backup/${preview?'preview':'restore'}`,{method:'POST',
 headers:{...accessHeaders('advisory'),'Content-Type':'application/json','X-Advisory-Client':'dashboard'},body:raw,signal:AbortSignal.timeout(60000)});
 if(!response.ok)throw new Error('تعذر اعتماد النسخة أو دمجها؛ السجل الحالي محفوظ.');
 return Result.parse(await response.json());
}
