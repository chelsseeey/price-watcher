type Props = { value?: Record<string,unknown>; onChange:(v:Record<string,unknown>)=>void };

export default function SchedulePanel({ value={ start:"now" }, onChange }:Props) {
  const startNow = value["start"]==="now";
  return (
    <section>
      <h3>스케줄</h3>
      <label style={{ display:"flex", gap:8, alignItems:"center", marginBottom:8 }}>
        <input type="radio" checked={startNow} onChange={()=>onChange({ start:"now" })}/> 지금 실행
      </label>
      <label style={{ display:"grid", gap:6 }}>
        <div style={{ display:"flex", gap:8, alignItems:"center" }}>
          <input type="radio" checked={!startNow} onChange={()=>onChange({ cron:"0 */3 * * *", timezone:"Asia/Seoul" })}/>
          <span>크론</span>
        </div>
        {!startNow && (
          <input placeholder="0 */3 * * *" defaultValue={String(value["cron"] || "0 */3 * * *")}
                 onChange={e=>onChange({ cron:e.target.value, timezone:"Asia/Seoul" })}
                 style={{ padding:8, borderRadius:8, border:"1px solid #ddd", maxWidth:240 }}/>
        )}
      </label>
    </section>
  );
}
