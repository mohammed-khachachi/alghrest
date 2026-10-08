"use client";
import { useRef, useEffect, useState } from "react";
import { ArrowLeft, ArrowRight, X, Maximize2 } from "lucide-react";
import { DecisionOrbit } from "./decision-orbit";
import { stages, modes, roadmap, type Lang } from "@/lib/site-content";
import type { ProjectSummary } from "@/lib/project";
export function Presentation({ language, project }: { language:Lang; project:ProjectSummary }) {
 const dialog=useRef<HTMLDialogElement>(null),previousOverflow=useRef(""),[page,setPage]=useState(0),[stage,setStage]=useState(0);
 const t=(ar:string,fr:string)=>language==="ar"?ar:fr;
 const chapters=[t("فكرة المشروع","Le projet"),t("مسار القرار","Le parcours"),t("البنية","Architecture"),t("مصادر البيانات","Provenance"),t("أدلة الجودة","Preuves techniques"),t("حدود الجاهزية","Limites"),t("خطة التطوير","Développement"),t("القرار يبقى للإنسان","L’humain décide")];
 useEffect(()=>{
  const element=dialog.current;
  const handle=(event:KeyboardEvent)=>{
   if(!element?.open)return;
   if(event.key==="ArrowLeft"||event.key==="ArrowRight"){
    event.preventDefault(); const next=language==="ar"?event.key==="ArrowLeft":event.key==="ArrowRight";
    setPage(p=>Math.max(0,Math.min(7,p+(next?1:-1))));
   }
  };
  window.addEventListener("keydown",handle); return()=>window.removeEventListener("keydown",handle);
 },[language]);
 function open(){setPage(0);previousOverflow.current=document.body.style.overflow;document.body.style.overflow="hidden";dialog.current?.showModal();}
 function close(){dialog.current?.close();}
 return <>
  <button className="present-button" onClick={open}><Maximize2 size={16}/><span>{t("وضع العرض","Présenter")}</span></button>
  <dialog ref={dialog} className="presentation" aria-labelledby="presentation-title" onClose={()=>{document.body.style.overflow=previousOverflow.current;}} onClick={e=>{if(e.target===dialog.current)close();}}>
   <div className="presentation-inner">
    <div className="presentation-top"><span className="mono">ALGHREST / PROJECT BRIEF</span><button className="icon-button" onClick={close} aria-label={t("إغلاق العرض","Fermer")}><X/></button></div>
    <div className="presentation-body" key={page}><p className="eyebrow"><bdi dir="ltr">{String(page+1).padStart(2,"0")} / 08</bdi></p><h2 id="presentation-title">{chapters[page]}</h2>
     {page===0&&<><p className="presentation-headline">{t("الذكاء يقرأ. القواعد تتحقق. أنت تقرر.","L’intelligence analyse. Les règles vérifient. Vous décidez.")}</p><p>{t("منصة بحث ودعم قرار متعددة الأسواق، بملف TCP25 استشاري فقط.","Recherche et aide à la décision multi-marchés. Profil TCP25 consultatif uniquement.")}</p></>}
     {page===1&&<div className="present-flow">{stages.map((s,i)=><div key={s.code}><span className="mono">{i+1} / {s.code}</span><h3>{s.title[language]}</h3><p>{s.detail[language]}</p></div>)}</div>}
     {page===2&&<div className="present-flow">{modes.map(m=><div key={m.id}><span className="mono">{m.tag}</span><h3>{m.title[language]}</h3><p>{m.desc[language]}</p></div>)}</div>}
     {page===3&&<><p className="presentation-headline">{t("حقيقية عند ثبوت المصدر. مصطنعة حين تكون محاكاة.","Réelles si la provenance est prouvée. Synthétiques si simulées.")}</p><p>{t("Mock ومزودات الواجهة مصطنعة. قراءات crypto والأخبار قد تكون فعلية عند الاتصال. العقود المستقبلية تحتاج استيرادًا موثقًا. HMM قد يتحول إلى بديل مصطنع.","Mock et fournisseurs UI sont simulés. Crypto/RSS peuvent être réels si connectés. Futures : import documenté. HMM : repli synthétique possible.")}</p></>}
     {page===4&&<><div className="present-metrics"><strong>{project.evidence?.passed.toLocaleString("en-US")??"—"}</strong><strong>{project.evidence?project.evidence.coverage+"%":"—"}</strong></div><p>{t("اختبارات ناجحة وتغطية مجمعة وفق دليل محلي في README. ليست نتائج تداول أو نجاح CI مستضاف.","Tests réussis et couverture d’après une preuve locale du README. Aucun résultat de trading ou succès CI hébergé implicite.")}</p><p className="small-copy">{t("اختبارات الخدمات الاختيارية المتجاوزة: ","Opt-ins externes non exécutés : ")}{project.evidence?.skipped??"—"} · {project.evidence?.date??"UNKNOWN"}</p></>}
     {page===5&&<><p className="presentation-headline">{t("أساس قابل للفحص. جاهزية مالية لم تثبت بعد.","Fondations inspectables. Validation financière encore à démontrer.")}</p><p>{t("الميزة الموجبة خارج العينة، محاكاة التقييم الدقيقة، احتمال الاجتياز والتقييمات الورقية الكاملة تبقى بوابات تطوير.","Espérance positive OOS, simulation exacte, probabilité de réussite et évaluations paper complètes restent des critères à satisfaire.")}</p></>}
     {page===6&&<div className="present-flow">{roadmap.map(r=><div key={r.number}><span className="mono">{r.number}</span><h3>{r.title[language]}</h3><p>{r.body[language]}</p></div>)}</div>}
     {page===7&&<div className="present-end"><p className="presentation-headline">{t("بيانات واضحة. مخاطرة حتمية. قرار موثّق.","Données explicites. Risque déterministe. Décision documentée.")}</p><DecisionOrbit active={stage} onSelect={setStage} language={language}/></div>}
    </div>
    <div className="presentation-controls"><button className="button ghost" disabled={page===0} onClick={()=>setPage(p=>p-1)}>{language==="ar"?<ArrowRight size={18}/>:<ArrowLeft size={18}/>} {t("السابق","Précédent")}</button><div className="presentation-dots">{chapters.map((c,i)=><button key={c} aria-label={c} aria-current={page===i?"step":undefined} onClick={()=>setPage(i)} className={page===i?"active":""}/>)}</div><button className="button primary" disabled={page===7} onClick={()=>setPage(p=>p+1)}>{t("التالي","Suivant")} {language==="ar"?<ArrowLeft size={18}/>:<ArrowRight size={18}/>}</button></div>
   </div>
  </dialog>
 </>;
}
