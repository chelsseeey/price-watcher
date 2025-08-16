import { RunRequest, Login, Region, Device } from "../types/run";

type Props = { value: RunRequest; onChange: (v: RunRequest) => void };

export default function ProfileBuilder({ value, onChange }: Props) {
  const isCross = value.combination_mode === "cross_product";
  return (
    <section>
      <div style={{ display:"flex", gap:8, alignItems:"center", marginBottom:8 }}>
        <strong>프로필 조합 방식</strong>
        <button onClick={()=>onChange({ ...value, combination_mode: isCross ? "explicit":"cross_product" })}
                style={{ padding:"6px 10px", borderRadius:6, border:"1px solid #ddd", background:"#fff" }}>
          {isCross ? "교차곱 → 수동" : "수동 → 교차곱"}
        </button>
      </div>
      {isCross ? <Cross value={value} onChange={onChange}/> : <Explicit value={value} onChange={onChange}/>}
    </section>
  );
}

function Cross({ value, onChange }: Props) {
  const dims = value.dimensions!;
  const toggle = <T extends string>(arr:T[], v:T)=> arr.includes(v)? arr.filter(x=>x!==v): [...arr, v];
  const setDims = (d: Partial<NonNullable<RunRequest["dimensions"]>>) =>
    onChange({ ...value, dimensions: { ...dims, ...d } });

  return (
    <div style={{ display:"grid", gridTemplateColumns:"repeat(3,1fr)", gap:12, maxWidth:700 }}>
      <Box title="login">
        {(["guest","member"] as Login[]).map(l=>(
          <label key={l} style={row}><input type="checkbox" checked={dims.login.includes(l)} onChange={()=>setDims({ login: toggle(dims.login, l) })}/> {l}</label>
        ))}
      </Box>
      <Box title="region">
        {(["KR","US"] as Region[]).map(r=>(
          <label key={r} style={row}><input type="checkbox" checked={dims.region.includes(r)} onChange={()=>setDims({ region: toggle(dims.region, r) })}/> {r}</label>
        ))}
      </Box>
      <Box title="device">
        {(["desktop","mobile"] as Device[]).map(d=>(
          <label key={d} style={row}><input type="checkbox" checked={dims.device.includes(d)} onChange={()=>setDims({ device: toggle(dims.device, d) })}/> {d}</label>
        ))}
      </Box>
    </div>
  );
}

function Explicit({ value, onChange }: Props) {
  const list = value.profiles || [];
  const add = () => {
    const id = `custom_${Date.now()}`;
    onChange({ ...value, profiles: [...list, {
      id, login:"guest", ip_exit:"KR-1", device:"desktop",
      user_agent:"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
      language:"ko-KR", timezone:"Asia/Seoul", cookie_reset:true
    }]});
  };
  const update = (i:number, patch:any) => { const a=[...list]; a[i]={...a[i], ...patch}; onChange({ ...value, profiles:a }); };
  const remove = (i:number) => { const a=[...list]; a.splice(i,1); onChange({ ...value, profiles:a }); };

  return (
    <div>
      <button onClick={add} style={{ padding:"6px 10px", borderRadius:6, border:"1px solid #ddd", background:"#fff", marginBottom:10 }}>프로필 추가</button>
      <div style={{ display:"grid", gap:10 }}>
        {list.map((p,i)=>(
          <div key={p.id} style={{ border:"1px solid #eee", borderRadius:8, padding:10, display:"grid", gap:8 }}>
            <div style={{ display:"grid", gridTemplateColumns:"repeat(4,1fr)", gap:8 }}>
              <Sel label="login" value={p.login} options={["guest","member"]} onChange={v=>update(i,{login:v})}/>
              <Sel label="ip_exit" value={p.ip_exit} options={["KR-1","US-1"]} onChange={v=>update(i,{ip_exit:v})}/>
              <Sel label="device" value={p.device} options={["desktop","mobile"]} onChange={v=>update(i,{device:v})}/>
              <Inp label="language" value={p.language} onChange={v=>update(i,{language:v})}/>
              <Inp label="timezone" value={p.timezone} onChange={v=>update(i,{timezone:v})}/>
              <Inp label="user_agent" value={p.user_agent} onChange={v=>update(i,{user_agent:v})}/>
              <Inp label="storage_state" value={(p as any).storage_state || ""} onChange={v=>update(i,{storage_state: v || undefined})}/>
              <label style={{ display:"flex", alignItems:"center", gap:8 }}>
                <input type="checkbox" checked={p.cookie_reset} onChange={e=>update(i,{cookie_reset:e.target.checked})}/> cookie_reset
              </label>
            </div>
            <div><button onClick={()=>remove(i)} style={{ color:"#c00", background:"transparent", border:"1px solid #f2caca", padding:"6px 10px", borderRadius:6 }}>삭제</button></div>
          </div>
        ))}
      </div>
    </div>
  );
}

function Box({title, children}:{title:string; children:React.ReactNode}) {
  return <div style={{ border:"1px solid #eee", borderRadius:8, padding:10 }}>
    <div style={{ fontSize:12, color:"#666", marginBottom:6 }}>{title}</div>{children}
  </div>;
}
function Sel({label, value, options, onChange}:{label:string; value:string; options:string[]; onChange:(v:string)=>void}) {
  return <label style={{ display:"grid", gap:6 }}>
    <span style={{ fontSize:12, color:"#666" }}>{label}</span>
    <select value={value} onChange={e=>onChange(e.target.value)} style={inputStyle}/>
  </label>;
}
function Inp({label, value, onChange}:{label:string; value:string; onChange:(v:string)=>void}) {
  return <label style={{ display:"grid", gap:6 }}>
    <span style={{ fontSize:12, color:"#666" }}>{label}</span>
    <input value={value} onChange={e=>onChange(e.target.value)} style={inputStyle}/>
  </label>;
}
const row:React.CSSProperties = { display:"flex", alignItems:"center", gap:6 };
const inputStyle:React.CSSProperties = { padding:8, borderRadius:8, border:"1px solid #ddd" };
