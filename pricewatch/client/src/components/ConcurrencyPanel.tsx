type Props = {
    value: { max_contexts:number; batch_size:number; batch_window_sec:number };
    onChange: (v:Props["value"])=>void;
  };
  export default function ConcurrencyPanel({ value, onChange }:Props) {
    const set = (k:keyof Props["value"], v:number)=> onChange({ ...value, [k]: v });
    return (
      <section>
        <h3>동시성</h3>
        <div style={{ display:"grid", gridTemplateColumns:"repeat(3,1fr)", gap:12, maxWidth:540 }}>
          <Num label="max_contexts" value={value.max_contexts} onChange={v=>set("max_contexts", v)}/>
          <Num label="batch_size" value={value.batch_size} onChange={v=>set("batch_size", v)}/>
          <Num label="batch_window_sec" value={value.batch_window_sec} onChange={v=>set("batch_window_sec", v)}/>
        </div>
      </section>
    );
  }
  function Num({label, value, onChange}:{label:string; value:number; onChange:(n:number)=>void}) {
    return (
      <label style={{ display:"grid", gap:6 }}>
        <span style={{ fontSize:12, color:"#555" }}>{label}</span>
        <input type="number" value={value} onChange={e=>onChange(Number(e.target.value))}
               style={{ padding:8, borderRadius:8, border:"1px solid #ddd" }}/>
      </label>
    );
  }
  