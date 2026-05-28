"""
MOSH シフト管理 UI

タブ構成:
  シフト管理       — owner / manager / payroll_admin（カレンダー型編集）
  マイシフト       — 全員（自分のシフト閲覧）
  打刻              — 全員（出退勤）
  シフト希望        — 全員（希望提出）／owner系（希望一覧確認）
  給与計算          — owner / payroll_admin（要セカンドパスワード）
  スタッフマスター — owner / payroll_admin
"""
import io
import re
import calendar
import time as time_module
from datetime import datetime, date, time, timedelta
from typing import Optional

import streamlit as st
import pandas as pd

import shift_db
import mosh_db
import payroll_logic as pl


# ─────────────────────────────────────────
# 共通ユーティリティ
# ─────────────────────────────────────────

STORE_OPTIONS = [
    ("kashiwa",         "柏店"),
    ("masons",          "The Mason's"),
    ("higashimurayama", "東村山店"),
    ("nishifunabashi",  "西船橋店"),
    ("otaka",           "おおたかの森店"),
    ("matsudo",         "松戸店"),
]
STORE_CODE_TO_NAME = dict(STORE_OPTIONS)
STORE_NAME_TO_CODE = {n: c for c, n in STORE_OPTIONS}
# シフト作成画面の他店シフト略号表示用（柏=柏、メ=メイソンズ、東=東村山、西=西船橋、大=おおたか、松=松戸）
STORE_CODE_TO_SHORT = {
    "kashiwa": "柏",
    "masons": "メ",
    "higashimurayama": "東",
    "nishifunabashi": "西",
    "otaka": "お",
    "matsudo": "松",
}


def _csv_download(df: pd.DataFrame, filename: str, label: str = "CSV出力"):
    """UTF-8 BOM付きCSVをダウンロードボタンで提供"""
    buf = io.BytesIO()
    buf.write("﻿".encode("utf-8"))
    df.to_csv(buf, index=False, encoding="utf-8")
    st.download_button(
        label=label,
        data=buf.getvalue(),
        file_name=filename,
        mime="text/csv",
        key=f"csv_dl_{filename}",
    )


def _inject_mobile_css():
    """Square風デザインシステム CSS（毎回注入してページ遷移時のスタイル消失を防止）"""
    st.markdown("""
<style>
/* ═══════════════════════════════════════════
   MOSH Shift Manager - Square風デザインシステム
   ═══════════════════════════════════════════ */

:root {
  --sq-primary:        #006AFF;
  --sq-primary-hover:  #0058D4;
  --sq-primary-bg:     rgba(0,106,255,0.08);
  --sq-text:           #1A1F36;
  --sq-text-secondary: #4F566B;
  --sq-text-muted:     #8792A2;
  --sq-bg:             #FFFFFF;
  --sq-bg-subtle:      #F7F8FA;
  --sq-bg-hover:       #F0F2F5;
  --sq-border:         #E3E8EE;
  --sq-border-strong:  #C1C9D2;
  --sq-success:        #1FBA63;
  --sq-success-bg:     rgba(31,186,99,0.1);
  --sq-warning:        #F5A623;
  --sq-warning-bg:     rgba(245,166,35,0.1);
  --sq-danger:         #E25555;
  --sq-danger-bg:      rgba(226,85,85,0.1);
  --sq-shadow-sm:      0 1px 2px rgba(26,31,54,0.04), 0 1px 3px rgba(26,31,54,0.04);
  --sq-shadow:         0 1px 3px rgba(26,31,54,0.06), 0 4px 12px rgba(26,31,54,0.04);
  --sq-shadow-lg:      0 4px 12px rgba(26,31,54,0.08), 0 16px 32px rgba(26,31,54,0.06);
  --sq-radius-sm:      6px;
  --sq-radius:         8px;
  --sq-radius-lg:      12px;
}

/* ─── 全体フォント & 背景 ─── */
html, body, [class*="css"], .stApp {
  font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Helvetica Neue", "Hiragino Sans", "Hiragino Kaku Gothic ProN", sans-serif !important;
  color: var(--sq-text);
}
.stApp { background: var(--sq-bg-subtle); }
section[data-testid="stMain"] .block-container {
  padding-top: 1rem;
  max-width: 100% !important;
  animation: mosh-page-fade-in 0.18s ease-out;
}
/* ページ切替時にフェードインで前のページの残像を隠す */
@keyframes mosh-page-fade-in {
  from { opacity: 0; transform: translateY(4px); }
  to { opacity: 1; transform: translateY(0); }
}

/* ─── Streamlit ネイティブサイドバー Square風 ─── */
section[data-testid="stSidebar"] {
  background: var(--sq-bg) !important;
  border-right: 1px solid var(--sq-border) !important;
}
/* PC: サイドバーは常時250px、閉じるボタンを非表示にして誤操作防止 */
@media (min-width: 769px) {
  section[data-testid="stSidebar"] {
    width: 250px !important;
    min-width: 250px !important;
    transform: none !important;
    visibility: visible !important;
  }
  /* 閉じる矢印・トグルボタンを非表示（複数バージョン対応） */
  button[data-testid="stSidebarCollapseButton"],
  button[data-testid="baseButton-headerNoPadding"],
  button[kind="headerNoPadding"],
  [data-testid="collapsedControl"],
  button[aria-label="Close sidebar"],
  button[aria-label="Hide sidebar"] {
    display: none !important;
  }
}
/* スマホでは Streamlit のハンバーガー自動制御に任せる */
section[data-testid="stSidebar"] > div:first-child {
  padding-top: 8px !important;
  background: var(--sq-bg) !important;
}
section[data-testid="stSidebar"] hr {
  margin: 8px 0 !important;
  border-color: var(--sq-border) !important;
}
/* サイドバー内のロゴエリア */
.mosh-sidebar-brand {
  padding: 14px 18px 20px;
  border-bottom: 1px solid var(--sq-border);
  margin-bottom: 10px;
}
.mosh-sidebar-logo {
  font-size: 24px;
  font-weight: 700;
  color: var(--sq-text);
  letter-spacing: 1.5px;
  line-height: 1;
}
.mosh-sidebar-sub {
  font-size: 10px;
  color: var(--sq-text-muted);
  margin-top: 4px;
  letter-spacing: 1.5px;
  text-transform: lowercase;
}
/* ユーザー情報エリア */
.mosh-sidebar-user {
  padding: 8px 18px 4px;
}
.mosh-sidebar-username {
  font-size: 14px;
  font-weight: 600;
  color: var(--sq-text);
}
.mosh-sidebar-rolemeta {
  font-size: 11px;
  color: var(--sq-text-muted);
  margin-top: 2px;
}
/* サイドバー内 radio をメニュー風に */
section[data-testid="stSidebar"] [data-testid="stRadio"] > div {
  flex-direction: column !important;
  gap: 2px !important;
  padding: 0 8px !important;
}
section[data-testid="stSidebar"] [data-testid="stRadio"] label {
  width: 100% !important;
  padding: 9px 12px !important;
  border-radius: var(--sq-radius) !important;
  cursor: pointer;
  font-size: 14px !important;
  color: var(--sq-text-secondary) !important;
  background: transparent !important;
  border: none !important;
  transition: all 0.12s ease;
  margin: 0 !important;
  display: flex !important;
  align-items: center !important;
}
section[data-testid="stSidebar"] [data-testid="stRadio"] label:hover {
  background: var(--sq-bg-hover) !important;
  color: var(--sq-text) !important;
}
/* radio ○ボタンを非表示 */
section[data-testid="stSidebar"] [data-testid="stRadio"] label > div:first-child {
  display: none !important;
}
/* 選択中のラベル */
section[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) {
  background: var(--sq-primary-bg) !important;
  color: var(--sq-primary) !important;
  font-weight: 600 !important;
}
/* サイドバー内のボタン（ログアウト用） */
section[data-testid="stSidebar"] .stButton > button {
  margin: 0 8px !important;
  width: calc(100% - 16px) !important;
  background: transparent !important;
  color: var(--sq-text-secondary) !important;
  border: 1px solid var(--sq-border) !important;
  font-size: 13px !important;
}
section[data-testid="stSidebar"] .stButton > button:hover {
  background: var(--sq-bg-hover) !important;
  color: var(--sq-danger) !important;
  border-color: var(--sq-danger) !important;
}
/* 旧:メインタブ用 CSS は不要になったが、念のため残す（他の st.tabs に効く） */

/* ─── タブを左サイドバー化（PC・769px以上）─── */
@media (min-width: 769px) {
  /* 最上位の tab-list のみサイドバー化（ネストには適用しない） */
  div[data-testid="stTabs"] > div > div[data-baseweb="tab-list"] {
    flex-direction: column !important;
    width: 220px !important;
    min-width: 220px !important;
    align-self: flex-start;
    background: var(--sq-bg);
    border-right: 1px solid var(--sq-border);
    border-radius: var(--sq-radius);
    padding: 12px 8px !important;
    gap: 2px !important;
    box-shadow: var(--sq-shadow-sm);
    position: sticky;
    top: 1rem;
  }
  div[data-testid="stTabs"] > div {
    display: flex !important;
    flex-direction: row !important;
    gap: 20px !important;
    align-items: flex-start !important;
  }
  div[data-testid="stTabs"] > div > div[data-baseweb="tab-panel"] {
    flex: 1 !important;
    min-width: 0;
    padding: 0 !important;
  }
  /* タブボタンを縦リストの行に */
  div[data-testid="stTabs"] > div > div[data-baseweb="tab-list"] button[role="tab"] {
    width: 100% !important;
    text-align: left !important;
    justify-content: flex-start !important;
    padding: 10px 14px !important;
    border-radius: var(--sq-radius) !important;
    font-size: 14px !important;
    font-weight: 500 !important;
    color: var(--sq-text-secondary) !important;
    background: transparent !important;
    border: none !important;
    transition: all 0.15s ease;
  }
  div[data-testid="stTabs"] > div > div[data-baseweb="tab-list"] button[role="tab"]:hover {
    background: var(--sq-bg-hover) !important;
    color: var(--sq-text) !important;
  }
  div[data-testid="stTabs"] > div > div[data-baseweb="tab-list"] button[role="tab"][aria-selected="true"] {
    background: var(--sq-primary-bg) !important;
    color: var(--sq-primary) !important;
    font-weight: 600 !important;
  }
  /* タブ下のラインを消す */
  div[data-testid="stTabs"] > div > div[data-baseweb="tab-list"] div[data-baseweb="tab-highlight"],
  div[data-testid="stTabs"] > div > div[data-baseweb="tab-list"] div[data-baseweb="tab-border"] {
    display: none !important;
  }
  /* ネスト（サブタブ）は横並びを維持 */
  div[data-testid="stTabs"] div[data-testid="stTabs"] > div > div[data-baseweb="tab-list"] {
    flex-direction: row !important;
    width: 100% !important;
    min-width: 0 !important;
    background: transparent;
    border: none;
    box-shadow: none;
    position: static;
    padding: 0 !important;
  }
  div[data-testid="stTabs"] div[data-testid="stTabs"] > div {
    flex-direction: column !important;
  }
}

/* ─── ボタン Square風 ─── */
.stButton > button {
  border-radius: var(--sq-radius) !important;
  font-weight: 500 !important;
  padding: 8px 16px !important;
  transition: all 0.15s ease;
  border: 1px solid var(--sq-border-strong);
  box-shadow: var(--sq-shadow-sm);
}
.stButton > button:hover {
  background: var(--sq-bg-hover);
  border-color: var(--sq-text-secondary);
}
.stButton > button[kind="primary"] {
  background: var(--sq-primary) !important;
  color: white !important;
  border: 1px solid var(--sq-primary) !important;
}
.stButton > button[kind="primary"]:hover {
  background: var(--sq-primary-hover) !important;
  border-color: var(--sq-primary-hover) !important;
}

/* ─── 打刻専用の巨大ボタン ─── */
button[data-clock-button="true"], .stButton button[kind="primary"][data-testid*="clock"] {
  min-height: 68px !important;
  font-size: 20px !important;
  font-weight: 700 !important;
  border-radius: var(--sq-radius-lg) !important;
  letter-spacing: 2px;
}

/* ─── selectbox / input ─── */
.stSelectbox label, .stRadio label, .stTextInput label, .stNumberInput label {
  font-size: 13px !important;
  font-weight: 500 !important;
  color: var(--sq-text-secondary) !important;
}
.stSelectbox > div > div, .stTextInput > div > div > input, .stNumberInput > div > div > input {
  min-height: 44px !important;
  border-radius: var(--sq-radius) !important;
  font-size: 15px !important;
  border: 1px solid var(--sq-border) !important;
}
.stSelectbox > div > div:focus-within, .stTextInput > div > div:focus-within {
  border-color: var(--sq-primary) !important;
  box-shadow: 0 0 0 3px var(--sq-primary-bg) !important;
}

/* ─── DataFrame / data_editor ─── */
[data-testid="stDataFrame"], [data-testid="stDataEditor"] {
  border-radius: var(--sq-radius) !important;
  border: 1px solid var(--sq-border) !important;
  box-shadow: var(--sq-shadow-sm);
}
/* セル内のフォントサイズと余白を縮めて、シフト表で「[メ18:45-29]」も入る幅にする */
[data-testid="stDataEditor"] [role="gridcell"],
[data-testid="stDataEditor"] [role="columnheader"] {
  font-size: 11px !important;
  padding-left: 3px !important;
  padding-right: 3px !important;
  letter-spacing: -0.3px;
}
[data-testid="stDataFrame"] [role="gridcell"],
[data-testid="stDataFrame"] [role="columnheader"] {
  font-size: 11px !important;
  padding-left: 3px !important;
  padding-right: 3px !important;
}

/* ─── Metric ─── */
[data-testid="stMetric"] {
  background: var(--sq-bg);
  padding: 16px 20px;
  border-radius: var(--sq-radius);
  border: 1px solid var(--sq-border);
  box-shadow: var(--sq-shadow-sm);
}
[data-testid="stMetricLabel"] {
  font-size: 13px !important;
  color: var(--sq-text-secondary) !important;
  font-weight: 500;
}
[data-testid="stMetricValue"] {
  font-size: 28px !important;
  font-weight: 600 !important;
  color: var(--sq-text) !important;
}

/* ─── Info / Warning / Success / Error ボックス ─── */
.stAlert {
  border-radius: var(--sq-radius) !important;
  border: 1px solid var(--sq-border) !important;
  padding: 12px 16px !important;
}

/* ═══════════════════════════════════════════
   MOSHコンポーネント
   ═══════════════════════════════════════════ */

/* ─── スタッフ情報ヘッダー ─── */
.mosh-staff-header {
  background: var(--sq-bg);
  color: var(--sq-text);
  padding: 20px 24px;
  border-radius: var(--sq-radius-lg);
  margin: 0 0 20px;
  border: 1px solid var(--sq-border);
  box-shadow: var(--sq-shadow-sm);
}
.mosh-staff-name { font-size: 24px; font-weight: 600; line-height: 1.3; color: var(--sq-text); }
.mosh-staff-meta { font-size: 14px; color: var(--sq-text-secondary); margin-top: 6px; }

/* ─── シフトカード ─── */
.mosh-shift-card {
  background: var(--sq-bg);
  border: 1px solid var(--sq-border);
  border-radius: var(--sq-radius-lg);
  padding: 18px 20px;
  margin: 10px 0;
  box-shadow: var(--sq-shadow-sm);
  transition: all 0.15s ease;
}
.mosh-shift-card:hover {
  border-color: var(--sq-border-strong);
  box-shadow: var(--sq-shadow);
}
.mosh-shift-date { font-size: 18px; font-weight: 600; margin-bottom: 8px; }
.mosh-shift-store { font-size: 14px; color: var(--sq-text-secondary); margin-bottom: 4px; }
.mosh-shift-time {
  font-size: 18px; font-weight: 600; color: var(--sq-text); margin: 8px 0;
  font-variant-numeric: tabular-nums; letter-spacing: 0.5px;
}
.mosh-shift-hours { font-size: 14px; color: var(--sq-text-secondary); }
.mosh-shift-hours strong { font-size: 16px; color: var(--sq-text); font-weight: 600; }
.mosh-shift-sub { font-size: 12px; color: var(--sq-text-muted); margin-left: 6px; }

/* ─── 打刻カード ─── */
.mosh-clock-card {
  background: var(--sq-bg);
  border-radius: var(--sq-radius-lg);
  padding: 28px 24px;
  margin: 12px 0 20px;
  text-align: center;
  border: 1px solid var(--sq-border);
  box-shadow: var(--sq-shadow);
}
.clock-status-active {
  background: linear-gradient(135deg, #006AFF 0%, #0058D4 100%);
  color: white;
  border-color: transparent;
}
.clock-status-active .mosh-clock-staff,
.clock-status-active .mosh-clock-store,
.clock-status-active .mosh-clock-now,
.clock-status-active .mosh-clock-status,
.clock-status-active .mosh-clock-elapsed { color: white !important; }
.mosh-clock-staff { font-size: 20px; font-weight: 600; margin-bottom: 6px; color: var(--sq-text); }
.mosh-clock-store { font-size: 14px; color: var(--sq-text-secondary); margin-bottom: 12px; }
.mosh-clock-now {
  font-size: 36px; font-weight: 600; letter-spacing: 1px; margin: 12px 0;
  font-variant-numeric: tabular-nums; color: var(--sq-text);
}
.mosh-clock-status { font-size: 18px; font-weight: 600; margin: 12px 0; color: var(--sq-text); }
.mosh-clock-elapsed { font-size: 14px; margin-top: 12px; line-height: 1.7; color: var(--sq-text-secondary); }
.mosh-clock-elapsed-h { font-size: 24px; font-weight: 700; }

/* ─── 店舗シフト確定版カード ─── */
.mosh-day-card {
  background: var(--sq-bg);
  border: 1px solid var(--sq-border);
  border-radius: var(--sq-radius-lg);
  padding: 16px 20px;
  margin: 10px 0;
  box-shadow: var(--sq-shadow-sm);
}
.mosh-day-header {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 10px;
  border-bottom: 1px solid var(--sq-border);
  padding-bottom: 8px;
}
.mosh-staff-row {
  font-size: 14px;
  padding: 8px 12px;
  margin: 4px 0;
  border-radius: var(--sq-radius-sm);
  background: var(--sq-bg-subtle);
  color: var(--sq-text);
}

/* ─── 打刻履歴カード ─── */
.mosh-log-card {
  background: var(--sq-bg-subtle);
  border-radius: var(--sq-radius);
  padding: 12px 14px;
  margin: 6px 0;
  border: 1px solid var(--sq-border);
}
.mosh-log-date { font-size: 14px; font-weight: 600; color: var(--sq-text); }
.mosh-log-store { font-size: 13px; color: var(--sq-text-secondary); margin: 2px 0; }
.mosh-log-time { font-size: 13px; color: var(--sq-text-secondary); font-variant-numeric: tabular-nums; }

/* ─── スマホ（768px以下）の調整 ─── */
@media (max-width: 768px) {
  .mosh-staff-header { padding: 16px 18px; }
  .mosh-staff-name { font-size: 20px; }
  .mosh-clock-card { padding: 22px 18px; }
  .mosh-clock-now { font-size: 38px; }
  .mosh-clock-elapsed-h { font-size: 28px; }
  .stButton > button[kind="primary"] { min-height: 56px !important; font-size: 17px !important; }
  /* スマホではタブを上部に横スクロール表示（Streamlitデフォルト挙動） */
  div[data-testid="stTabs"] > div > div[data-baseweb="tab-list"] {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }
}

/* ─── PWA対応: ホーム画面追加時のフルスクリーン挙動 ─── */
@media (display-mode: standalone) {
  .stApp { padding-top: env(safe-area-inset-top); }
  header[data-testid="stHeader"] { display: none !important; }
}

/* ─── Streamlit デフォルト要素を控えめに（アプリ感UP） ─── */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
.stDeployButton { display: none !important; }
</style>

<!-- ═══ PWA メタタグ（ホーム画面追加・フルスクリーン化） ═══ -->
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover, user-scalable=no">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="MOSH勤怠">
<meta name="mobile-web-app-capable" content="yes">
<meta name="theme-color" content="#006AFF">
""", unsafe_allow_html=True)


def _is_payroll_admin(user: dict) -> bool:
    return user and user.get("role") in ("owner", "payroll_admin")


def _is_manager_or_above(user: dict) -> bool:
    return user and user.get("role") in ("owner", "manager", "payroll_admin")


def _parse_time_cell(cell: str) -> Optional[tuple[time, time, bool]]:
    """
    「15-24」「15:30-24」「15-29」のような時間文字列をパース。
    返り値: (start_time, end_time, crosses_midnight) or None（休み/空欄）

    24以上の数字は翌日扱い（例: 29 → 翌5:00, crosses_midnight=True）
    """
    if not cell or not isinstance(cell, str):
        return None
    cell = cell.strip()
    if cell in ("", "休", "×", "ー", "-", "—", "－"):
        return None
    # ↓ 数字-数字 or 数字:分-数字:分
    m = re.match(r"^(\d{1,2})(?::(\d{1,2}))?\s*[-〜~]\s*(\d{1,2})(?::(\d{1,2}))?$", cell)
    if not m:
        return None
    sh, sm, eh, em = m.group(1), m.group(2), m.group(3), m.group(4)
    sh, sm = int(sh), int(sm or 0)
    eh, em = int(eh), int(em or 0)
    crosses = False
    if eh >= 24:
        eh -= 24
        crosses = True
    try:
        st_t = time(sh, sm)
        en_t = time(eh, em)
    except ValueError:
        return None
    return (st_t, en_t, crosses)


def _format_time_cell(start: time, end: time, crosses_midnight: bool) -> str:
    sh = f"{start.hour}:{start.minute:02d}" if start.minute else f"{start.hour}"
    eh = end.hour + (24 if crosses_midnight else 0)
    eh_str = f"{eh}:{end.minute:02d}" if end.minute else f"{eh}"
    return f"{sh}-{eh_str}"


def _shift_to_datetimes(shift_date: date, start_t: time, end_t: time, crosses: bool):
    """シフトレコードから出退勤の datetime ペアを生成"""
    start_dt = datetime.combine(shift_date, start_t)
    end_dt = datetime.combine(shift_date, end_t)
    if crosses or (end_t < start_t):
        end_dt += timedelta(days=1)
    return start_dt, end_dt


# ─────────────────────────────────────────
# 1. シフト管理タブ（owner / manager / payroll_admin）
# ─────────────────────────────────────────

def render_shift_create_tab(user: dict):
    st.markdown("### シフト作成")

    if not _is_manager_or_above(user):
        st.warning("この画面は管理者専用です。")
        return

    # シフト管理パスワード保護
    if not require_shift_admin_unlock("create"):
        return

    # スマホ警告（編集はPC推奨）
    st.info("シフト編集はPCでの操作を推奨します")

    # 店舗選択（managerは自店舗のみ）
    available_codes = [c for c, _ in STORE_OPTIONS]
    if user.get("role") == "manager" and user.get("store"):
        mapped = STORE_NAME_TO_CODE.get(user["store"]) or user["store"]
        available_codes = [mapped] if mapped in dict(STORE_OPTIONS) else available_codes

    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        store_code = st.selectbox(
            "店舗",
            available_codes,
            format_func=lambda c: STORE_CODE_TO_NAME.get(c, c),
            key="shift_store",
        )
    with col2:
        today = date.today()
        ym_options = []
        for i in range(-1, 4):
            d = (today.replace(day=1) + timedelta(days=32 * i)).replace(day=1)
            ym_options.append(d.strftime("%Y-%m"))
        ym = st.selectbox("月", ym_options, index=1, key="shift_ym")
    with col3:
        st.markdown("&nbsp;")
        refresh = st.button("再読込", use_container_width=True)

    year, month = map(int, ym.split("-"))
    _, days_in_month = calendar.monthrange(year, month)
    days = list(range(1, days_in_month + 1))

    # スタッフ取得（経営者は除外）
    staffs = shift_db.get_all_staff(active_only=True, store=store_code, for_shift_only=True)
    if not staffs:
        st.info("この店舗で勤務可能なスタッフがまだ登録されていません。")
        return

    # ── アクションボタン（希望反映・全公開）──
    st.markdown("#### アクション")
    act1, act2, act3 = st.columns(3)
    with act1:
        if st.button("希望から下書きを生成", use_container_width=True, key="import_req"):
            n = shift_db.import_requests_to_draft(ym, store_code, created_by=user.get("id"))
            if n > 0:
                st.success(f"{n}件のシフトを希望から下書きに反映しました")
                st.rerun()
            else:
                st.info("反映すべき新規希望はありませんでした（既存シフトは上書きしません）")
    with act2:
        if st.button("下書きを公開（確定）", type="primary", use_container_width=True, key="confirm_all"):
            n = shift_db.confirm_shifts(ym, store_code)
            if n > 0:
                st.success(f"{n}件のシフトを公開しました。スタッフのマイシフトに反映されます。")
                st.rerun()
            else:
                st.info("公開対象の下書きシフトがありませんでした")
    with act3:
        if st.button("公開を取消（下書きに戻す）", use_container_width=True, key="revert_draft"):
            n = shift_db.revert_to_draft(ym, store_code)
            if n > 0:
                st.warning(f"{n}件のシフトを下書きに戻しました")
                st.rerun()
            else:
                st.info("取消対象の確定シフトがありませんでした")

    # 表示モード（下書き編集 or 確定確認）
    view_mode = st.radio("表示モード", ["下書き編集", "確定済み（読み取り専用）", "全部"],
                          horizontal=True, key="shift_view_mode")
    status_filter = {"下書き編集": "draft", "確定済み（読み取り専用）": "confirmed", "全部": None}[view_mode]

    # シフト取得（当該店舗）
    shifts = shift_db.get_shifts_by_month(ym, store=store_code, status=status_filter)
    shift_map = {}
    for s in shifts:
        shift_map[(s["staff_id"], s["shift_date"].day)] = s

    # 他店シフト取得（掛け持ちスタッフの重複防止用）
    # status_filter に関わらず draft/confirmed 両方を表示対象に
    all_shifts = shift_db.get_shifts_by_month(ym)
    other_store_map = {}  # (staff_id, day) -> ["[西15-22]", "[メ22-29]"]
    for s in all_shifts:
        if s["store"] == store_code:
            continue  # 自店は除外
        key = (s["staff_id"], s["shift_date"].day)
        short_store = STORE_CODE_TO_SHORT.get(s["store"], s["store"])
        time_str = _format_time_cell(s["start_time"], s["end_time"], s["crosses_midnight"])
        other_store_map.setdefault(key, []).append(f"[{short_store}{time_str}]")

    # 曜日付きヘッダー（土曜・日曜・祝日で識別）
    weekday_emoji = ["", "", "", "", "", "", ""]  # 月火水木金土日
    weekday_label = ["月", "火", "水", "木", "金", "土", "日"]
    try:
        import jpholiday
        has_jpholiday = True
    except Exception:
        has_jpholiday = False

    day_headers = []
    for d in days:
        try:
            dt = date(year, month, d)
            wd = dt.weekday()  # 0=月, 6=日
            prefix = weekday_emoji[wd]
            if has_jpholiday and jpholiday.is_holiday(dt):
                prefix = ""
            day_headers.append(f"{prefix}{d}({weekday_label[wd]})")
        except Exception:
            day_headers.append(str(d))

    # DataFrame作成（列ヘッダーに曜日付き・スタッフ名はシンプルに）
    # 他店シフトがある場合は [西15-22] のように表示して掛け持ち重複を可視化
    rows = []
    for staff in staffs:
        row = {"スタッフ": staff["display_name"], "_staff_id": staff["id"]}
        for d, header in zip(days, day_headers):
            sh = shift_map.get((staff["id"], d))
            if sh:
                row[header] = _format_time_cell(sh["start_time"], sh["end_time"], sh["crosses_midnight"])
            else:
                others = other_store_map.get((staff["id"], d), [])
                row[header] = " ".join(others) if others else ""
        rows.append(row)
    df = pd.DataFrame(rows)

    st.caption("例: `15-24`（15時〜24時）/ `15-29`（15時〜翌5時）/ 休みは空欄・`休`・`×`・`ー`　　`[西15-22]` 形式は他店シフト（編集不可）")

    # 列幅: スタッフ名は small、日付列も small に戻す（CSSで文字を少し小さくして長文字列も収まるように）
    column_config = {"スタッフ": st.column_config.TextColumn(width="small", pinned="left")}
    for header in day_headers:
        column_config[header] = st.column_config.TextColumn(width="small")

    # 編集
    edited = st.data_editor(
        df.drop(columns=["_staff_id"]),
        use_container_width=True,
        hide_index=True,
        key=f"shift_editor_{store_code}_{ym}",
        disabled=["スタッフ"],
        column_config=column_config,
    )

    # 保存処理用に「列ヘッダー→日数」マップを作成
    header_to_day = {h: d for d, h in zip(days, day_headers)}

    # 保存ボタン
    col_save, col_csv = st.columns([1, 1])
    with col_save:
        if st.button("シフトを保存", type="primary", use_container_width=True):
            _save_shift_changes(edited, df, staffs, year, month, store_code, user, header_to_day)
    with col_csv:
        _csv_download(edited, f"mosh_shifts_{store_code}_{ym}.csv")

    # サマリー（労働時間・人件費試算）
    st.markdown("---")
    _render_shift_summary(staffs, shifts, store_code, ym, user)


def _save_shift_changes(edited_df: pd.DataFrame, original_df: pd.DataFrame,
                          staffs: list, year: int, month: int, store_code: str, user: dict,
                          header_to_day: dict = None):
    """data_editor の差分を検出して upsert/delete

    header_to_day: 曜日付き列ヘッダー（"1(日)"等）→ 日数(int) のマップ
    """
    header_to_day = header_to_day or {}
    changes = 0
    errors = []
    user_id = user.get("id")

    for idx, row in edited_df.iterrows():
        staff = staffs[idx]
        staff_id = staff["id"]
        for col in edited_df.columns:
            if col == "スタッフ":
                continue
            day = header_to_day.get(col)
            if day is None:
                continue
            new_val = (row[col] or "").strip() if isinstance(row[col], str) else ""
            old_val = (original_df.iloc[idx][col] or "").strip() if isinstance(original_df.iloc[idx][col], str) else ""
            if new_val == old_val:
                continue
            # [西15-22] 形式は他店シフトの表示用なので保存対象外（ユーザーが編集した場合は無視）
            if new_val.startswith("[") and new_val.endswith("]"):
                continue
            # 元が他店表示で new_val が空欄になった場合（ユーザーが他店表示を消した）も保存しない
            if old_val.startswith("[") and not new_val:
                continue
            try:
                shift_date = date(year, month, day)
            except ValueError:
                continue
            parsed = _parse_time_cell(new_val)
            # 新しい値が休/空 → 削除
            if parsed is None:
                # 既存シフトを削除（ある場合のみ）
                shifts_to_delete = [s for s in shift_db.get_shifts_by_month(f"{year:04d}-{month:02d}", store=store_code)
                                    if s["staff_id"] == staff_id and s["shift_date"] == shift_date]
                for s in shifts_to_delete:
                    shift_db.delete_shift(s["id"])
                changes += 1
            else:
                start_t, end_t, crosses = parsed
                try:
                    shift_db.upsert_shift(
                        staff_id=staff_id, store=store_code, shift_date=shift_date,
                        start_time=start_t, end_time=end_t,
                        crosses_midnight=crosses, created_by=user_id,
                        status="draft",  # 編集は常に下書き状態
                    )
                    changes += 1
                except Exception as e:
                    errors.append(f"{staff['display_name']} {month}/{day}: {e}")

    if errors:
        for e in errors:
            st.error(e)
    if changes:
        st.success(f"{changes}件のシフトを保存しました")
        st.rerun()
    else:
        st.info("変更はありませんでした")


def _render_shift_summary(staffs: list, shifts: list, store_code: str, ym: str, user: dict):
    """シフト合計時間 + 人件費試算（payroll_admin のみ人件費表示）"""
    st.markdown("#### 月次サマリー")

    summaries = []
    for staff in staffs:
        staff_shifts = [s for s in shifts if s["staff_id"] == staff["id"]]
        total_raw = 0.0
        total_actual = 0.0
        for s in staff_shifts:
            start_dt, end_dt = _shift_to_datetimes(s["shift_date"], s["start_time"], s["end_time"], s["crosses_midnight"])
            split = pl.split_work_hours(start_dt, end_dt, staff["employment_type"])
            total_raw += split["raw_hours"]
            total_actual += split["actual_hours"]
        summaries.append({
            "スタッフ": staff["display_name"],
            "出勤日数": len(staff_shifts),
            "想定時間": f"{total_raw:.1f}h",
            "実労働時間": f"{total_actual:.1f}h",
            "雇用形態": staff["employment_type"],
            "_actual_hours": total_actual,
            "_staff": staff,
        })

    df = pd.DataFrame(summaries).drop(columns=["_actual_hours", "_staff"])

    # 人件費は payroll_admin のみ表示（セカンドPWアンロックが必要）
    if _is_payroll_admin(user) and _payroll_unlocked():
        df_cost = []
        for s in summaries:
            staff = s["_staff"]
            staff_shifts = [sh for sh in shifts if sh["staff_id"] == staff["id"]]
            splits = []
            for sh in staff_shifts:
                start_dt, end_dt = _shift_to_datetimes(sh["shift_date"], sh["start_time"],
                                                        sh["end_time"], sh["crosses_midnight"])
                splits.append({"split": pl.split_work_hours(start_dt, end_dt, staff["employment_type"],
                                                              is_legal_holiday=sh["is_legal_holiday"]),
                                "date": sh["shift_date"]})
            rate = pl.calc_hourly_rate(
                employment_type=staff["employment_type"],
                hourly_wage=staff["hourly_wage"],
                base_monthly_salary=staff["base_monthly_salary"],
                monthly_standard_hours=staff["monthly_standard_hours"],
                position_allowance_per_hour=staff["position_allowance_per_hour"],
            )
            monthly = pl.calc_monthly_payroll(splits, rate, staff["employment_type"],
                                               base_monthly_salary=staff["base_monthly_salary"] or 0)
            df_cost.append({"スタッフ": staff["display_name"], "人件費": f"¥{monthly['total_pay']:,}"})

        df_cost_df = pd.DataFrame(df_cost)
        df = df.merge(df_cost_df, on="スタッフ", how="left")

        total_cost = sum(int(row["人件費"].replace("¥","").replace(",","")) for row in df_cost)
        store = next((s for s in shift_db.get_stores_master() if s["code"] == store_code), None)
        target = store["monthly_target_sales"] if store else 0
        ratio = (total_cost / target * 100) if target else 0
        target_ratio = float(store["target_labor_cost_ratio"]) if store else 30.0

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("総人件費", f"¥{total_cost:,}")
        with col2:
            st.metric("月間売上目標", f"¥{target:,}" if target else "—")
        with col3:
            color = "" if ratio < target_ratio else ("" if ratio < target_ratio + 5 else "")
            st.metric("人件費比率", f"{color} {ratio:.1f}%", delta=f"目標 {target_ratio:.0f}%以下", delta_color="off")

    st.dataframe(df, use_container_width=True, hide_index=True)


# ─────────────────────────────────────────
# 2. マイシフトタブ（全員）
# ─────────────────────────────────────────

def render_my_shift_tab(user: dict):
    """マイシフト（スマホファースト・カード型タイムライン）"""
    _inject_mobile_css()
    st.markdown("### マイシフト")

    staff_id = user.get("staff_id")
    if not staff_id:
        st.warning("あなたのアカウントはまだスタッフマスターに紐付いていません。管理者に連絡してください。")
        return

    staff = shift_db.get_staff(staff_id)
    if not staff:
        st.error("スタッフ情報が見つかりません。")
        return

    # スタッフ情報ヘッダーカード（役職プレフィックスなし）
    st.markdown(f"""
<div class="mosh-staff-header">
    <div class="mosh-staff-name">{staff['display_name']}</div>
    <div class="mosh-staff-meta">{STORE_CODE_TO_NAME.get(staff['primary_store'], staff['primary_store'])}　/　{staff.get('position', 'スタッフ')}</div>
</div>
""", unsafe_allow_html=True)

    # 月選択
    today = date.today()
    ym_options = []
    for i in range(-1, 3):
        d = (today.replace(day=1) + timedelta(days=32 * i)).replace(day=1)
        ym_options.append(d.strftime("%Y-%m"))
    ym = st.selectbox("月を選択", ym_options, index=1, key="my_shift_ym")

    # 確定済みシフトのみ表示（下書きはマイシフトに見えない）
    shifts = shift_db.get_shifts_by_month(ym, staff_id=staff_id, status="confirmed")

    # 月次サマリー（先に計算）
    total_actual = 0.0
    total_expected_pay = 0
    rate = pl.calc_hourly_rate(
        employment_type=staff["employment_type"],
        hourly_wage=staff["hourly_wage"],
        base_monthly_salary=staff["base_monthly_salary"],
        monthly_standard_hours=staff["monthly_standard_hours"],
        position_allowance_per_hour=staff["position_allowance_per_hour"],
    )
    shift_cards = []
    for s in shifts:
        start_dt, end_dt = _shift_to_datetimes(s["shift_date"], s["start_time"], s["end_time"], s["crosses_midnight"])
        split = pl.split_work_hours(start_dt, end_dt, staff["employment_type"],
                                     is_legal_holiday=s["is_legal_holiday"])
        pay = pl.calc_single_shift_pay(split, rate)
        total_actual += split["actual_hours"]
        total_expected_pay += sum(pay.values())
        shift_cards.append({"shift": s, "split": split, "pay_total": sum(pay.values())})

    # サマリーカード
    col1, col2 = st.columns(2)
    with col1:
        st.metric("出勤日数", f"{len(shift_cards)}日")
    with col2:
        st.metric("実労働", f"{total_actual:.1f}h")

    if not shift_cards:
        st.info("この月の確定シフトはまだ公開されていません")
        return

    st.markdown("---")
    st.markdown("#### シフト一覧")

    weekday_jp = ["月", "火", "水", "木", "金", "土", "日"]
    weekday_color = ["", "", "", "", "", "#4A90E2", "#E25555"]  # 土青・日赤
    try:
        import jpholiday
        has_jpholiday = True
    except Exception:
        has_jpholiday = False

    # カード型タイムライン
    for c in shift_cards:
        s = c["shift"]
        sp = c["split"]
        dt = s["shift_date"]
        wd = dt.weekday()
        wd_color = weekday_color[wd]
        is_holiday = has_jpholiday and jpholiday.is_holiday(dt)
        date_color = "#E25555" if (wd == 6 or is_holiday) else (wd_color if wd_color else "#333")
        time_label = _format_time_cell(s["start_time"], s["end_time"], s["crosses_midnight"])
        store_name = STORE_CODE_TO_NAME.get(s["store"], s["store"])

        st.markdown(f"""
<div class="mosh-shift-card">
    <div class="mosh-shift-date" style="color: {date_color};">
        {dt.month}/{dt.day} ({weekday_jp[wd]}){'' if is_holiday else ''}
    </div>
    <div class="mosh-shift-store">{store_name}</div>
    <div class="mosh-shift-time">{time_label}</div>
    <div class="mosh-shift-hours">
        実労働 <strong>{sp['actual_hours']:.1f}h</strong>
        <span class="mosh-shift-sub">（想定 {sp['raw_hours']:.1f}h / 休憩 {sp['break_minutes']}分）</span>
    </div>
</div>
""", unsafe_allow_html=True)

    st.markdown("---")
    df = pd.DataFrame([{
        "日付": f"{c['shift']['shift_date'].month}/{c['shift']['shift_date'].day}",
        "店舗": STORE_CODE_TO_NAME.get(c['shift']['store'], c['shift']['store']),
        "時間帯": _format_time_cell(c['shift']['start_time'], c['shift']['end_time'], c['shift']['crosses_midnight']),
        "実労働": f"{c['split']['actual_hours']:.1f}h",
    } for c in shift_cards])
    _csv_download(df, f"my_shifts_{staff_id}_{ym}.csv")


# ─────────────────────────────────────────
# 2-2. 店舗シフト（確定版・全員閲覧可）
# ─────────────────────────────────────────

def render_confirmed_shifts_tab(user: dict):
    """全員が見られる確定シフト閲覧画面（読み取り専用）"""
    _inject_mobile_css()
    st.markdown("### 店舗シフト")

    # 自分の所属店舗をデフォルトに
    staff_id = user.get("staff_id")
    default_store = "kashiwa"
    if staff_id:
        my_staff = shift_db.get_staff(staff_id)
        if my_staff:
            default_store = my_staff.get("primary_store") or "kashiwa"

    col1, col2 = st.columns(2)
    with col1:
        store_codes = [c for c, _ in STORE_OPTIONS]
        idx = store_codes.index(default_store) if default_store in store_codes else 0
        store_code = st.selectbox("店舗", store_codes,
                                     index=idx,
                                     format_func=lambda c: STORE_CODE_TO_NAME.get(c, c),
                                     key="confirmed_store")
    with col2:
        today = date.today()
        ym_options = []
        for i in range(-1, 3):
            d = (today.replace(day=1) + timedelta(days=32 * i)).replace(day=1)
            ym_options.append(d.strftime("%Y-%m"))
        ym = st.selectbox("月", ym_options, index=1, key="confirmed_ym")

    # 確定シフト取得
    shifts = shift_db.get_shifts_by_month(ym, store=store_code, status="confirmed")
    if not shifts:
        st.info(f"{ym} の {STORE_CODE_TO_NAME.get(store_code)} の確定シフトはまだありません（管理者が公開すると表示されます）")
        return

    # 日付ごとにグルーピング
    from collections import defaultdict
    by_date = defaultdict(list)
    for s in shifts:
        by_date[s["shift_date"]].append(s)

    weekday_jp = ["月", "火", "水", "木", "金", "土", "日"]
    try:
        import jpholiday
        has_jpholiday = True
    except Exception:
        has_jpholiday = False

    st.caption("黄色ハイライトは自分のシフトです")

    # 日付昇順でカード表示
    for d in sorted(by_date.keys()):
        wd = d.weekday()
        is_holiday = has_jpholiday and jpholiday.is_holiday(d)
        date_color = "#E25555" if (wd == 6 or is_holiday) else ("#4A90E2" if wd == 5 else "#2D1F0F")

        shifts_html = ""
        for s in sorted(by_date[d], key=lambda x: x["start_time"]):
            is_self = staff_id and s["staff_id"] == staff_id
            style = ' style="background:#FFF3CD;font-weight:700;border-left:3px solid #FFC107;"' if is_self else ''
            time_str = _format_time_cell(s["start_time"], s["end_time"], s["crosses_midnight"])
            shifts_html += f'<div class="mosh-staff-row"{style}>{s["display_name"]}　{time_str}</div>'

        st.markdown(f"""
<div class="mosh-day-card">
    <div class="mosh-day-header" style="color:{date_color};">
        {d.month}/{d.day} ({weekday_jp[wd]}){'祝日' if is_holiday else ''}
    </div>
    {shifts_html}
</div>
""", unsafe_allow_html=True)

    # CSVエクスポート
    rows = [{
        "日付": s["shift_date"].strftime("%Y-%m-%d"),
        "曜日": weekday_jp[s["shift_date"].weekday()],
        "スタッフ": s["display_name"],
        "時間帯": _format_time_cell(s["start_time"], s["end_time"], s["crosses_midnight"]),
    } for s in sorted(shifts, key=lambda x: (x["shift_date"], x["start_time"]))]
    _csv_download(pd.DataFrame(rows), f"confirmed_shifts_{store_code}_{ym}.csv")


# ─────────────────────────────────────────
# 3. 打刻タブ（全員）
# ─────────────────────────────────────────

def render_timecard_tab(user: dict):
    """打刻（スマホファースト・巨大ボタン）"""
    _inject_mobile_css()
    st.markdown("### 打刻")

    staff_id = user.get("staff_id")
    if not staff_id:
        st.warning("あなたのアカウントはまだスタッフマスターに紐付いていません。管理者に連絡してください。")
        return

    staff = shift_db.get_staff(staff_id)
    open_log = shift_db.get_open_time_log(staff_id)

    # 現在時刻（JST明示）
    now = shift_db.now_jst()

    import streamlit.components.v1 as components

    if open_log:
        # 出勤中
        clock_in_time = open_log["clock_in"]
        if clock_in_time.tzinfo is None:
            from datetime import timezone as _tz
            clock_in_time = clock_in_time.replace(tzinfo=_tz.utc)
        clock_in_jst = clock_in_time.astimezone(shift_db.JST)
        elapsed_h = (now - clock_in_jst).total_seconds() / 3600
        clock_in_iso = clock_in_jst.isoformat()
        clock_in_date_str = clock_in_jst.strftime("%Y/%m/%d")
        clock_in_time_str = clock_in_jst.strftime("%H:%M")
        store_name = STORE_CODE_TO_NAME.get(open_log['store'], open_log['store'])
        components.html(f"""
<!DOCTYPE html><html><head><meta charset="utf-8"><style>
body{{margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,"SF Pro Display","Helvetica Neue","Hiragino Sans",sans-serif;background:transparent;}}
.card{{background:linear-gradient(135deg,#006AFF 0%,#0058D4 100%);color:white;padding:28px 24px;border-radius:12px;text-align:center;box-shadow:0 4px 12px rgba(26,31,54,0.08);}}
.staff{{font-size:20px;font-weight:600;margin-bottom:6px;}}
.store{{font-size:14px;opacity:0.92;margin-bottom:14px;}}
.now-time{{font-size:42px;font-weight:600;letter-spacing:2px;margin:12px 0;font-variant-numeric:tabular-nums;}}
.status{{font-size:18px;font-weight:600;margin:12px 0;}}
.elapsed-label{{font-size:13px;opacity:0.9;margin-top:14px;}}
.elapsed-value{{font-size:26px;font-weight:700;margin-top:4px;font-variant-numeric:tabular-nums;}}
</style></head><body>
<div class="card">
  <div class="staff">{staff['display_name']}</div>
  <div class="store">{store_name}</div>
  <div class="now-time" id="now-time">--:--:--</div>
  <div class="status">出勤中</div>
  <div class="elapsed-label">{clock_in_date_str} {clock_in_time_str} 出勤</div>
  <div class="elapsed-value" id="elapsed">{elapsed_h:.2f} 時間</div>
</div>
<script>
const startMs = new Date("{clock_in_iso}").getTime();
function pad(n){{return String(n).padStart(2,'0');}}
function tick(){{
  const now = new Date();
  document.getElementById('now-time').textContent = pad(now.getHours())+':'+pad(now.getMinutes())+':'+pad(now.getSeconds());
  const h = (now.getTime() - startMs) / 1000 / 3600;
  document.getElementById('elapsed').textContent = h.toFixed(2) + ' 時間';
}}
tick();
setInterval(tick, 1000);
</script>
</body></html>
""", height=290)

        if st.button("退勤", type="primary", use_container_width=True, key="clock_out_btn"):
            shift_db.clock_out(open_log["id"])
            st.success("退勤しました。お疲れさまでした！")
            time_module.sleep(1)
            st.rerun()
    else:
        # 未出勤
        components.html(f"""
<!DOCTYPE html><html><head><meta charset="utf-8"><style>
body{{margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,"SF Pro Display","Helvetica Neue","Hiragino Sans",sans-serif;background:transparent;}}
.card{{background:#FFFFFF;border:1px solid #E3E8EE;color:#1A1F36;padding:24px 20px;border-radius:12px;text-align:center;box-shadow:0 1px 3px rgba(26,31,54,0.04);}}
.staff{{font-size:18px;font-weight:600;margin-bottom:8px;}}
.now-time{{font-size:38px;font-weight:600;letter-spacing:2px;margin:12px 0;font-variant-numeric:tabular-nums;color:#1A1F36;}}
.status{{font-size:16px;font-weight:500;color:#4F566B;}}
</style></head><body>
<div class="card">
  <div class="staff">{staff['display_name']}</div>
  <div class="now-time" id="now-time">--:--:--</div>
  <div class="status">未出勤</div>
</div>
<script>
function pad(n){{return String(n).padStart(2,'0');}}
function tick(){{
  const now = new Date();
  document.getElementById('now-time').textContent = pad(now.getHours())+':'+pad(now.getMinutes())+':'+pad(now.getSeconds());
}}
tick();
setInterval(tick, 1000);
</script>
</body></html>
""", height=200)

        store_code = st.selectbox(
            "勤務店舗を選んでください",
            [c for c, _ in STORE_OPTIONS],
            format_func=lambda c: STORE_CODE_TO_NAME.get(c, c),
            index=[c for c, _ in STORE_OPTIONS].index(staff["primary_store"])
                if staff["primary_store"] in [c for c, _ in STORE_OPTIONS] else 0,
            key="clock_in_store",
        )
        if st.button("出勤", type="primary", use_container_width=True, key="clock_in_btn"):
            shift_db.clock_in(staff_id, store_code)
            st.success("出勤を記録しました！")
            time_module.sleep(1)
            st.rerun()

    # 当月の打刻履歴（折りたたみ）
    st.markdown("---")
    with st.expander("今月の打刻履歴を見る"):
        ym = date.today().strftime("%Y-%m")
        logs = shift_db.get_time_logs_by_month(ym, staff_id=staff_id)
        if not logs:
            st.caption("打刻履歴はまだありません")
            return
        for log in logs:
            ci = log["clock_in"]
            co = log["clock_out"]
            # JST に変換して表示
            ci_jst = ci.astimezone(shift_db.JST) if ci and ci.tzinfo else ci
            co_jst = co.astimezone(shift_db.JST) if co and co.tzinfo else co
            if ci_jst and co_jst:
                split = pl.split_work_hours(ci_jst.replace(tzinfo=None), co_jst.replace(tzinfo=None),
                                             staff["employment_type"])
                status_str = f"{ci_jst.strftime('%H:%M')} - {co_jst.strftime('%H:%M')} / 実労働 {split['actual_hours']:.1f}h"
            else:
                status_str = f"{ci_jst.strftime('%H:%M')} - 出勤中"
            st.markdown(f"""
<div class="mosh-log-card">
    <div class="mosh-log-date">{log['work_date'].strftime('%Y/%m/%d')}</div>
    <div class="mosh-log-store">{STORE_CODE_TO_NAME.get(log['store'], log['store'])}</div>
    <div class="mosh-log-time">{status_str}</div>
</div>
""", unsafe_allow_html=True)
        rows = [{
            "日付": log["work_date"].strftime("%Y-%m-%d"),
            "店舗": STORE_CODE_TO_NAME.get(log["store"], log["store"]),
            "出勤": (log["clock_in"].astimezone(shift_db.JST).strftime("%H:%M") if log["clock_in"] and log["clock_in"].tzinfo else (log["clock_in"].strftime("%H:%M") if log["clock_in"] else "")),
            "退勤": (log["clock_out"].astimezone(shift_db.JST).strftime("%H:%M") if log["clock_out"] and log["clock_out"].tzinfo else (log["clock_out"].strftime("%H:%M") if log["clock_out"] else "")),
        } for log in logs]
        _csv_download(pd.DataFrame(rows), f"my_timelogs_{staff_id}_{ym}.csv")


# ─────────────────────────────────────────
# 4. シフト希望タブ（全員 + owner系の一覧確認）
# ─────────────────────────────────────────

def render_shift_request_tab(user: dict):
    st.markdown("### シフト希望")

    # 来月のYYYY-MM
    today = date.today()
    next_month_first = (today.replace(day=1) + timedelta(days=32)).replace(day=1)
    ym = next_month_first.strftime("%Y-%m")

    tabs = st.tabs(["希望を提出", "全員の希望一覧"] if _is_manager_or_above(user) else ["希望を提出"])

    with tabs[0]:
        _render_submit_request(user, ym)

    if _is_manager_or_above(user) and len(tabs) > 1:
        with tabs[1]:
            _render_request_overview(ym)


def _render_submit_request(user: dict, ym: str):
    _inject_mobile_css()
    staff_id = user.get("staff_id")
    if not staff_id:
        st.warning("あなたのアカウントはまだスタッフマスターに紐付いていません。")
        return
    staff = shift_db.get_staff(staff_id)

    # ヘッダーカード（役職プレフィックスなし）
    st.markdown(f"""
<div class="mosh-staff-header">
    <div class="mosh-staff-name">{staff['display_name']}</div>
    <div class="mosh-staff-meta">{ym} のシフト希望を提出</div>
</div>
""", unsafe_allow_html=True)

    year, month = map(int, ym.split("-"))
    _, days_in_month = calendar.monthrange(year, month)

    existing = {r["request_date"]: r for r in shift_db.get_shift_requests(ym, staff_id=staff_id)}

    weekday_jp = ["月", "火", "水", "木", "金", "土", "日"]
    try:
        import jpholiday
        has_jpholiday = True
    except Exception:
        has_jpholiday = False

    type_options = ["未定", "出れる", "休み希望", "時間指定"]
    type_to_db = {"出れる": "available", "休み希望": "unavailable", "時間指定": "preferred"}
    db_to_type = {v: k for k, v in type_to_db.items()}

    st.caption("各日付の希望を選んでください。「時間指定」を選んだら時間帯も入力してください（例: 15-24）。")

    # 各日付カード（formでまとめてsubmit）
    with st.form(f"req_form_{ym}", clear_on_submit=False):
        choices = {}
        time_inputs = {}
        notes = {}
        for d in range(1, days_in_month + 1):
            rd = date(year, month, d)
            wd = rd.weekday()
            r = existing.get(rd)
            current_type = db_to_type.get(r["request_type"]) if r else "未定"
            current_time = _format_request_time(r) if r else ""
            current_note = r["note"] if r else ""

            is_holiday = has_jpholiday and jpholiday.is_holiday(rd)
            date_emoji = "" if is_holiday else ("" if wd == 6 else ("" if wd == 5 else ""))
            label = f"{date_emoji}{d}日({weekday_jp[wd]})"

            cols = st.columns([1.2, 1.5, 1.3, 2])
            with cols[0]:
                st.markdown(f"<div style='padding-top:8px;font-weight:600;font-size:16px;'>{label}</div>", unsafe_allow_html=True)
            with cols[1]:
                choices[rd] = st.selectbox(
                    "希望", type_options,
                    index=type_options.index(current_type),
                    key=f"req_choice_{rd}",
                    label_visibility="collapsed",
                )
            with cols[2]:
                time_inputs[rd] = st.text_input(
                    "時間",
                    value=current_time,
                    key=f"req_time_{rd}",
                    placeholder="15-24",
                    label_visibility="collapsed",
                )
            with cols[3]:
                notes[rd] = st.text_input(
                    "備考",
                    value=current_note,
                    key=f"req_note_{rd}",
                    placeholder="（任意）",
                    label_visibility="collapsed",
                )

        submitted = st.form_submit_button("希望を一括保存", type="primary", use_container_width=True)

    if submitted:
        cnt = 0
        for rd, ctype in choices.items():
            rtype = type_to_db.get(ctype)
            if not rtype:
                continue
            pstart, pend = None, None
            parsed = _parse_time_cell(time_inputs[rd])
            if parsed:
                pstart, pend = parsed[0], parsed[1]
            shift_db.upsert_shift_request(staff_id, ym, rd, rtype, pstart, pend, notes[rd] or "")
            cnt += 1
        st.success(f"{cnt}件の希望を保存しました")
        time_module.sleep(1)
        st.rerun()


def _format_request_time(r):
    if r.get("preferred_start") and r.get("preferred_end"):
        return _format_time_cell(r["preferred_start"], r["preferred_end"], False)
    return ""


def _render_request_overview(ym: str):
    reqs = shift_db.get_shift_requests(ym)
    if not reqs:
        st.info("まだ希望提出がありません")
        return
    rows = [{
        "スタッフ": r["display_name"],
        "店舗": STORE_CODE_TO_NAME.get(r["primary_store"], r["primary_store"]),
        "日付": r["request_date"].strftime("%-m/%-d"),
        "希望": {"available": "出れる", "unavailable": "休み希望", "preferred": "時間指定"}.get(r["request_type"], r["request_type"]),
        "希望時間帯": _format_request_time(r),
        "備考": r["note"] or "",
    } for r in reqs]
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)
    _csv_download(df, f"mosh_requests_{ym}.csv")


# ─────────────────────────────────────────
# 5. 給与計算タブ（owner / payroll_admin・セカンドPW保護）
# ─────────────────────────────────────────

# ─────────────────────────────────────────
# 初期セットアップタブ（owner専用・staff_seed投入）
# ─────────────────────────────────────────

def render_setup_tab(user: dict):
    st.markdown("### 初期セットアップ")
    if user.get("role") != "owner":
        st.error("この画面は owner 専用です")
        return

    # 経営陣パスワードで保護
    if not require_payroll_unlock("setup"):
        return

    st.markdown("""
シフト管理ツールの**初回セットアップ**を行います。

- シフト管理用5テーブルを Supabase に作成（既存なら何もしない）
- 店舗マスター（5店舗）を初期投入
- スタッフマスターに全30名を投入
- 認証アカウントを30名分発行（初期PW: `MOSH4148`）
- 賃金画面パスワード設定（`datakintaimosh`）

**冪等です**：何度実行しても既存データは保護されます。
""")

    # 現状の登録状況
    try:
        current_staff = shift_db.get_all_staff(active_only=False)
        st.info(f"現在の登録: スタッフ {len(current_staff)}名 / 店舗 {len(shift_db.get_stores_master(active_only=False))}店")
    except Exception as e:
        st.warning(f"DB接続を確認中... ({e})")

    if "setup_confirmed" not in st.session_state:
        st.session_state.setup_confirmed = False

    if not st.session_state.setup_confirmed:
        if st.button("セットアップを開始", type="primary"):
            st.session_state.setup_confirmed = True
            st.rerun()
    else:
        st.warning("本当に実行しますか？（既存データは保護されますが、新規スタッフが追加されます）")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("実行する", type="primary"):
                _run_setup()
                st.session_state.setup_confirmed = False
        with col2:
            if st.button("キャンセル"):
                st.session_state.setup_confirmed = False
                st.rerun()


def _run_setup():
    import staff_seed
    log_area = st.empty()
    logs = []

    def log_fn(msg):
        logs.append(str(msg))
        log_area.code("\n".join(logs[-30:]))

    try:
        result = staff_seed.seed(log=log_fn)
        st.success(f"セットアップ完了！スタッフ {result['staff_count']}名 / 新規ユーザー {result['user_created']}名")

        # 認証情報CSV出力
        creds_df = pd.DataFrame(result["credentials"])
        st.markdown("### 全スタッフのログイン情報")
        st.dataframe(creds_df, use_container_width=True, hide_index=True)
        _csv_download(creds_df, f"mosh_staff_credentials_{date.today().strftime('%Y-%m-%d')}.csv",
                       label="ログイン情報CSV（スタッフ配布用）")
    except Exception as e:
        st.error(f"エラー: {e}")
        st.exception(e)


def _build_square_csv(staffs, ym, source, store_map):
    """Square 形式CSV（24カラム・日次行データ）の rows を生成"""
    all_rows = []

    if source == "シフト（予定）":
        all_shifts = shift_db.get_shifts_by_month(ym)
        all_logs = []
    else:
        all_shifts = []
        all_logs = shift_db.get_time_logs_by_month(ym)

    for staff in staffs:
        rate = pl.calc_hourly_rate(
            employment_type=staff["employment_type"],
            hourly_wage=staff["hourly_wage"],
            base_monthly_salary=staff["base_monthly_salary"],
            monthly_standard_hours=staff["monthly_standard_hours"],
            position_allowance_per_hour=staff["position_allowance_per_hour"],
        )
        if rate <= 0:
            continue

        entries = []
        if source == "シフト（予定）":
            for s in [x for x in all_shifts if x["staff_id"] == staff["id"]]:
                start_dt, end_dt = _shift_to_datetimes(
                    s["shift_date"], s["start_time"], s["end_time"], s["crosses_midnight"]
                )
                entries.append({
                    "start_dt": start_dt,
                    "end_dt": end_dt,
                    "store": s["store"],
                    "is_legal_holiday": s["is_legal_holiday"],
                })
        else:
            for l in [x for x in all_logs if x["staff_id"] == staff["id"] and x["clock_out"]]:
                # JST に変換してから naive datetime にする
                ci = l["clock_in"]
                co = l["clock_out"]
                if ci.tzinfo:
                    ci = ci.astimezone(shift_db.JST).replace(tzinfo=None)
                if co.tzinfo:
                    co = co.astimezone(shift_db.JST).replace(tzinfo=None)
                entries.append({
                    "start_dt": ci,
                    "end_dt": co,
                    "store": l["store"],
                    "is_legal_holiday": False,
                })

        entries.sort(key=lambda x: x["start_dt"])

        monthly_ot = 0.0
        for e in entries:
            result = pl.export_square_row(
                start_dt=e["start_dt"],
                end_dt=e["end_dt"],
                employment_type=staff["employment_type"],
                hourly_rate=rate,
                store_display=store_map.get(e["store"], e["store"]),
                last_name=staff.get("last_name", "") or "",
                first_name=staff.get("first_name", "") or "",
                employee_id=staff.get("employee_id", "") or "",
                is_legal_holiday=e["is_legal_holiday"],
                monthly_overtime_so_far=monthly_ot,
            )
            all_rows.append(result["row"])
            monthly_ot += result["overtime_added"]

    return all_rows


PAYROLL_UNLOCK_KEY = "payroll_unlocked_at"
SHIFT_ADMIN_UNLOCK_KEY = "shift_admin_unlocked_at"
# タイムアウトなし。session_state にフラグが立っていれば常に unlocked。
# ログアウト or ブラウザ閉じれば自動的にセッション切れる。


def _payroll_unlocked() -> bool:
    return bool(st.session_state.get(PAYROLL_UNLOCK_KEY))


def _shift_admin_unlocked() -> bool:
    return bool(st.session_state.get(SHIFT_ADMIN_UNLOCK_KEY))


def require_shift_admin_unlock(context: str = "default") -> bool:
    """シフト作成画面用セカンドパスワード（経営陣・店長級共有）"""
    if _shift_admin_unlocked():
        return True
    st.warning("シフト作成画面は専用パスワードで保護されています（経営陣・店長共有）")
    pw = st.text_input("シフト管理パスワード", type="password", key=f"shift_pw_input_{context}")
    if st.button("ロック解除", key=f"shift_unlock_btn_{context}"):
        if shift_db.verify_shift_admin_password(pw):
            st.session_state[SHIFT_ADMIN_UNLOCK_KEY] = True
            st.success("ロック解除しました")
            st.rerun()
        else:
            st.error("パスワードが違います")
    return False


def require_payroll_unlock(context: str = "default") -> bool:
    """賃金関連UIの前に呼ぶ。アンロック済みなら True、未アンロックなら入力UIを描画して False

    Args:
        context: 呼び出し元タブを識別する文字列。同じkeyの widget 重複エラーを避けるため
                 各呼び出し元で異なる値を渡すこと（例: "payroll", "staff_admin", "store_admin"）
    """
    if _payroll_unlocked():
        return True
    st.warning("この画面は経営陣パスワードで保護されています")
    pw = st.text_input("経営陣パスワード", type="password", key=f"payroll_pw_input_{context}")
    if st.button("ロック解除", key=f"payroll_unlock_btn_{context}"):
        if shift_db.verify_payroll_password(pw):
            st.session_state[PAYROLL_UNLOCK_KEY] = True
            st.success("ロック解除しました")
            st.rerun()
        else:
            st.error("パスワードが違います")
    return False


def render_payroll_tab(user: dict):
    st.markdown("### 給与計算")

    if not _is_payroll_admin(user):
        st.error("この画面は経営陣（owner / payroll_admin）専用です")
        return

    if not require_payroll_unlock("payroll"):
        return

    # 月選択
    today = date.today()
    ym_options = []
    for i in range(-3, 2):
        d = (today.replace(day=1) + timedelta(days=32 * i)).replace(day=1)
        ym_options.append(d.strftime("%Y-%m"))
    ym = st.selectbox("対象月", ym_options, index=3, key="payroll_ym")

    if st.button("ロックする", key="payroll_relock"):
        st.session_state.pop(PAYROLL_UNLOCK_KEY, None)
        st.rerun()

    st.markdown("---")

    # 全スタッフの月次集計
    staffs = shift_db.get_all_staff(active_only=True)
    shifts = shift_db.get_shifts_by_month(ym)
    logs = shift_db.get_time_logs_by_month(ym)

    # ソース選択
    source = st.radio("集計ソース", ["シフト（予定）", "打刻（実績）"], horizontal=True, key="payroll_source")

    rows = []
    for staff in staffs:
        if source == "シフト（予定）":
            staff_shifts = [s for s in shifts if s["staff_id"] == staff["id"]]
            splits = []
            for s in staff_shifts:
                start_dt, end_dt = _shift_to_datetimes(s["shift_date"], s["start_time"],
                                                        s["end_time"], s["crosses_midnight"])
                splits.append({"split": pl.split_work_hours(start_dt, end_dt, staff["employment_type"],
                                                              is_legal_holiday=s["is_legal_holiday"]),
                                "date": s["shift_date"]})
        else:
            staff_logs = [l for l in logs if l["staff_id"] == staff["id"] and l["clock_out"]]
            splits = []
            for l in staff_logs:
                splits.append({"split": pl.split_work_hours(l["clock_in"].replace(tzinfo=None),
                                                              l["clock_out"].replace(tzinfo=None),
                                                              staff["employment_type"]),
                                "date": l["work_date"]})

        if not splits:
            continue

        rate = pl.calc_hourly_rate(
            employment_type=staff["employment_type"],
            hourly_wage=staff["hourly_wage"],
            base_monthly_salary=staff["base_monthly_salary"],
            monthly_standard_hours=staff["monthly_standard_hours"],
            position_allowance_per_hour=staff["position_allowance_per_hour"],
        )
        monthly = pl.calc_monthly_payroll(splits, rate, staff["employment_type"],
                                           base_monthly_salary=staff["base_monthly_salary"] or 0)

        rows.append({
            "スタッフ": staff["display_name"],
            "店舗": STORE_CODE_TO_NAME.get(staff["primary_store"], staff["primary_store"]),
            "雇用": staff["employment_type"],
            "出勤日数": monthly["shift_days"],
            "想定h": round(monthly["raw_hours"], 1),
            "休憩(分)": monthly["break_minutes"],
            "実労働h": round(monthly["actual_hours"], 1),
            "通常h": round(monthly["regular_hours"], 1),
            "深夜h": round(monthly["night_hours"], 1),
            "残業h": round(monthly["overtime_hours"], 1),
            "残業×深夜h": round(monthly["overtime_night_hours"], 1),
            "月60h超h": round(monthly["overtime_60_plus_hours"], 1),
            "法定休日h": round(monthly["holiday_hours"], 1),
            "基本給": monthly["base_monthly_salary"],
            "通常賃金": monthly["regular_pay"],
            "深夜手当": monthly["night_pay"],
            "残業手当": monthly["overtime_pay"],
            "残業×深夜手当": monthly["overtime_night_pay"],
            "月60h超手当": monthly["overtime_60_plus_pay"],
            "法定休日手当": monthly["holiday_pay"],
            "支給合計": monthly["total_pay"],
        })

    if not rows:
        st.info("対象月のデータがありません")
        return

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    total_pay = df["支給合計"].sum()
    st.metric("月間総人件費", f"¥{total_pay:,}")

    col_csv1, col_csv2 = st.columns(2)
    with col_csv1:
        _csv_download(df, f"mosh_payroll_summary_{ym}_{source.replace('（','_').replace('）','')}.csv",
                       label="月次サマリーCSV（スタッフ別合算）")
    with col_csv2:
        # Square 形式CSV（日次行データ）を生成
        square_rows = _build_square_csv(staffs, ym, source, store_map=STORE_CODE_TO_NAME)
        if square_rows:
            square_df = pd.DataFrame(square_rows, columns=pl.SQUARE_CSV_COLUMNS)
            _csv_download(square_df, f"square_{ym}_{source.replace('（','_').replace('）','')}.csv",
                           label="Square形式CSV（日次行データ）")

    # パスワード変更（owner のみ）
    if user.get("role") == "owner":
        st.markdown("---")
        with st.expander("経営陣パスワード変更（給与・スタッフ管理用）"):
            new_pw = st.text_input("新しいパスワード", type="password", key="new_payroll_pw")
            new_pw2 = st.text_input("確認用パスワード", type="password", key="new_payroll_pw2")
            if st.button("変更を保存", key="save_payroll_pw"):
                if not new_pw or new_pw != new_pw2:
                    st.error("パスワードが一致しません")
                else:
                    shift_db.update_payroll_password(new_pw)
                    st.success("パスワードを変更しました")

        with st.expander("シフト管理パスワード変更（店長・経営陣共有）"):
            new_pw3 = st.text_input("新しいパスワード", type="password", key="new_shift_pw")
            new_pw4 = st.text_input("確認用パスワード", type="password", key="new_shift_pw2")
            if st.button("変更を保存", key="save_shift_pw"):
                if not new_pw3 or new_pw3 != new_pw4:
                    st.error("パスワードが一致しません")
                else:
                    shift_db.update_shift_admin_password(new_pw3)
                    st.success("シフト管理パスワードを変更しました")


# ─────────────────────────────────────────
# 6. スタッフマスター管理タブ（owner / payroll_admin・要セカンドPW）
# ─────────────────────────────────────────

def _safe_int(v, default=0):
    """None・空文字・非数値を安全にintに変換"""
    if v is None or (isinstance(v, str) and v.strip() == ""):
        return default
    try:
        if isinstance(v, float) and (v != v):  # NaN
            return default
        return int(v)
    except (ValueError, TypeError):
        return default


def render_staff_admin_tab(user: dict):
    st.markdown("### スタッフマスター")

    if not _is_payroll_admin(user):
        st.error("この画面は経営陣（owner / payroll_admin）専用です")
        return
    if not require_payroll_unlock("staff_admin"):
        return

    # フィルタ
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        show_excluded = st.checkbox("経営者・FCオーナーも表示", value=False, key="staff_show_excluded")
    with col_f2:
        show_inactive = st.checkbox("退職者も表示", value=False, key="staff_show_inactive")

    staffs = shift_db.get_all_staff(
        active_only=not show_inactive,
        for_payroll=not show_excluded,
    )
    if not staffs:
        st.info("該当するスタッフがいません")
        return

    rows = []
    for s in staffs:
        rows.append({
            "ID": s["id"],
            "本名": s["display_name"],
            "通称": s["nickname"] or "",
            "店舗": STORE_CODE_TO_NAME.get(s["primary_store"], s["primary_store"]),
            "役職": s["position"] or "スタッフ",
            "雇用": s["employment_type"] or "アルバイト",
            "時給": _safe_int(s["hourly_wage"], 0),
            "月給": _safe_int(s["base_monthly_salary"], 0),
            "所定h/月": _safe_int(s["monthly_standard_hours"], 176),
            "役職給/h": _safe_int(s["position_allowance_per_hour"], 0),
            "週休日数": _safe_int(s["weekly_off_days"], 2),
            "月目標h": _safe_int(s["monthly_target_hours"], 160),
            "フレキ": bool(s["flexible"]),
            "アクティブ": bool(s["active"]),
        })
    df = pd.DataFrame(rows)
    edited = st.data_editor(
        df,
        use_container_width=True,
        hide_index=True,
        disabled=["ID", "本名"],
        column_config={
            "雇用": st.column_config.SelectboxColumn(options=["社員", "アルバイト", "業務委託"]),
            "時給": st.column_config.NumberColumn(min_value=0, step=10),
            "月給": st.column_config.NumberColumn(min_value=0, step=1000),
            "所定h/月": st.column_config.NumberColumn(min_value=0, step=1),
            "役職給/h": st.column_config.NumberColumn(min_value=0, step=10),
            "週休日数": st.column_config.NumberColumn(min_value=0, max_value=7, step=1),
            "月目標h": st.column_config.NumberColumn(min_value=0, step=4),
        },
        key="staff_admin_editor",
    )

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("変更を保存", type="primary", use_container_width=True):
            cnt = 0
            errors = []
            for i, row in edited.iterrows():
                orig = df.iloc[i]
                changed = {}
                try:
                    if row["通称"] != orig["通称"]: changed["nickname"] = row["通称"] or ""
                    if row["役職"] != orig["役職"]: changed["position"] = row["役職"] or "スタッフ"
                    if row["雇用"] != orig["雇用"]: changed["employment_type"] = row["雇用"] or "アルバイト"
                    if row["時給"] != orig["時給"]: changed["hourly_wage"] = _safe_int(row["時給"], 0)
                    if row["月給"] != orig["月給"]: changed["base_monthly_salary"] = _safe_int(row["月給"], 0)
                    if row["所定h/月"] != orig["所定h/月"]: changed["monthly_standard_hours"] = _safe_int(row["所定h/月"], 176)
                    if row["役職給/h"] != orig["役職給/h"]: changed["position_allowance_per_hour"] = _safe_int(row["役職給/h"], 0)
                    if row["週休日数"] != orig["週休日数"]: changed["weekly_off_days"] = _safe_int(row["週休日数"], 2)
                    if row["月目標h"] != orig["月目標h"]: changed["monthly_target_hours"] = _safe_int(row["月目標h"], 160)
                    if row["フレキ"] != orig["フレキ"]: changed["flexible"] = bool(row["フレキ"])
                    if row["アクティブ"] != orig["アクティブ"]: changed["active"] = bool(row["アクティブ"])
                    if changed:
                        shift_db.update_staff(row["ID"], **changed)
                        cnt += 1
                except Exception as e:
                    errors.append(f"{row['本名']}: {e}")
            if errors:
                for e in errors:
                    st.error(e)
            st.success(f"{cnt}名のスタッフ情報を更新しました")
            st.rerun()
    with col2:
        _csv_download(edited, f"mosh_staff_master_{date.today().strftime('%Y-%m')}.csv")

    # ── 退職処理 ──
    st.markdown("---")
    st.markdown("#### 退職処理")
    st.caption("退職スタッフはアクティブ=falseにします。打刻・シフト記録は保持され、新規シフトには表示されなくなります。")
    active_staffs = [s for s in staffs if s["active"]]
    if active_staffs:
        target_name = st.selectbox(
            "退職するスタッフを選択",
            [""] + [s["display_name"] for s in active_staffs],
            key="deactivate_target",
        )
        if target_name and st.button(f"{target_name} を退職処理する", key="deactivate_btn"):
            target = next((s for s in active_staffs if s["display_name"] == target_name), None)
            if target:
                shift_db.deactivate_staff(target["id"])
                st.success(f"{target_name} を退職処理しました（アクティブ=false）")
                st.rerun()

    # 再アクティブ化（退職取消）
    inactive_staffs = [s for s in staffs if not s["active"]]
    if inactive_staffs:
        st.markdown("##### 退職取消（再アクティブ化）")
        reactivate_name = st.selectbox(
            "再アクティブ化するスタッフ",
            [""] + [s["display_name"] for s in inactive_staffs],
            key="reactivate_target",
        )
        if reactivate_name and st.button(f"{reactivate_name} をアクティブに戻す", key="reactivate_btn"):
            target = next((s for s in inactive_staffs if s["display_name"] == reactivate_name), None)
            if target:
                shift_db.update_staff(target["id"], active=True)
                st.success(f"{reactivate_name} をアクティブに戻しました")
                st.rerun()

    # ── 新規スタッフ追加 ──
    st.markdown("---")
    with st.expander("新規スタッフを追加"):
        with st.form("add_staff_form"):
            c1, c2 = st.columns(2)
            with c1:
                new_display_name = st.text_input("本名（display_name）*", placeholder="例: 山田太郎")
                new_last_name = st.text_input("姓", placeholder="例: 山田")
                new_first_name = st.text_input("名", placeholder="例: 太郎")
                new_nickname = st.text_input("通称", placeholder="例: タロー")
                new_username = st.text_input("ログインID*", placeholder="例: taro_kashiwa")
            with c2:
                new_store = st.selectbox("主所属店舗", [c for c, _ in STORE_OPTIONS],
                                            format_func=lambda c: STORE_CODE_TO_NAME.get(c, c))
                new_position = st.selectbox("役職",
                    ["スタッフ", "店長", "副店長", "店長代理（共同）", "研修生", "事務", "FCオーナー", "マネージャー"])
                new_employment = st.selectbox("雇用形態", ["アルバイト", "社員", "業務委託"])
                new_hourly = st.number_input("時給（アルバイト用）", min_value=0, step=10, value=0)
                new_monthly = st.number_input("月給（社員用）", min_value=0, step=1000, value=0)

            submitted = st.form_submit_button("追加", type="primary")
            if submitted:
                if not new_display_name.strip() or not new_username.strip():
                    st.error("本名 と ログインID は必須です")
                else:
                    try:
                        # 1. users 認証アカウント作成
                        existing_users = mosh_db.get_all_users()
                        if any(u["username"] == new_username.strip() for u in existing_users):
                            st.error(f"ログインID '{new_username}' は既に使われています")
                        else:
                            mosh_db.add_user(
                                username=new_username.strip(),
                                password="MOSH4148",
                                role="staff",
                                store="",
                            )
                            # 2. staff_master 追加
                            staff_id = shift_db.upsert_staff(
                                display_name=new_display_name.strip(),
                                last_name=new_last_name.strip(),
                                first_name=new_first_name.strip(),
                                nickname=new_nickname.strip(),
                                short_name=(new_nickname.strip() or new_display_name.strip())[:6],
                                primary_store=new_store,
                                available_stores=[new_store],
                                position=new_position,
                                employment_type=new_employment,
                                hourly_wage=int(new_hourly),
                                base_monthly_salary=int(new_monthly),
                                active=True,
                                include_in_shift=True,
                                include_in_payroll=(new_position not in ("代表", "共同経営", "FCオーナー")),
                            )
                            # 3. users.staff_id にリンク
                            with shift_db.get_conn() as conn:
                                with conn.cursor() as cur:
                                    cur.execute("UPDATE users SET staff_id = %s WHERE username = %s",
                                                (staff_id, new_username.strip()))
                            st.success(f"✅ {new_display_name} を追加しました（初期PW: MOSH4148）")
                            st.rerun()
                    except Exception as e:
                        st.error(f"追加失敗: {e}")


# ─────────────────────────────────────────
# 7. 店舗マスター管理（簡易・owner のみ）
# ─────────────────────────────────────────

def render_store_admin_tab(user: dict):
    if user.get("role") != "owner":
        st.error("この画面は owner 専用です")
        return
    if not require_payroll_unlock("store_admin"):
        return

    st.markdown("### 店舗マスター")
    stores = shift_db.get_stores_master(active_only=False)
    df = pd.DataFrame([{
        "コード": s["code"],
        "店舗名": s["display_name"],
        "月間売上目標": s["monthly_target_sales"],
        "目標人件比%": float(s["target_labor_cost_ratio"]),
        "FC": s["is_franchise"],
        "アクティブ": s["active"],
    } for s in stores])
    edited = st.data_editor(df, use_container_width=True, hide_index=True,
                              disabled=["コード"],
                              key="store_admin_editor")
    if st.button("店舗情報を保存", type="primary"):
        for i, row in edited.iterrows():
            orig = df.iloc[i]
            changed = {}
            if row["店舗名"] != orig["店舗名"]: changed["display_name"] = row["店舗名"]
            if row["月間売上目標"] != orig["月間売上目標"]: changed["monthly_target_sales"] = int(row["月間売上目標"])
            if row["目標人件比%"] != orig["目標人件比%"]: changed["target_labor_cost_ratio"] = float(row["目標人件比%"])
            if row["FC"] != orig["FC"]: changed["is_franchise"] = bool(row["FC"])
            if row["アクティブ"] != orig["アクティブ"]: changed["active"] = bool(row["アクティブ"])
            if changed:
                shift_db.update_store_master(row["コード"], **changed)
        st.success("店舗情報を更新しました")
        st.rerun()
