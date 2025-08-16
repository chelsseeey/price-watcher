import { useEffect, useState } from "react";
import { getPlatforms } from "../api/meta";

type Props = { value: string[]; onChange: (v: string[]) => void };

export default function PlatformPicker({ value, onChange }: Props) {
  const [items, setItems] = useState<{id:string; name:string}[]>([]);
  useEffect(()=>{ getPlatforms().then(setItems); }, []);
  const toggle = (id:string) => onChange(value.includes(id) ? value.filter(v=>v!==id) : [...value, id]);

  return (
    <section>
      <h3 style={{ marginBottom: 6 }}>플랫폼</h3>
      <div style={{ display:"flex", gap:10, flexWrap:"wrap" }}>
        {items.map(p=>(
          <label key={p.id} style={chip(value.includes(p.id))}>
            <input type="checkbox" checked={value.includes(p.id)} onChange={()=>toggle(p.id)} />
            <span>{p.name}</span>
          </label>
        ))}
      </div>
    </section>
  );
}
const chip = (active:boolean):React.CSSProperties => ({
  display:"inline-flex", alignItems:"center", gap:6, padding:"6px 10px",
  borderRadius:999, border:"1px solid #ddd", background:active?"#111":"#fff", color:active?"#fff":"#111"
});
