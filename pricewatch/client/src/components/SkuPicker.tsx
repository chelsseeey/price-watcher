import { useEffect, useMemo, useState } from "react";
import { getSkus } from "../api/meta";

type Props = { value: string[]; onChange: (v: string[]) => void; platforms: string[] };

export default function SkuPicker({ value, onChange, platforms }: Props) {
  const [map, setMap] = useState<Record<string,{id:string; name:string}[]>>({});
  useEffect(()=>{
    (async ()=>{
      const out:Record<string,{id:string; name:string}[]>= {};
      for (const p of platforms) out[p] = await getSkus(p);
      setMap(out);
    })();
  }, [platforms]);

  const all = useMemo(()=>Object.entries(map).flatMap(([k,v])=>v.map(i=>({...i, platform:k}))),[map]);
  const toggle = (id:string)=> onChange(value.includes(id)? value.filter(v=>v!==id): [...value, id]);

  return (
    <section>
      <h3 style={{ marginBottom:6 }}>SKU</h3>
      {!platforms.length && <p style={{ color:"#888" }}>플랫폼을 먼저 선택하세요.</p>}
      <div style={{ display:"grid", gap:8 }}>
        {all.map(s=>(
          <label key={s.id} style={{ display:"flex", alignItems:"center", gap:8 }}>
            <input type="checkbox" checked={value.includes(s.id)} onChange={()=>toggle(s.id)}/>
            <span>{s.name}</span>
            <span style={{ fontSize:12, color:"#888" }}>({s.platform})</span>
          </label>
        ))}
      </div>
    </section>
  );
}
