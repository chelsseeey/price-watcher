import { RunRequest } from "../types/run";

export default function RunPreview({ payload }: { payload: RunRequest }) {
  const profilesCount = payload.combination_mode==="cross_product"
    ? (payload.dimensions!.login.length * payload.dimensions!.region.length * payload.dimensions!.device.length)
    : (payload.profiles?.length || 0);

  return (
    <section className="card" style={{ border:"1px dashed #ddd", borderRadius:8, padding:12, maxWidth:720 }}>
      <h3>미리보기</h3>
      <ul>
        <li>플랫폼: {payload.platforms.join(", ") || "(선택 없음)"}</li>
        <li>SKU 수: {payload.skus.length}</li>
        <li>프로필 수: {profilesCount}</li>
        <li>동시성: max_contexts={payload.concurrency?.max_contexts}, batch_size={payload.concurrency?.batch_size}, window={payload.concurrency?.batch_window_sec}s</li>
        <li>스케줄: {payload.schedule?.["start"]==="now" ? "지금 실행" : `cron=${payload.schedule?.["cron"]}`}</li>
      </ul>
    </section>
  );
}
