// TS 인터페이스

export type Login = "guest" | "member";
export type Region = "KR" | "US";
export type Device = "desktop" | "mobile";

export interface ProfileResolved {
  id: string;
  login: Login;
  ip_exit: string;
  device: Device;
  user_agent: string;
  language: string;
  timezone: string;
  cookie_reset: boolean;
  storage_state?: string;
}

export interface RunRequest {
  platforms: string[];
  skus: string[];
  combination_mode: "cross_product" | "explicit";
  dimensions?: { login: Login[]; region: Region[]; device: Device[]; };
  profiles?: ProfileResolved[];
  overrides?: Record<string,string>;
  schedule?: Record<string,unknown>;
  concurrency?: { max_contexts:number; batch_size:number; batch_window_sec:number };
  artifacts?: { keep_html:boolean; keep_screenshot:boolean };
}
