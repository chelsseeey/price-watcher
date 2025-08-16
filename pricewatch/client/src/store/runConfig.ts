// ▶ Zustand: 사용자가 고른 조합 상태

import { create } from "zustand";
import { RunRequest } from "../types/run";

type State = { payload: RunRequest; set: (partial: Partial<RunRequest>) => void; };

export const useRunConfig = create<State>((set)=>({
  payload: {
    platforms: ["coupang"],
    skus: [],
    combination_mode: "cross_product",
    dimensions: { login:["guest","member"], region:["KR","US"], device:["desktop","mobile"] },
    overrides: { "region.KR.ip_exit":"KR-1", "region.US.ip_exit":"US-1" },
    concurrency: { max_contexts:6, batch_size:4, batch_window_sec:30 },
    artifacts: { keep_html:true, keep_screenshot:true },
    schedule: { start:"now" }
  },
  set: (partial) => set(s => ({ payload: { ...s.payload, ...partial } }))
}));
