import Link from "next/link";
import path from "node:path";
import { notFound } from "next/navigation";
import Markdown, { defaultUrlTransform } from "react-markdown";
import remarkGfm from "remark-gfm";
import { ArrowLeft, BookOpen, ExternalLink } from "lucide-react";
import { getProject } from "@/lib/project";
export const dynamic="force-dynamic";
export default async function DocumentPage({params,searchParams}:{params:Promise<{slug:string}>;searchParams:Promise<{lang?:string}>}){
 const [{slug},query,project]=await Promise.all([params,searchParams,getProject()]);
 const doc=project.docs.find(d=>d.slug===slug);if(!doc)notFound();
 const fr=query.lang==="fr";
 const rootUrl="https://github.com/mohammed-khachachi/alghrest/blob/main/";
 const transform=(url:string)=>{
  const safe=defaultUrlTransform(url);
  if(!safe||safe.startsWith("http")||safe.startsWith("mailto:"))return safe;
  if(safe.startsWith("#"))return rootUrl+doc.path+safe;
  const [target,hash]=safe.split("#");
  const resolved=path.posix.normalize(path.posix.join(path.posix.dirname(doc.path),target));
  const mapped=project.docs.find(d=>d.path===resolved);
  return mapped?"/docs/"+mapped.slug+(fr?"?lang=fr":""):rootUrl+resolved.split("/").map(encodeURIComponent).join("/")+(hash?"#"+hash:"");
 };
 return <div className="document-shell" dir={fr?"ltr":"rtl"} lang={fr?"fr":"ar"}><header className="document-header container"><Link className="wordmark" href={"/"+(fr?"?lang=fr":"")}>ALGHREST<span className="brand-dot">.</span></Link><Link className="text-link" href={"/"+(fr?"?lang=fr":"")+"#docs"}><ArrowLeft size={17}/>{fr?"Retour au projet":"العودة إلى المشروع"}</Link></header><main className="document-main container"><p className="eyebrow dark-eyebrow"><BookOpen size={15}/> README / SOURCE DOCUMENT</p><h1>{fr?doc.fr:doc.ar}</h1><p className="document-disclosure">{fr?"Document original du dépôt ; langue et terminologie conservées. Liens GitHub soumis à l’accès au dépôt privé.":"وثيقة المستودع الأصلية، بلغتها ومصطلحاتها. روابط GitHub تتطلب صلاحية الوصول للمستودع الخاص."}</p><div className="document-meta mono" dir="ltr"><span>{doc.path}</span><span>SHA256 / {doc.hash.slice(0,12)}</span></div><article className="prose" dir="auto"><Markdown remarkPlugins={[remarkGfm]} urlTransform={transform} components={{a:({href,children,...props})=><a href={href} {...props} target={href?.startsWith("http")?"_blank":undefined} rel={href?.startsWith("http")?"noreferrer":undefined}>{children}{href?.startsWith("http")&&<ExternalLink size={12} className="inline-icon"/>}</a>}}>{doc.markdown}</Markdown></article></main></div>;
}

