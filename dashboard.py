# -*- coding: utf-8 -*-
"""
자동 탐지 대시보드 (Agoda / Kayak / Amazon)
- 명령어 인자 없이 streamlit run dashboard.py 만으로 동작
- ./outputs 폴더의 CSV/Parquet 파일들을 자동 스캔/로딩/병합
- 표준 스키마로 자동 매핑: site, ts_min, price, (선택)item/region/device/currency
- env = "{REGION}-{DEVICE}" 생성 → 환경별 멀티라인 그래프
"""

from __future__ import annotations
from pathlib import Path
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse
import re

import numpy as np
import pandas as pd
import streamlit as st
import altair as alt

# --------------- 페이지 설정 ---------------
st.set_page_config(page_title="Real-Time Visualization", page_icon="✅", layout="wide")

# --------------- 기본 경로/패턴 ---------------
DEFAULT_DATA_DIR = Path("./outputs")
SCAN_PATTERNS = ["*.csv", "*.parquet"]      # 자동 스캔 패턴
MAX_FILES = 30                               # 너무 많을 때 방지

# --------------- 컬럼 매핑 후보 ---------------
SITE_ALIASES = ["site", "platform", "seller", "source", "site_name", "domain"]
ITEM_ALIASES = ["item", "product", "sku", "asin", "title", "name", "product_name",
                "url", "path", "route", "hotel", "room", "room_name"]
TIME_ALIASES = ["ts_min", "ts", "timestamp", "datetime", "time", "date",
                "scraped_at", "collected_at", "created_at", "run_at", "start_ts", "start_time"]
PRICE_ALIASES = ["price", "fare", "total_price", "final_price", "amount", "value", "room_price", "deal_price"]
REGION_ALIASES = ["region", "country", "ip_region", "geo", "location", "loc"]
DEVICE_ALIASES = ["device", "ua_device", "device_type", "user_agent_device"]
CURRENCY_ALIASES = ["currency", "ccy", "cur", "price_currency"]

# --------------- 유틸 ---------------
def clean_cols(cols: List[str]) -> List[str]:
    return [str(c).replace("\ufeff", "").strip().lower() for c in cols]

def normalize_dt(s: pd.Series) -> pd.Series:
    if not pd.api.types.is_datetime64_any_dtype(s):
        s = pd.to_datetime(s, errors="coerce", infer_datetime_format=True)
    try:
        if getattr(s.dt, "tz", None) is not None:
            s = s.dt.tz_convert(None)
        s = s.dt.tz_localize(None)
    except Exception:
        pass
    return s

def first_present(df: pd.DataFrame, names: List[str]) -> Optional[str]:
    for n in names:
        if n in df.columns:
            return n
    # 부분 매칭
    for c in df.columns:
        if any(n in c for n in names):
            return c
    return None

def infer_site_from_filename_or_url(path: Path, df: pd.DataFrame) -> str:
    name = path.name.lower()
    if "agoda" in name: return "agoda"
    if "kayak" in name: return "kayak"
    if "amazon" in name or "amzn" in name: return "amazon"
    # url 컬럼이 있으면 도메인으로 추정
    url_col = first_present(df, ["url", "link", "href"])
    if url_col:
        try:
            host = urlparse(str(df[url_col].dropna().astype(str).iloc[0])).netloc.lower()
            if "agoda" in host: return "agoda"
            if "kayak" in host: return "kayak"
            if "amazon" in host: return "amazon"
        except Exception:
            pass
    return "unknown"

def coerce_datetime(series: pd.Series) -> pd.Series:
    if pd.api.types.is_datetime64_any_dtype(series):
        return normalize_dt(series)
    if pd.api.types.is_numeric_dtype(series):
        s = pd.to_datetime(series, unit="ms", errors="coerce")
        if s.isna().all():
            s = pd.to_datetime(series, unit="s", errors="coerce")
        return normalize_dt(s)
    return normalize_dt(pd.to_datetime(series, errors="coerce", infer_datetime_format=True))

def extract_env_from_site(site_val: str) -> Dict[str, str]:
    s = (site_val or "").upper()
    region = "KR" if "KR" in s or "KOREA" in s else ("US" if "US" in s or "USA" in s else "")
    device = "mobile" if any(k in s for k in ["MOBILE", "PHONE", "IOS", "ANDROID"]) else ("pc" if "PC" in s or "DESKTOP" in s else "")
    return {"region": region, "device": device}

def build_env(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "region" not in df.columns or "device" not in df.columns:
        extr = df["site"].astype(str).apply(extract_env_from_site)
        if "region" not in df.columns: df["region"] = extr.apply(lambda x: x["region"])
        if "device" not in df.columns: df["device"] = extr.apply(lambda x: x["device"])
    def mk_env(r, d):
        r = (str(r).upper() if pd.notna(r) else "").strip()
        d = (str(d).lower() if pd.notna(d) else "").strip()
        if r and d: return f"{r}-{d.upper()}"
        if r: return r
        if d: return d.upper()
        return "(ENV)"
    df["env"] = [mk_env(r, d) for r, d in zip(df.get("region", ""), df.get("device", ""))]
    return df

# --------------- 파일 로더(표준화) ---------------
def load_and_standardize(path: Path) -> pd.DataFrame:
    # 읽기
    if path.suffix.lower() == ".parquet":
        df = pd.read_parquet(path)
    else:
        df = pd.read_csv(path, encoding="utf-8", low_memory=False)
    # 컬럼 정리
    df.columns = clean_cols(df.columns.tolist())
    # site
    site_col = first_present(df, SITE_ALIASES)
    if site_col:
        df = df.rename(columns={site_col: "site"})
        df["site"] = df["site"].astype(str)
    else:
        df["site"] = infer_site_from_filename_or_url(path, df)
    # item
    item_col = first_present(df, ITEM_ALIASES)
    if item_col and item_col != "item":
        df = df.rename(columns={item_col: "item"})
    if "item" not in df.columns:
        df["item"] = "(default)"
    # ts_min
    tcol = first_present(df, TIME_ALIASES)
    if tcol and tcol != "ts_min":
        df["ts_min"] = coerce_datetime(df[tcol])
    elif "ts_min" in df.columns:
        df["ts_min"] = coerce_datetime(df["ts_min"])
    else:
        df["ts_min"] = pd.NaT
    # price
    pcol = first_present(df, PRICE_ALIASES)
    if pcol and pcol != "price":
        df = df.rename(columns={pcol: "price"})
    if "price" in df.columns and not np.issubdtype(df["price"].dtype, np.number):
        df["price"] = (
            df["price"].astype(str)
            .str.replace(",", "", regex=False)
            .str.extract(r"([-+]?\d*\.?\d+)")[0]
            .astype(float)
        )
    # region/device/currency
    rcol = first_present(df, REGION_ALIASES)
    if rcol and rcol != "region": df = df.rename(columns={rcol: "region"})
    dcol = first_present(df, DEVICE_ALIASES)
    if dcol and dcol != "device": df = df.rename(columns={dcol: "device"})
    ccol = first_present(df, CURRENCY_ALIASES)
    if ccol and ccol != "currency": df = df.rename(columns={ccol: "currency"})
    # 기본 정리
    df["source"] = path.name
    # 핵심 결측 제거 및 양수 가격만
    if "ts_min" in df.columns:
        df = df.dropna(subset=["ts_min"])
    if "price" in df.columns:
        df = df.dropna(subset=["price"])
        df = df[df["price"] > 0]
    # env 생성
    df = build_env(df)
    # 정렬
    if set(["site", "item", "ts_min"]).issubset(df.columns):
        df = df.sort_values(["site", "item", "ts_min"])
    return df.reset_index(drop=True)

# --------------- 전체 데이터 자동 스캔/로딩 ---------------
@st.cache_data(show_spinner=True, ttl=300)
def load_all_data() -> pd.DataFrame:
    files: List[Path] = []
    if DEFAULT_DATA_DIR.exists():
        for pat in SCAN_PATTERNS:
            files.extend(list(DEFAULT_DATA_DIR.glob(pat)))
    files = sorted(files)[:MAX_FILES]
    # 업로더 대체
    if not files:
        st.warning("`./outputs` 폴더에서 파일을 찾지 못했습니다. CSV/Parquet를 업로드하세요.")
        up = st.file_uploader("파일 업로드 (CSV/Parquet, 여러 개 가능)", accept_multiple_files=True, type=["csv","parquet"])
        if not up:
            raise FileNotFoundError("데이터 파일 없음")
        dfs = []
        for upl in up:
            tmp_path = Path(upl.name)
            # 업로드 핸들러는 파일객체로 직접 읽기
            if upl.name.lower().endswith(".parquet"):
                df = pd.read_parquet(upl)
            else:
                df = pd.read_csv(upl, encoding="utf-8", low_memory=False)
            df.columns = clean_cols(df.columns.tolist())
            # 임시 path 이름 기반으로 site 추론
            dfs.append(load_and_standardize(tmp_path if isinstance(tmp_path, Path) else Path(upl.name)).combine_first(df))
        # 위 combine_first는 표준화가 필요해서 간단화: 업로드는 한 개씩 load_and_standardize 다시 호출
        dfs = [load_and_standardize(Path(f.name)) if hasattr(f, "name") else load_and_standardize(Path("upload.csv")) for f in up]  # 재호출
        return pd.concat(dfs, ignore_index=True)
    # 로컬 스캔 파일 로딩
    dfs = []
    for p in files:
        try:
            dfs.append(load_and_standardize(p))
        except Exception as e:
            st.warning(f"{p.name} 로드 실패: {e}")
    if not dfs:
        raise FileNotFoundError("읽을 수 있는 데이터가 없습니다.")
    return pd.concat(dfs, ignore_index=True)

# --------------- 사이드바/필터 ---------------
def sidebar_controls(df: pd.DataFrame) -> Dict[str, Any]:
    st.sidebar.header("필터")
    # 소스 파일 선택
    sources = sorted(df["source"].dropna().unique().tolist()) if "source" in df.columns else []
    src_sel = st.sidebar.multiselect("데이터 소스(파일)", options=sources, default=sources)
    view = df[df["source"].isin(src_sel)] if src_sel else df

    # 사이트 선택
    sites = sorted(view["site"].dropna().unique().tolist())
    site = st.sidebar.selectbox("사이트", sites, index=0 if sites else 0)

    # 아이템 선택
    items = sorted(view.loc[view["site"] == site, "item"].dropna().unique().tolist())
    item = st.sidebar.selectbox("아이템", items, index=0 if items else 0)

    # 기간
    min_ts, max_ts = view["ts_min"].min(), view["ts_min"].max()
    st.sidebar.caption(f"데이터 기간: {min_ts:%Y-%m-%d %H:%M} ~ {max_ts:%Y-%m-%d %H:%M}")
    start_date = st.sidebar.date_input("시작 날짜", value=max_ts.date())
    use_time = st.sidebar.checkbox("시작 시각 지정", value=False)
    hh = st.sidebar.number_input("시", 0, 23, 0, 1) if use_time else 0
    mm = st.sidebar.number_input("분", 0, 59, 0, 1) if use_time else 0
    start_ts = pd.Timestamp(year=start_date.year, month=start_date.month, day=start_date.day, hour=int(hh), minute=int(mm))

    # 환경 선택
    envs_all = sorted(view.loc[(view["site"] == site) & (view["item"] == item), "env"].dropna().unique().tolist())
    envs_sel = st.sidebar.multiselect("환경 라인 (KR-PC, US-MOBILE 등)", options=envs_all, default=envs_all)

    # 리샘플 간격
    freq = st.sidebar.selectbox("리샘플 간격", options=["5min","15min","30min","60min","1D"], index=2)

    return dict(view=view, site=site, item=item, start_ts=start_ts, envs=envs_sel, freq=freq)

def apply_filters(view: pd.DataFrame, cfg: Dict[str, Any]) -> pd.DataFrame:
    start_ts = pd.to_datetime(cfg["start_ts"])
    try:
        start_ts = start_ts.tz_localize(None)
    except Exception:
        pass
    sel = (
        (view["site"] == cfg["site"]) &
        (view["item"] == cfg["item"]) &
        (view["ts_min"] >= start_ts) &
        (view["env"].isin(cfg["envs"]))
    )
    out = view.loc[sel].copy()
    out["ts_min"] = normalize_dt(out["ts_min"])
    return out.sort_values("ts_min")

# --------------- 차트/KPI ---------------
def kpi_row(df: pd.DataFrame):
    # 표시 소수 자리수
    DEC_PLACES = 2
    def fmt(x):
        return f"{x:,.{DEC_PLACES}f}"

    c1, c2, c3, c4, c5 = st.columns(5)

    if df.empty or "price" not in df.columns or df["price"].notna().sum() == 0:
        c1.metric("데이터 수", 0)
        c2.metric("최신 가격", "-")
        c3.metric("평균 가격", "-")
        c4.metric("최저 가격", "-")
        c5.metric("최고 가격", "-")
        return

    use = df.dropna(subset=["price"]).sort_values("ts_min")
    last = use["price"].iloc[-1]
    avg  = use["price"].mean()
    min_idx = use["price"].idxmin()
    max_idx = use["price"].idxmax()
    p_min = use.loc[min_idx, "price"]
    p_max = use.loc[max_idx, "price"]

    c1.metric("데이터 수", f"{len(use):,}")
    c2.metric("최신 가격", fmt(last))
    c3.metric("평균 가격", fmt(avg))
    c4.metric("최저 가격", fmt(p_min))
    c5.metric("최고 가격", fmt(p_max))

    st.caption(
        f"최저 시각: {pd.to_datetime(use.loc[min_idx, 'ts_min']):%Y-%m-%d %H:%M} · "
        f"최고 시각: {pd.to_datetime(use.loc[max_idx, 'ts_min']):%Y-%m-%d %H:%M}"
    )
    
def plot_env_lines(df: pd.DataFrame, freq: str):
    if df.empty or "price" not in df.columns:
        st.info("표시할 데이터가 없습니다."); return
    use = df.copy()
    use["price"] = pd.to_numeric(use["price"], errors="coerce")
    use["ts_min"] = pd.to_datetime(use["ts_min"], errors="coerce")
    use = use.dropna(subset=["ts_min", "price"]).sort_values("ts_min")
    if use.empty: st.info("유효한 데이터가 없습니다."); return
    wide = use.pivot_table(index="ts_min", columns="env", values="price", aggfunc="mean").sort_index()
    try:
        wide = wide.resample(freq).mean()
    except Exception:
        wide.index = pd.to_datetime(wide.index, errors="coerce")
        wide = wide.dropna(how="all")
        wide = wide.sort_index().resample(freq).mean()
    wide = wide.dropna(how="all")
    if wide.empty: st.info("표시할 값이 없습니다."); return
    st.line_chart(wide)

# --------------- main ---------------
def main():
    try:
        df_all = load_all_data()
    except Exception as e:
        st.error(f"데이터 로드 실패: {e}")
        st.stop()

    st.title("💹 Real-Time Visualization")
    #st.caption(f"작업 디렉토리: {Path.cwd()} · 스캔 폴더: {DEFAULT_DATA_DIR.resolve()}")

    cfg = sidebar_controls(df_all)
    view = cfg["view"]
    data = apply_filters(view, cfg)

    st.subheader(f"[{cfg['site']}] {cfg['item']} — {cfg['start_ts']:%Y-%m-%d %H:%M} 이후")
    st.caption(f"Env: {', '.join(cfg['envs']) if cfg['envs'] else '(없음)'} · 소스 파일 수: {len(view['source'].unique()) if 'source' in view.columns else '-'}")
    kpi_row(data); st.divider()

    st.subheader("Price Difference Over Time")
    plot_env_lines(data, freq=cfg["freq"])

    with st.expander("원본 데이터 보기", expanded=False):
        cols = ["source","site","item","env","region","device","ts_min","price","currency"]
        cols = [c for c in cols if c in data.columns]
        show = data.copy()
        if "ts_min" in show.columns:
            show["ts_min"] = pd.to_datetime(show["ts_min"], errors="coerce").dt.strftime("%Y-%m-%d %H:%M:%S")
        st.dataframe(show[cols] if cols else show, use_container_width=True)

    if st.button("새로고침"): st.rerun()

if __name__ == "__main__":
    main()
