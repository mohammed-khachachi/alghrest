import test from 'node:test';
import assert from 'node:assert/strict';
import { setAccessToken } from '../src/lib/access';
import { MAX_BACKUP_BYTES,researchBackupDownload,researchRestore } from '../src/lib/researchBackup';
const result={sha256:'a'.repeat(64),watches_in_file:1,snapshots_in_file:2,watches_added:1,snapshots_added:1,snapshots_unchanged:1};
test('backup download authenticates locally and keeps credentials out of URLs and exported bytes',async()=>{
 setAccessToken('advisory','synthetic_backup_'+'x'.repeat(32));
 try {
  const fetcher:typeof fetch=async(input,options)=>{
    assert.equal(input,'/assistant-api/research-backup');assert(!String(input).includes('synthetic'));
    assert(new Headers(options?.headers).get('Authorization')?.startsWith('Bearer synthetic_backup_'));
    return new Response('{"schema_version":"research-backup-v1"}',{headers:{'Content-Type':'application/json'}});
  };
  const file=await researchBackupDownload(fetcher);assert((await file.blob.text()).includes('research-backup-v1'));assert(!((await file.blob.text()).includes('synthetic_backup_')));
 }finally{setAccessToken('advisory','');}
});
test('preview and restore send identical archive bytes to distinct protected endpoints',async()=>{
 const raw='{"fixture":"preserve these bytes"}';const paths:string[]=[];
 const fetcher:typeof fetch=async(input,options)=>{paths.push(String(input));assert.equal(options?.body,raw);assert.equal(options?.method,'POST');assert.equal(new Headers(options?.headers).get('X-Advisory-Client'),'dashboard');return new Response(JSON.stringify(result));};
 assert.deepEqual(await researchRestore(raw,true,fetcher),result);assert.deepEqual(await researchRestore(raw,false,fetcher),result);
 assert.deepEqual(paths,['/assistant-api/research-backup/preview','/assistant-api/research-backup/restore']);
});
test('restore failures and malformed receipts are rejected without claiming success',async()=>{
 await assert.rejects(()=>researchRestore('{}',false,async()=>new Response('{}',{status:409})));
 for(const invalid of [{...result,sha256:'invalid'},{...result,snapshots_added:-1},{...result,extra:true}]) await assert.rejects(()=>researchRestore('{}',false,async()=>new Response(JSON.stringify(invalid))));
});
test('oversized restore is rejected before sending and a bad download type is refused',async()=>{
 let called=false;await assert.rejects(()=>researchRestore('x'.repeat(MAX_BACKUP_BYTES+1),false,async()=>{called=true;return new Response('{}');}));assert.equal(called,false);
 await assert.rejects(()=>researchBackupDownload(async()=>new Response('<html/>',{headers:{'Content-Type':'text/html'}})));
});
test('streaming download limit cancels an oversized source instead of creating a partial backup',async()=>{
 let cancelled=false,count=0;
 const stream=new ReadableStream<Uint8Array>({pull(controller){if(count++<32)controller.enqueue(new Uint8Array(1024*1024));else controller.enqueue(new Uint8Array(1));},cancel(){cancelled=true;}});
 await assert.rejects(()=>researchBackupDownload(async()=>new Response(stream,{headers:{'Content-Type':'application/json'}})));assert.equal(cancelled,true);
});
