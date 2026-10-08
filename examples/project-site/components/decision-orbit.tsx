"use client";
import { stages, type Lang } from "@/lib/site-content";
export function DecisionOrbit({ active, onSelect, language }: { active:number; onSelect:(value:number)=>void; language:Lang }) {
 const positions = [[50,13],[82,31],[82,67],[50,85],[18,67],[18,31]];
 return <div className="decision-orbit">
  <svg viewBox="0 0 600 560" className="orbit-art" fill="none" aria-hidden="true">
   <defs><radialGradient id="glow"><stop stopColor="#d8f36a" stopOpacity=".13"/><stop offset="1" stopColor="#d8f36a" stopOpacity="0"/></radialGradient></defs>
   <circle cx="300" cy="275" r="240" fill="url(#glow)"/>
   <circle cx="300" cy="275" r="174" stroke="#d8f36a" strokeOpacity=".24" strokeDasharray="2 7" className="orbit-ring"/>
   <circle cx="300" cy="275" r="229" stroke="#d8f36a" strokeOpacity=".08"/>
   <circle cx="300" cy="275" r="109" stroke="#d8f36a" strokeOpacity=".12"/>
   {positions.map(([x,y],i)=><g key={i}><path d={"M300 275 L"+x*6+" "+y*5.6} stroke={i===active?"#d8f36a":"#577260"} strokeOpacity={i === active ? .7 : .23} strokeDasharray="3 8" className={i===active?"orbit-flow":""}/><circle cx={x*6} cy={y*5.6} r="5" fill={i===active?"#d8f36a":"#71856a"}/></g>)}
   <path d="M282 234 300 193l18 41m-30-13h24" stroke="#d8f36a" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
  <div className="orbit-center"><span className="mono">ALGHREST CORE</span><strong>{language==="ar"?"قواعد قبل القرار":"Les règles avant la décision"}</strong><span className="orbit-state mono">ADVISORY ONLY</span></div>
  {stages.map((stage,i)=><button key={stage.code} className={"orbit-node "+(active===i?"active":"")} style={{left:positions[i][0]+"%",top:positions[i][1]+"%"}} onClick={()=>onSelect(i)} aria-label={stage.title[language]} aria-pressed={active===i}><span className="mono">{String(i+1).padStart(2,"0")}</span><b>{stage.code}</b></button>)}
  <span className="orbit-caption">{language==="ar"?"خريطة تفاعلية للفكرة · بلا اتصال بالسوق":"Schéma interactif · aucun flux de marché"}</span>
 </div>;
}

