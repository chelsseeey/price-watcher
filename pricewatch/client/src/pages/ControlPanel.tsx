import { useRunConfig } from "../store/runConfig";
import PlatformPicker from "../components/PlatformPicker";
import SkuPicker from "../components/SkuPicker";
import ProfileBuilder from "../components/ProfileBuilder";
import ConcurrencyPanel from "../components/ConcurrencyPanel";
import SchedulePanel from "../components/SchedulePanel";
import RunPreview from "../components/RunPreview";
import { createRun } from "../api/runs";

export default function ControlPanel() {
  const { payload, set } = useRunConfig();

  const submit = async () => {
    if (payload.platforms.length === 0) return alert("플랫폼을 선택하세요.");
    if (payload.skus.length === 0) return alert("SKU를 선택하세요.");
    const res = await createRun(payload);
    alert("실행 생성:\n" + JSON.stringify(res, null, 2));
  };

  return (
    <div style={{ display:"grid", gap:18, maxWidth: 980 }}>
      <PlatformPicker value={payload.platforms} onChange={(v)=>set({ platforms: v })}/>
      <SkuPicker value={payload.skus} onChange={(v)=>set({ skus: v })} platforms={payload.platforms}/>
      <ProfileBuilder value={payload} onChange={(v)=>set(v)} />
      <ConcurrencyPanel value={payload.concurrency!} onChange={(v)=>set({ concurrency: v })}/>
      <SchedulePanel value={payload.schedule} onChange={(v)=>set({ schedule: v })}/>
      <RunPreview payload={payload}/>
      <div>
        <button onClick={submit} style={{ padding:"10px 14px", borderRadius:8, border:"1px solid #111", background:"#111", color:"#fff" }}>
          실행
        </button>
      </div>
    </div>
  );
}
