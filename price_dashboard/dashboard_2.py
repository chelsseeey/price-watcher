# -*- coding: utf-8 -*-
"""
자동 탐지 대시보드 (Agoda / Kayak / Amazon)
- streamlit run dashboard.py
- ./outputs 폴더의 CSV/Parquet 자동 스캔/로딩/병합
- 표준 스키마: site, ts_min, price, (선택)item/region/device/currency
- env = "{REGION}-{DEVICE}" → KR/US × PC/Mobile
- 상태(state)는 파일명 *_1/*_2/*_3/*_4 로 추론:
    _1 = 로그인(L1)
    _2 = 로그인(L1) + 장바구니(Cart)
    _3 = 비로그인(L0) + 쿠키삭제(Cleared)
    _4 = 로그인(L1) + 쿠키삭제(Cleared)
=> ENV(4) × STATE(4) = 16 라인, 각기 다른 색상으로 출력
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

# ---------------- 페이지 설정 ----------------
st.set_page_config(page_title="Real-Time Visualization", layout="wide")

# ---------------- 기본 경로/패턴 ----------------
DEFAULT_DATA_DIR = Path("./outputs")
SCAN_PATTERNS = ["*.csv", "*.parquet"]
MAX_FILES = 50

# ---------------- 컬럼 매핑 후보 ----------------
SITE_ALIASES = ["site", "platform", "seller", "source", "site_name", "domain"]
ITEM_ALIASES = ["item","product","sku","asin","title","name","product_name","url","path","route","hotel","room","room_name"]
TIME_ALIASES = ["ts_min","ts","timestamp","datetime","time","date","scraped_at","collected_at","created_at","run_at","start_ts","start_time"]
PRICE_ALIASES = ["price","fare","total_price","final_price","amount","value","room_price","deal_price"]
REGION_ALIASES = ["region","country","ip_region","geo","location","loc"]
DEVICE_ALIASES = ["device","ua_device","device_type","user_agent_device"]
CURRENCY_ALIASES = ["currency","ccy","cur","price_currency"]

# ---------------- 유틸 ----------------
def clean_cols(cols: List[str]) -> List[str]:
    return [str(c).replace("\ufeff","").strip().lower() for c in cols]

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
    for c in df.columns:
        if any(n in c for n in names):
            return c
    return None

def infer_site_from_filename_or_url(path: Path, df: pd.DataFrame) -> str:
    name = path.name.lower()
    if "agoda" in name: return "agoda"
    if "kayak" in name: return "kayak"
    if "amazon" in name or "amzn" in name: return "amazon"
    url_col = first_present(df, ["url","link","href"])
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

def extract_env_from_site(site_val: str) -> Dict[str,str]:
    s = (site_val or "").upper()
    region = "KR" if ("KR" in s or "KOREA" in s) else ("US" if ("US" in s or "USA" in s) else "")
    device = "mobile" if any(k in s for k in ["MOBILE","PHONE","IOS","ANDROID"]) else ("pc" if ("PC" in s or "DESKTOP" in s) else "")
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
    df["env"] = [mk_env(r,d) for r,d in zip(df.get("region",""), df.get("device",""))]
    return df

# ----------- 상태(state) 추론 (_1/_2/_3/_4) -----------
#   1 → L1 (로그인) / 2 → L1+Cart / 3 → L0+Cleared / 4 → L1+Cleared
_STATE_CODE_RE = re.compile(r"(?:_|-)(?:price_)?([1234])(?:\D|$)")
def infer_state_code(name: str) -> str:
    m = _STATE_CODE_RE.search(name.lower())
    return m.group(1) if m else "1"

def state_label_from_code(code: str) -> str:
    code = str(code)
    if code == "2":  return "L1+Cart"
    if code == "3":  return "L0+Cleared"
    if code == "4":  return "L1+Cleared"
    return "L1"

def derive_flags_from_code(code: str) -> Dict[str,str]:
    if code == "2":
        return {"login":"L1","cart":"Cart","cookie_cleared":"NotCleared"}
    if code == "3":
        return {"login":"L0","cart":"NoCart","cookie_cleared":"Cleared"}
    if code == "4":
        return {"login":"L1","cart":"NoCart","cookie_cleared":"Cleared"}
    return {"login":"L1","cart":"NoCart","cookie_cleared":"NotCleared"}

# ---------------- 파일 로더(표준화) ----------------
def load_and_standardize(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".parquet":
        df = pd.read_parquet(path)
    else:
        df = pd.read_csv(path, encoding="utf-8", low_memory=False)
    df.columns = clean_cols(df.columns.tolist())

    if "login" in df.columns and "logged_in" not in df.columns:
        df = df.rename(columns={"login":"logged_in"})

    site_col = first_present(df, SITE_ALIASES)
    if site_col and site_col != "site":
        df = df.rename(columns={site_col:"site"})
    if "site" not in df.columns:
        df["site"] = infer_site_from_filename_or_url(path, df)
    df["site"] = df["site"].astype(str)

    item_col = first_present(df, ITEM_ALIASES)
    if item_col and item_col != "item":
        df = df.rename(columns={item_col:"item"})
    if "item" not in df.columns:
        df["item"] = "(default)"

    tcol = first_present(df, TIME_ALIASES)
    if tcol and tcol != "ts_min":
        df["ts_min"] = coerce_datetime(df[tcol])
    elif "ts_min" in df.columns:
        df["ts_min"] = coerce_datetime(df["ts_min"])
    else:
        df["ts_min"] = pd.NaT

    pcol = first_present(df, PRICE_ALIASES)
    if pcol and pcol != "price":
        df = df.rename(columns={pcol:"price"})
    if "price" in df.columns and not np.issubdtype(df["price"].dtype, np.number):
        df["price"] = (
            df["price"].astype(str)
            .str.replace(",", "", regex=False)
            .str.extract(r"([-+]?\d*\.?\d+)")[0]
            .astype(float)
        )

    rcol = first_present(df, REGION_ALIASES)
    if rcol and rcol != "region": df = df.rename(columns={rcol:"region"})
    dcol = first_present(df, DEVICE_ALIASES)
    if dcol and dcol != "device": df = df.rename(columns={dcol:"device"})
    ccol = first_present(df, CURRENCY_ALIASES)
    if ccol and ccol != "currency": df = df.rename(columns={ccol:"currency"})

    df["source"] = path.name

    code = infer_state_code(path.name)
    df["state_code"] = code
    df["state"] = state_label_from_code(code)

    flags = derive_flags_from_code(code)
    for k, v in flags.items():
        if k not in df.columns:
            df[k] = v

    if "ts_min" in df.columns:
        df = df.dropna(subset=["ts_min"])
    if "price" in df.columns:
        df = df.dropna(subset=["price"])
        df = df[df["price"] > 0]

    df = build_env(df)

    if set(["site","item","ts_min"]).issubset(df.columns):
        df = df.sort_values(["site","item","ts_min"])
    return df.reset_index(drop=True)

# ---------------- 데이터 스캔 ----------------
@st.cache_data(show_spinner=True, ttl=300)
def load_all_data() -> pd.DataFrame:
    files: List[Path] = []
    if DEFAULT_DATA_DIR.exists():
        for pat in SCAN_PATTERNS:
            files.extend(list(DEFAULT_DATA_DIR.glob(pat)))
    files = sorted(files)[:MAX_FILES]

    if not files:
        st.warning("`./outputs`에서 파일을 찾지 못했습니다. CSV/Parquet를 업로드하세요.")
        up = st.file_uploader("파일 업로드 (CSV/Parquet, 여러 개 가능)", accept_multiple_files=True, type=["csv","parquet"])
        if not up:
            raise FileNotFoundError("데이터 파일 없음")
        dfs = []
        for upl in up:
            tmp_path = Path(upl.name)
            if upl.name.lower().endswith(".parquet"):
                df = pd.read_parquet(upl)
            else:
                df = pd.read_csv(upl, encoding="utf-8", low_memory=False)
            df.to_csv(".tmp.csv", index=False)  # dummy (로더 통일용)
            dfs.append(load_and_standardize(tmp_path))
        return pd.concat(dfs, ignore_index=True)

    dfs = []
    for p in files:
        try:
            dfs.append(load_and_standardize(p))
        except Exception as e:
            st.warning(f"{p.name} 로드 실패: {e}")
    if not dfs:
        raise FileNotFoundError("읽을 수 있는 데이터가 없습니다.")
    return pd.concat(dfs, ignore_index=True)

# ---------------- 사이드바/필터 ----------------
def sidebar_controls(df: pd.DataFrame) -> Dict[str,Any]:
    st.sidebar.header("필터")
    sources = sorted(df["source"].dropna().unique().tolist()) if "source" in df.columns else []
    src_sel = st.sidebar.multiselect("데이터 소스(파일)", options=sources, default=sources)
    view = df[df["source"].isin(src_sel)] if src_sel else df

    sites = sorted(view["site"].dropna().unique().tolist())
    site = st.sidebar.selectbox("사이트", sites, index=0 if sites else 0)

    items = sorted(view.loc[view["site"]==site, "item"].dropna().unique().tolist())
    item = st.sidebar.selectbox("아이템", items, index=0 if items else 0)

    if not view.empty and "ts_min" in view.columns:
        min_ts, max_ts = view["ts_min"].min(), view["ts_min"].max()
        st.sidebar.caption(f"데이터 기간: {min_ts:%Y-%m-%d %H:%M} ~ {max_ts:%Y-%m-%d %H:%M}")
    else:
        min_ts = max_ts = pd.Timestamp.now()

    start_date = st.sidebar.date_input("시작 날짜", value=(max_ts.date() if pd.notna(max_ts) else pd.Timestamp.now().date()))
    use_time = st.sidebar.checkbox("시작 시각 지정", value=False)
    hh = st.sidebar.number_input("시", 0, 23, 0, 1) if use_time else 0
    mm = st.sidebar.number_input("분", 0, 59, 0, 1) if use_time else 0
    start_ts = pd.Timestamp(year=start_date.year, month=start_date.month, day=start_date.day, hour=int(hh), minute=int(mm))

    envs_all = sorted(view.loc[(view["site"]==site) & (view["item"]==item), "env"].dropna().unique().tolist())
    envs_sel = st.sidebar.multiselect("Env", options=envs_all, default=envs_all)

    freq = st.sidebar.selectbox("리샘플 간격", options=["5min","15min","30min","60min","1D"], index=2)

    return dict(view=view, site=site, item=item, start_ts=start_ts, envs=envs_sel, freq=freq)

def apply_filters(view: pd.DataFrame, cfg: Dict[str,Any]) -> pd.DataFrame:
    start_ts = pd.to_datetime(cfg["start_ts"])
    try: start_ts = start_ts.tz_localize(None)
    except Exception: pass
    sel = (
        (view["site"] == cfg["site"]) &
        (view["item"] == cfg["item"]) &
        (view["ts_min"] >= start_ts) &
        (view["env"].isin(cfg["envs"]))
    )
    out = view.loc[sel].copy()
    out["ts_min"] = normalize_dt(out["ts_min"])
    return out.sort_values("ts_min")

# ---------------- KPI ----------------
def kpi_row(df: pd.DataFrame):
    DEC = 2
    def fmt(x): return f"{x:,.{DEC}f}"
    c1, c2, c3, c4, c5 = st.columns(5)
    if df.empty or "price" not in df.columns or df["price"].notna().sum() == 0:
        c1.metric("데이터 수", 0); c2.metric("최신 가격", "-"); c3.metric("평균 가격","-"); c4.metric("최저 가격","-"); c5.metric("최고 가격","-"); return
    use = df.dropna(subset=["price"]).sort_values("ts_min").copy()
    if "currency" in use.columns and use["currency"].notna().any():
        curr_series = use["currency"].astype(str).str.upper()
    else:
        curr_series = pd.Series(np.where(use["site"].str.lower().eq("amazon"), "USD", "KRW"), index=use.index)
    curr_list = sorted(pd.Series(curr_series).dropna().unique().tolist())
    unit_str = " / ".join(curr_list) if curr_list else ""
    last = use["price"].iloc[-1]; avg = use["price"].mean()
    p_min = use["price"].min(); p_max = use["price"].max()
    t_min = use.loc[use["price"].idxmin(),"ts_min"]; t_max = use.loc[use["price"].idxmax(),"ts_min"]
    c1.metric("데이터 수", f"{len(use):,}")
    c2.metric(f"최신 가격 ({unit_str})", fmt(last))
    c3.metric(f"평균 가격 ({unit_str})", fmt(avg))
    c4.metric(f"최저 가격 ({unit_str})", fmt(p_min))
    c5.metric(f"최고 가격 ({unit_str})", fmt(p_max))
    st.caption(f"최저 시각: {pd.to_datetime(t_min):%Y-%m-%d %H:%M} · 최고 시각: {pd.to_datetime(t_max):%Y-%m-%d %H:%M}")

# ---------------- 16 라인 시각화 (인터랙티브) ----------------
def plot_env_state_lines(df: pd.DataFrame, freq: str):
    """
    ENV(4) × STATE(4) = 16 라인을 각기 다른 색으로 표시
    + 차트 내부 드래그/휠 인터랙션, 범례 토글, 하단 브러시로 구간 이동
    """
    need = {"ts_min","price","env","state"}
    if df is None or df.empty or not need.issubset(df.columns):
        st.info("표시할 데이터가 부족합니다."); return

    t = df.copy()
    t["ts_min"] = pd.to_datetime(t["ts_min"], errors="coerce")
    t = t.dropna(subset=["ts_min","price"]).sort_values("ts_min")
    if t.empty: 
        st.info("리샘플 결과가 비었습니다."); return

    t["ENV"] = t["env"].astype(str).str.upper()
    t["STATE"] = t["state"].astype(str)
    t["EnvState"] = t["ENV"] + " | " + t["STATE"]

    long = (
        t.set_index("ts_min")
         .groupby("EnvState")["price"]
         .resample(freq).mean()
         .reset_index()
         .dropna(subset=["price"])
    )
    if long.empty: 
        st.info("리샘플 결과가 비었습니다."); return

    sel_leg = alt.selection_point(fields=["EnvState"], bind="legend")
    brush = alt.selection_interval(encodings=["x"])

    detail = (
        alt.Chart(long)
          .mark_line()
          .encode(
              x=alt.X("ts_min:T", title="Time"),
              y=alt.Y("price:Q", title="Price"),
              color=alt.Color("EnvState:N", title="Env | State")
          )
          .add_params(sel_leg)
          .transform_filter(sel_leg)
          .transform_filter(brush)
          .properties(height=360)
          .interactive()
    )

    overview = (
        alt.Chart(long)
          .mark_area(opacity=0.25)
          .encode(
              x=alt.X("ts_min:T", title=None),
              y=alt.Y("price:Q", title=None, aggregate="mean"),
              color=alt.Color("EnvState:N", legend=None)
          )
          .add_params(brush)
          .properties(height=70)
    )

    st.altair_chart((detail & overview).resolve_scale(color='shared'), use_container_width=True)

# ---------------- 히트맵(옵션 포함) ----------------
def heatmap_fixed_axes(df: pd.DataFrame, freq: str, tol: float = 0.0,
                       scale_mode: str = "Absolute Frequency",
                       show_values: bool = True):
    """
    고정 축 히트맵 + 옵션
      - tol: 동률 허용 오차 (같은 시각에 가격 차이가 tol 이내면 모두 최저가로 집계)
      - scale_mode:
          * Absolute Frequency                : 절대 횟수
          * Relative Frequency (Global %)     : 전체 대비 백분율
          * Region-normalized Proportion      : 지역(KR/US) 내 비율
          * Device-normalized Proportion      : 디바이스(PC/Mobile) 내 비율
      - show_values: 셀 값 표시 여부
    """
    need_any = {"ts_min","price","region","device"}
    if df is None or df.empty or not need_any.issubset(df.columns):
        st.info("히트맵을 그릴 데이터가 부족합니다.")
        return

    t = df.copy()
    t["ts_min"] = pd.to_datetime(t["ts_min"], errors="coerce")
    t = t.dropna(subset=["ts_min","price"]).sort_values("ts_min")
    if t.empty:
        st.info("히트맵을 그릴 데이터가 없습니다."); return

    # Region/Device 정규화 → KR/US, PC/Mobile
    t["region"] = t["region"].astype(str).str.upper().replace({"KOREA":"KR","USA":"US"})
    dv = t["device"].astype(str).str.lower()
    t["device_std"] = np.where(dv.str.contains("mobile"), "Mobile",
                        np.where(dv.str.contains("pc|desktop"), "PC", dv.str.title()))
    t["env_label"] = t["region"] + "-" + t["device_std"]

    x_order = ["KR-PC","KR-Mobile","US-PC","US-Mobile"]
    x_vals = [x for x in x_order if x in t["env_label"].unique().tolist()]
    if not x_vals:
        st.info("표시할 환경 조합(KR/US × PC/Mobile)이 없습니다.")
        return

    # 사용할 Y축 구성 (있을 때만)
    y_blocks = []
    if "logged_in" in t.columns or "login" in t.columns:
        col = "logged_in" if "logged_in" in t.columns else "login"
        y_blocks.append((col, ["L1","L0"], "Login"))
    if "cart" in t.columns:
        y_blocks.append(("cart", ["Cart","NoCart"], "Cart"))
    if "cookie_cleared" in t.columns:
        y_blocks.append(("cookie_cleared", ["Cleared","NotCleared"], "Cookie"))
    if not y_blocks:
        st.info("표시할 Y축 상태 컬럼이 없습니다. (login/logged_in, cart, cookie_cleared)")
        return

    # Y축 전체 순서
    y_vals = []
    for col, vals, prefix in y_blocks:
        for v in vals:
            y_vals.append(f"{prefix}={v}")

    def count_min(flag_col: str, vals: list, prefix: str) -> pd.DataFrame:
        sub = t.copy()
        sub["row_label"] = prefix + "=" + sub[flag_col].astype(str)
        sub = sub[sub["row_label"].isin([f"{prefix}={v}" for v in vals])]
        if sub.empty:
            return pd.DataFrame(columns=["row_label","env_label","count"])
        sub["col_key"] = sub["env_label"] + " | " + sub["row_label"]
        wide = (sub.pivot_table(index="ts_min", columns="col_key", values="price", aggfunc="mean")
                   .resample(freq).mean())
        if wide is None or wide.empty:
            return pd.DataFrame(columns=["row_label","env_label","count"])
        wmin = wide.min(axis=1)
        is_tie = (wide.sub(wmin, axis=0).abs() <= float(tol))
        counts = is_tie.sum(axis=0).rename("count").rename_axis("col_key").reset_index()
        parts = counts["col_key"].str.split(r" \| ", n=1, expand=True)
        counts["env_label"] = parts[0]
        counts["row_label"] = parts[1]
        return counts[["row_label","env_label","count"]]

    blocks = [count_min(col, vals, prefix) for (col, vals, prefix) in y_blocks]
    blocks = [b for b in blocks if b is not None and not b.empty]
    if not blocks:
        st.info("집계할 데이터가 부족합니다."); return
    counts = pd.concat(blocks, ignore_index=True)

    full = pd.MultiIndex.from_product([y_vals, x_vals], names=["row_label","env_label"])
    counts = counts.set_index(["row_label","env_label"]).reindex(full, fill_value=0).reset_index()

    # 스케일 변환
    parts = counts["env_label"].str.split("-", n=1, expand=True)
    counts["region"] = parts[0]
    counts["device"] = parts[1]

    value_col = "value"
    color_title = "최저가 횟수"
    text_fmt = "d"

    if scale_mode == "Absolute Frequency":
        counts[value_col] = counts["count"].astype(float)
        domain = [0.0, float(counts[value_col].max() or 1.0)]
        text_fmt = "d"
    elif scale_mode == "Relative Frequency (Global %)":
        total = float(counts["count"].sum()) or 1.0
        counts[value_col] = (counts["count"] / total) * 100.0
        color_title = "Global %"
        domain = [0.0, 100.0]
        text_fmt = ".1f"
    elif scale_mode == "Region-normalized Proportion":
        totals = counts.groupby("region")["count"].transform("sum").replace(0, np.nan)
        counts[value_col] = counts["count"] / totals
        color_title = "Proportion (by Region)"
        domain = [0.0, 1.0]
        text_fmt = ".2f"
    else:  # Device-normalized Proportion
        totals = counts.groupby("device")["count"].transform("sum").replace(0, np.nan)
        counts[value_col] = counts["count"] / totals
        color_title = "Proportion (by Device)"
        domain = [0.0, 1.0]
        text_fmt = ".2f"

    st.subheader("Lowest Price by Environment Combination")
    base = (
        alt.Chart(counts)
          .mark_rect(cornerRadius=6)
          .encode(
              x=alt.X("env_label:N", title="Environment", sort=x_order,
                      scale=alt.Scale(paddingInner=0.15, paddingOuter=0.05),
                      axis=alt.Axis(labelAngle=0)),
              y=alt.Y("row_label:N", title="Login / Cart / Cookie", sort=y_vals,
                      scale=alt.Scale(paddingInner=0.2, paddingOuter=0.1)),
              color=alt.Color(f"{value_col}:Q", title=color_title,
                              scale=alt.Scale(domain=domain, scheme="blues")),
              tooltip=[
                  alt.Tooltip("row_label:N", title="Row"),
                  alt.Tooltip("env_label:N", title="Env"),
                  alt.Tooltip("count:Q", title="최저가 횟수", format="d"),
                  alt.Tooltip(f"{value_col}:Q", title=color_title,
                              format=(".2f" if "Proportion" in color_title else (".1f" if "Global" in color_title else "d"))),
              ]
          )
          .properties(height=340)
    )

    chart = base
    if show_values:
        labels = (
            alt.Chart(counts)
              .mark_text(baseline="middle", fontSize=12, fontWeight="bold")
              .encode(
                  x="env_label:N", y="row_label:N",
                  text=alt.Text(f"{value_col}:Q", format=text_fmt),
                  color=alt.condition(
                      alt.datum[value_col] > (domain[1]*0.6 if domain[1] else 0),
                      alt.value("white"), alt.value("black")
                  )
              )
              .properties(height=340)
        )
        chart = base + labels

    st.altair_chart(
        chart.resolve_scale(color='shared').configure_axis(grid=False).configure_view(strokeOpacity=0),
        use_container_width=True
    )

# ---------------- main ----------------
def main():
    try:
        df_all = load_all_data()
    except Exception as e:
        st.error(f"데이터 로드 실패: {e}")
        st.stop()

    st.title("💹 Real-Time Visualization")

    cfg = sidebar_controls(df_all)
    view = cfg["view"]
    data = apply_filters(view, cfg)

    st.subheader(f"[{cfg['site']}] {cfg['item']} — {cfg['start_ts']:%Y-%m-%d %H:%M} 이후")
    st.caption(f"Env: {', '.join(cfg['envs']) if cfg['envs'] else '(없음)'} · 소스 파일 수: {len(view['source'].unique()) if 'source' in view.columns else '-'}")

    kpi_row(data)
    st.divider()

    st.subheader("Price Over Time")
    plot_env_state_lines(data, freq=cfg["freq"])

    st.divider()
    with st.expander("Options", expanded=False):
        tie_tol = st.number_input("동률 허용 오차", min_value=0.0, value=0.00, step=0.01, format="%.2f")
        scale_mode = st.radio(
            "Color Scale",
            options=[
                "Absolute Frequency",
                "Relative Frequency (Global %)",
                "Region-normalized Proportion",
                "Device-normalized Proportion",
            ],
            index=0,
        )
        show_values = st.checkbox("Show Values", value=True)

    heatmap_fixed_axes(
        data, cfg["freq"],
        tol=tie_tol,
        scale_mode=scale_mode,
        show_values=show_values,
    )

    with st.expander("원본 데이터 보기", expanded=False):
        cols = ["source","state","site","item","env","region","device","logged_in","login","cart","cookie_cleared","ts_min","price","currency"]
        cols = [c for c in cols if c in data.columns]
        show = data.copy()
        if "ts_min" in show.columns:
            show["ts_min"] = pd.to_datetime(show["ts_min"], errors="coerce").dt.strftime("%Y-%m-%d %H:%M:%S")
        st.dataframe(show[cols] if cols else show, use_container_width=True, height=700)
        csv = show.to_csv(index=False).encode("utf-8")
        st.download_button("CSV download", data=csv, file_name="raw_data.csv", mime="text/csv")

    if st.button("새로고침"):
        st.rerun()

if __name__ == "__main__":
    main()
