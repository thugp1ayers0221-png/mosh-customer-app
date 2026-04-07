"""
MOSH 顧客管理アプリ
Streamlit製・スマホ対応・MOSHブランドカラー
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, date
import random
import string
import io
import base64
import os
import html as _html
import importlib
import mosh_db as db

# MOSHロゴをbase64エンコード
_logo_b64 = ""
_logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "mosh_logo.jpg")
if os.path.exists(_logo_path):
    with open(_logo_path, "rb") as _f:
        _logo_b64 = base64.b64encode(_f.read()).decode()

# ─── AI機能（オプション：APIキーがない場合はスキップ）───
try:
    import anthropic
    _anthropic_client = anthropic.Anthropic(api_key=st.secrets.get("ANTHROPIC_API_KEY", ""))
    HAS_ANTHROPIC = True
except Exception:
    HAS_ANTHROPIC = False

try:
    from openai import OpenAI as _OpenAI
    _openai_client = _OpenAI(api_key=st.secrets.get("OPENAI_API_KEY", ""))
    HAS_OPENAI = True
except Exception:
    HAS_OPENAI = False

_GOOGLE_AI_KEY = st.secrets.get("GOOGLE_AI_API_KEY", "")
HAS_GEMINI = False
_gemini_client = None
_gemini_use_new_sdk = False
if _GOOGLE_AI_KEY:
    try:
        from google import genai
        _gemini_client = genai.Client(api_key=_GOOGLE_AI_KEY)
        HAS_GEMINI = True
        _gemini_use_new_sdk = True
    except Exception:
        try:
            import google.generativeai as _genai_legacy
            _genai_legacy.configure(api_key=_GOOGLE_AI_KEY)
            _gemini_client = _genai_legacy
            HAS_GEMINI = True
            _gemini_use_new_sdk = False
        except Exception:
            pass

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except Exception:
    HAS_PIL = False

# ─────────────────────────────────────────
# ページ設定
# ─────────────────────────────────────────
st.set_page_config(
    page_title="MOSH 顧客管理",
    page_icon="🫧",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# DBスキーマの自動マイグレーション（起動時に必ず実行・エラーは無視）
if "db_migrated" not in st.session_state:
    try:
        db.migrate_db()
        st.session_state.db_migrated = True
    except Exception:
        pass

# ─── キャッシュ付きDB取得 ───
@st.cache_data(ttl=300, show_spinner=False)
def cached_get_customers(store=None, period=None, rank=None, search=None, limit=200):
    return db.get_customers(store=store, period=period, rank=rank, search=search, limit=limit)

@st.cache_data(ttl=600, show_spinner=False)
def cached_get_stores():
    return db.get_stores()

@st.cache_data(ttl=600, show_spinner=False)
def cached_get_available_periods():
    return db.get_available_periods()

@st.cache_data(ttl=300, show_spinner=False)
def cached_get_dashboard_stats(store=None, period=None):
    return db.get_dashboard_stats(store=store, period=period)

@st.cache_data(ttl=600, show_spinner=False)
def cached_get_weekday_stats(store=None, period=None):
    return db.get_weekday_stats(store=store, period=period)

@st.cache_data(ttl=300, show_spinner=False)
def cached_get_all_stores_stats(period=None):
    """全店舗統計を1クエリで取得（ダッシュボード高速化）"""
    return db.get_all_stores_stats(period=period)

@st.cache_data(ttl=300, show_spinner=False)
def cached_get_s_candidates():
    return db.get_s_candidates()

@st.cache_data(ttl=120, show_spinner=False)
def cached_get_customer(cid):
    return db.get_customer(cid)

@st.cache_data(ttl=120, show_spinner=False)
def cached_get_visits(cid):
    return db.get_visits(cid)

@st.cache_data(ttl=120, show_spinner=False)
def cached_get_visit_stats(cid):
    return db.get_visit_stats(cid)

# ─────────────────────────────────────────
# MOSHブランドCSS（スマホ対応）
# ─────────────────────────────────────────
st.markdown("""
<style>
/* Google Fonts */
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@300;400;500;700&display=swap');

/* Stripe-inspired MOSH Design System */
:root {
  /* Brand */
  --mosh-primary:       #5BA4C9;
  --mosh-primary-hover: #4A93B8;
  --mosh-primary-light: #E8F4FA;
  --mosh-sky:           #A8D8EA;
  --mosh-cream:         #F5EFE0;
  --mosh-brown:         #6B4226;
  --mosh-dark:          #2D1F0F;
  --mosh-green:         #5B8F5F;

  /* Surfaces */
  --bg:             #FFFDF7;
  --surface:        #FFFFFF;
  --surface-hover:  #FAFAF7;
  --surface-muted:  #F7F5F0;

  /* Borders */
  --border:         #E8E0D4;
  --border-light:   #F0EBE3;

  /* Shadows (warm brown-tinted, Stripe multi-layer) */
  --shadow-1:       rgba(107,66,38,0.10);
  --shadow-2:       rgba(0,0,0,0.04);
  --shadow-hover:   rgba(107,66,38,0.18);

  /* Text */
  --text-primary:   #2D1F0F;
  --text-secondary: #6B7B8D;
  --text-tertiary:  #9E8B7D;

  /* Rank (unchanged) */
  --rank-s:  #C8922A;
  --rank-a:  #4AA8D8;
  --rank-b:  #c8b89a;
  --rank-c:  #AAAAAA;
}

/* 上部余白を削除 */
.stApp > header { display: none !important; }
[data-testid="stAppViewBlockContainer"] { padding-top: 0 !important; }
[data-testid="stMainBlockContainer"] { padding-top: 0 !important; }
.block-container { padding-top: 0.5rem !important; }
section.main > div:first-child { padding-top: 0 !important; }
section[data-testid="stSidebar"] + section { padding-top: 0 !important; }
.stMainPadding { padding-top: 0 !important; }
div[class*="appview-container"] { padding-top: 0 !important; }

/* 全体背景 */
.stApp {
  background-color: var(--bg);
  font-family: 'Noto Sans JP', sans-serif;
  -webkit-font-smoothing: antialiased;
}

/* ヘッダーバー (Stripe-style clean header) */
.mosh-header {
  background: var(--surface);
  padding: 14px 20px;
  border-radius: 0;
  margin: -1rem -1rem 1.5rem;
  display: flex;
  align-items: center;
  gap: 12px;
  border-bottom: 1px solid var(--border);
  box-shadow: 0 1px 3px var(--shadow-2), 0 1px 2px var(--shadow-1);
}
.mosh-logo {
  font-size: 1.6rem;
  font-weight: 600;
  color: var(--mosh-dark);
  letter-spacing: -0.5px;
  line-height: 1;
}
.mosh-logo span {
  font-size: 0.75rem;
  font-weight: 400;
  color: var(--text-secondary);
  display: block;
  letter-spacing: 0.5px;
}
.mosh-user-badge {
  margin-left: auto;
  font-size: 0.8rem;
  background: var(--surface-muted);
  padding: 4px 12px;
  border-radius: 4px;
  color: var(--mosh-brown);
  font-weight: 500;
  border: 1px solid var(--border-light);
}

/* 検索バー (Stripe-style) */
.search-wrap input {
  font-size: 1rem !important;
  border-radius: 6px !important;
  border: 1px solid var(--border) !important;
  padding: 10px 16px !important;
  transition: border-color 0.15s, box-shadow 0.15s !important;
}
.search-wrap input:focus {
  border-color: var(--mosh-primary) !important;
  box-shadow: 0 0 0 3px rgba(91,164,201,0.15) !important;
}

/* カード（ランク色帯つき - Stripe shadow system） */
.customer-card {
  background: var(--surface);
  border-radius: 6px;
  margin-bottom: 8px;
  border: 1px solid var(--border);
  box-shadow: 0 1px 3px var(--shadow-2), 0 1px 2px var(--shadow-1);
  display: flex;
  overflow: hidden;
  cursor: pointer;
  transition: box-shadow 0.15s, border-color 0.15s;
}
.customer-card:active {
  box-shadow: 0 4px 12px var(--shadow-hover), 0 2px 4px var(--shadow-2);
  border-color: var(--mosh-primary);
}
.card-rank-bar {
  width: 6px;
  flex-shrink: 0;
}
.card-rank-bar.rank-V { background: #A855F7; }
.card-rank-bar.rank-S { background: var(--rank-s); }
.card-rank-bar.rank-A { background: var(--rank-a); }
.card-rank-bar.rank-B { background: var(--rank-b); }
.card-rank-bar.rank-C { background: var(--rank-c); }
.card-body {
  flex: 1;
  padding: 10px 12px;
  min-width: 0;
}
.card-row1 {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 3px;
}
.card-name {
  font-size: 1.0rem;
  font-weight: 700;
  color: var(--mosh-dark);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.card-marks { font-size: 0.85rem; }
.card-trend-up   { color: #16A34A; font-weight:700; font-size:0.82rem; margin-left:auto; }
.card-trend-down { color: #DC2626; font-weight:700; font-size:0.82rem; margin-left:auto; }
.card-trend-new  { color: #7C3AED; font-weight:700; font-size:0.82rem; margin-left:auto; }
.card-trend-flat { color:#bbb; font-size:0.82rem; margin-left:auto; }
.card-row2 {
  display: flex;
  align-items: center;
  gap: 10px;
}
.card-store {
  font-size: 0.75rem;
  color: #999;
}
.card-this-month {
  font-size: 0.82rem;
  font-weight: 700;
  color: var(--mosh-brown);
  background: var(--surface-muted);
  padding: 1px 7px;
  border-radius: 4px;
}
.card-days-ago {
  font-size: 0.75rem;
  color: #aaa;
  margin-left: auto;
}
.card-days-ago.recent { color: #16A34A; font-weight: 600; }

/* カードリスト：2列構成（ランクバー＋ボタン）*/
.card-list > div[data-testid="stVerticalBlock"] > div[data-testid="stHorizontalBlock"] {
  gap: 3px !important;
  margin-bottom: 5px !important;
  align-items: stretch !important;
}
.card-list .stButton button {
  text-align: left !important;
  background: var(--surface) !important;
  border: 1px solid var(--border) !important;
  border-radius: 0 6px 6px 0 !important;
  padding: 10px 14px !important;
  box-shadow: 0 1px 2px var(--shadow-2) !important;
  height: auto !important;
  min-height: 64px !important;
  white-space: pre-line !important;
  color: var(--mosh-dark) !important;
  font-size: 0.9rem !important;
  line-height: 1.6 !important;
}
.card-list .stButton button:hover {
  background: var(--surface-hover) !important;
  box-shadow: 0 2px 6px var(--shadow-1), 0 1px 2px var(--shadow-2) !important;
}

/* ランクバッジ (Stripe-style: 4px radius, semi-transparent) */
.rank-badge {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 4px;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.5px;
}
.rank-V { background: linear-gradient(135deg,#6B21A8,#A855F7); color: white; letter-spacing:1px; }
.rank-S { background: rgba(200,146,42,0.15); color: #92690C; border: 1px solid rgba(200,146,42,0.3); }
.rank-A { background: rgba(74,168,216,0.15); color: #1A5F80; border: 1px solid rgba(74,168,216,0.3); }
.rank-B { background: rgba(200,184,154,0.2); color: #6B4226; border: 1px solid rgba(200,184,154,0.4); }
.rank-C { background: rgba(170,170,170,0.15); color: #555; border: 1px solid rgba(170,170,170,0.3); }

/* トレンド表示 */
.trend-up   { color: #16A34A; font-weight:700; font-size:1rem; }
.trend-down { color: #DC2626; font-weight:700; font-size:1rem; }
.trend-flat { color: #9CA3AF; font-size:0.9rem; }

/* トップ替え警告（3回到達） */
.top-change-alert {
  background: #FEE2E2;
  border: 2px solid #EF4444;
  border-radius: 6px;
  padding: 10px 14px;
  color: #991B1B;
  font-weight: 700;
  text-align: center;
  margin-bottom: 10px;
}
.top-change-ok {
  background: #F0FDF4;
  border: 1.5px solid #86EFAC;
  border-radius: 6px;
  padding: 10px 14px;
  color: #166534;
  text-align: center;
  margin-bottom: 10px;
}

/* フィルターバー */
.filter-bar {
  background: var(--surface-muted);
  border-radius: 6px;
  border: 1px solid var(--border-light);
  padding: 12px 14px;
  margin-bottom: 16px;
}

/* メトリクスカード (Stripe-style) */
.metric-card {
  background: var(--surface);
  border-radius: 6px;
  padding: 14px 16px;
  text-align: center;
  border: 1px solid var(--border);
  box-shadow: 0 1px 3px var(--shadow-2), 0 1px 2px var(--shadow-1);
}
.metric-value {
  font-size: 2rem;
  font-weight: 300;
  color: var(--text-primary);
  line-height: 1.1;
  letter-spacing: -0.5px;
}
.metric-label {
  font-size: 0.72rem;
  color: var(--text-tertiary);
  margin-top: 4px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

/* ナビゲーションタブ (Stripe underline-style) */
.nav-tabs {
  display: flex;
  gap: 0;
  margin-bottom: 16px;
  border-bottom: 1px solid var(--border);
}
.nav-tab {
  flex: 1;
  text-align: center;
  padding: 10px 8px;
  border-radius: 0;
  font-size: 0.82rem;
  font-weight: 500;
  cursor: pointer;
  background: transparent;
  color: var(--text-secondary);
  border: none;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  transition: color 0.15s, border-color 0.15s;
}
.nav-tab.active {
  background: transparent;
  color: var(--text-primary);
  border-bottom: 2px solid var(--mosh-primary);
  font-weight: 700;
}

/* 顧客詳細 (Stripe-style card) */
.customer-header {
  background: var(--surface);
  border-radius: 6px;
  padding: 18px;
  margin-bottom: 14px;
  border: 1px solid var(--border);
  box-shadow: 0 1px 3px var(--shadow-2), 0 1px 2px var(--shadow-1);
}
.customer-name {
  font-size: 1.4rem;
  font-weight: 300;
  color: var(--text-primary);
  letter-spacing: -0.3px;
}
.visit-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px solid var(--border-light);
  font-size: 0.85rem;
}
.visit-date { color: var(--mosh-brown); font-weight: 500; }
.visit-store { color: #888; }
.visit-type-top { color: var(--mosh-green); font-size: 0.75rem; }
.visit-type-cafe { color: var(--mosh-sky); font-size: 0.75rem; }

/* 警告バナー（クロスストア） */
.cross-store-banner {
  background: #FFF3CD;
  border: 1px solid #FBBF24;
  border-radius: 6px;
  padding: 10px 14px;
  font-size: 0.82rem;
  color: #92400E;
  margin-bottom: 12px;
}

/* ログイン画面 (Stripe-style) */
.login-wrap {
  max-width: 360px;
  margin: 60px auto 0;
  padding: 32px 28px;
  background: var(--surface);
  border-radius: 8px;
  border: 1px solid var(--border);
  box-shadow: 0 4px 6px var(--shadow-2), 0 10px 20px var(--shadow-1);
}
.login-logo {
  text-align: center;
  font-size: 2rem;
  font-weight: 300;
  color: var(--text-primary);
  margin-bottom: 6px;
  letter-spacing: -0.5px;
}
.login-sub {
  text-align: center;
  font-size: 0.8rem;
  color: var(--text-secondary);
  margin-bottom: 24px;
}

/* Streamlitデフォルト上書き (Stripe-style) */
.stButton > button {
  border-radius: 6px !important;
  font-family: 'Noto Sans JP', sans-serif !important;
  font-weight: 500 !important;
  transition: box-shadow 0.15s, filter 0.15s !important;
}
/* Primary button */
[data-testid="baseButton-primary"] {
  background-color: var(--mosh-primary) !important;
  color: white !important;
  border: none !important;
  border-radius: 6px !important;
  box-shadow: 0 1px 3px var(--shadow-1), 0 1px 2px var(--shadow-2) !important;
}
[data-testid="baseButton-primary"]:hover {
  background-color: var(--mosh-primary-hover) !important;
  box-shadow: 0 4px 8px var(--shadow-hover), 0 2px 4px var(--shadow-2) !important;
}
/* 顧客カードボタン 共通 */
[data-testid="baseButton-secondary"] {
  width: 100% !important;
  border-radius: 6px !important;
  padding: 12px 16px !important;
  text-align: center !important;
  font-size: 15px !important;
  font-weight: 600 !important;
  line-height: 1.6 !important;
  min-height: 56px !important;
  border: 1px solid var(--border) !important;
  box-shadow: 0 1px 2px var(--shadow-2) !important;
  margin-bottom: 6px !important;
  transition: box-shadow 0.15s, filter 0.15s ease !important;
}
[data-testid="baseButton-secondary"] p {
  white-space: pre-line !important;
  text-align: center !important;
  margin: 0 !important;
}
[data-testid="baseButton-secondary"]:hover {
  box-shadow: 0 2px 6px var(--shadow-1), 0 1px 2px var(--shadow-2) !important;
  filter: brightness(0.97) !important;
}
/* ランク別カラー - stElementContainerレベルで:has()を使用（DOM構造確認済み）*/
div[data-testid="stElementContainer"]:has(.rank-s) + div[data-testid="stElementContainer"] button,
div[data-testid="stElementContainer"]:has(.rank-v) + div[data-testid="stElementContainer"] button {
  background-color: #FFF3CD !important; border: 2px solid #C8922A !important;
  border-left: 6px solid #C8922A !important; color: #6B4226 !important;
}
div[data-testid="stElementContainer"]:has(.rank-a) + div[data-testid="stElementContainer"] button {
  background-color: #D6EEF8 !important; border: 2px solid #A8D8EA !important;
  border-left: 6px solid #4AA8D8 !important; color: #1A5F80 !important;
}
div[data-testid="stElementContainer"]:has(.rank-b) + div[data-testid="stElementContainer"] button {
  background-color: #FAF5EE !important; border: 2px solid #c8b89a !important;
  border-left: 6px solid #c8b89a !important; color: #6B4226 !important;
}
.stSelectbox > div > div,
.stTextInput > div > div > input {
  border-radius: 6px !important;
  border-color: var(--border) !important;
  font-family: 'Noto Sans JP', sans-serif !important;
  transition: border-color 0.15s, box-shadow 0.15s !important;
}
.stSelectbox > div > div:focus-within,
.stTextInput > div > div > input:focus {
  border-color: var(--mosh-primary) !important;
  box-shadow: 0 0 0 3px rgba(91,164,201,0.15) !important;
}
/* Streamlit tabs (Stripe underline) */
div[data-testid="stTabs"] button {
  font-family: 'Noto Sans JP', sans-serif !important;
  border-radius: 0 !important;
  border-bottom: 2px solid transparent !important;
  background: transparent !important;
  font-weight: 500 !important;
  color: var(--text-secondary) !important;
  transition: color 0.15s, border-color 0.15s !important;
}
div[data-testid="stTabs"] button[aria-selected="true"] {
  border-bottom: 2px solid var(--mosh-primary) !important;
  color: var(--text-primary) !important;
  font-weight: 700 !important;
}
div[data-testid="stTabs"] [data-testid="stMarkdownContainer"] {
  color: inherit !important;
}

/* ─── Streamlit UI要素を非表示（GitHub/Fork/デプロイ/フッター全て）─── */
header[data-testid="stHeader"]         { display: none !important; }
footer                                  { display: none !important; }
#MainMenu                               { display: none !important; }
[data-testid="stToolbar"]              { display: none !important; }
[data-testid="stDecoration"]           { display: none !important; }
.stDeployButton                        { display: none !important; }
[data-testid="stStatusWidget"]         { display: none !important; }
[data-testid="stToolbarActionButton"]  { display: none !important; }
/* アプリ下部のStreamlit広告バナー（"Created by" / "Hosted with Streamlit"）*/
[data-testid="stBottom"]               { display: none !important; }
[class*="viewerBadge"]                 { display: none !important; }
[class*="badge"]                       { display: none !important; }
#stDecoration                          { display: none !important; }
.st-emotion-cache-1dp5vir              { display: none !important; }
.st-emotion-cache-15ecox0              { display: none !important; }
/* 上部のStreamlitツールバー帯（"Hosted with Streamlit" 上部）*/
[data-testid="stAppViewBlockContainer"] > div:first-child { padding-top: 0 !important; }
/* 再実行中の白いもやオーバーレイを非表示 */
[data-testid="stAppViewBlockContainer"] { opacity: 1 !important; }
.main .block-container { opacity: 1 !important; }
div[class*="withScreencast"] { opacity: 1 !important; }
iframe[title="streamlit_component"] { opacity: 1 !important; }
div[data-stale="true"] { opacity: 1 !important; filter: none !important; }
[class*="stale"] { opacity: 1 !important; }
div[aria-live] > div { opacity: 1 !important; }
.stApp > div { opacity: 1 !important; }
/* Streamlitの白いもや（実行中オーバーレイ）を完全に非表示 */
div[data-testid="stAppRunningIcon"] { display: none !important; }
.st-emotion-cache-uf99v8 { background: none !important; }
[class*="AppRunning"] { display: none !important; }

/* ─── MOSHローディングアニメーション ─── */
@keyframes mosh-wobble {
  0%   { transform: rotate(-5deg) scale(1);   }
  25%  { transform: rotate( 5deg) scale(1.04);}
  50%  { transform: rotate(-3deg) scale(1);   }
  75%  { transform: rotate( 3deg) scale(1.02);}
  100% { transform: rotate(-5deg) scale(1);   }
}
@keyframes mosh-float {
  0%,100% { transform: translateY(0);  }
  50%      { transform: translateY(-8px); }
}
[data-testid="stSpinner"] {
  display: flex !important;
  flex-direction: column !important;
  align-items: center !important;
  justify-content: center !important;
  padding: 24px !important;
}
[data-testid="stSpinner"] svg { display: none !important; }
[data-testid="stSpinner"] > div > p {
  font-family: 'Noto Sans JP', sans-serif !important;
  font-size: 0.85rem !important;
  color: var(--text-secondary) !important;
  margin-top: 8px !important;
}
</style>
""", unsafe_allow_html=True)

# MOSHキャラクターをローディングスピナーに注入
if _logo_b64:
    st.markdown(f"""
<style>
[data-testid="stSpinner"] > div::before {{
  content: "";
  display: block;
  width: 130px;
  height: 130px;
  background-image: url("data:image/jpeg;base64,{_logo_b64}");
  background-size: contain;
  background-repeat: no-repeat;
  background-position: center;
  border-radius: 8px;
  animation: mosh-wobble 0.8s ease-in-out infinite, mosh-float 1.4s ease-in-out infinite;
  margin: 0 auto 8px;
}}
</style>
""", unsafe_allow_html=True)
else:
    st.markdown("""
<style>
[data-testid="stSpinner"] > div::before {
  content: "🫧";
  font-size: 3rem;
  display: block;
  text-align: center;
  animation: mosh-wobble 0.8s ease-in-out infinite, mosh-float 1.4s ease-in-out infinite;
  margin-bottom: 8px;
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────
# セッション初期化 + ログイン記憶チェック
# ─────────────────────────────────────────
if "user" not in st.session_state:
    st.session_state.user = None
if "page" not in st.session_state:
    st.session_state.page = "home"
if "selected_customer" not in st.session_state:
    st.session_state.selected_customer = None
if "login_token" not in st.session_state:
    st.session_state.login_token = None
if "invite_action" not in st.session_state:
    st.session_state.invite_action = None  # "register" or "login"

# 共通パスワード（全スタッフ共通）
SHARED_PASSWORD = "MOSH4148"

# URLトークンからの自動ログイン
if st.session_state.user is None:
    params = st.query_params
    saved_token = params.get("t", None)
    if saved_token:
        auto_user = db.verify_session_token(saved_token)
        if auto_user:
            st.session_state.user = auto_user
            st.session_state.login_token = saved_token

# ─── URLパラメータからページ復元（スマホ戻るボタン対応）───
if st.session_state.user is not None:
    _p = st.query_params.get("p", "home")
    if _p == "detail":
        _id = st.query_params.get("id", None)
        if _id and str(_id).isdigit():
            st.session_state.selected_customer = int(_id)
            st.session_state.page = "detail"
    else:
        # homeに戻ってきたらdetailページをリセット
        if st.session_state.page == "detail" and "id" not in st.query_params:
            st.session_state.page = "home"
            st.session_state.selected_customer = None

# ─── Cookie からセッショントークンを読み込んでURLに乗せる ───
# （ページロード時に毎回実行。cookieにトークンがあればURL経由で自動ログインを発動）
st.components.v1.html("""
<script>
(function(){
  function getCookie(name) {
    try {
      var cookies = (window.parent || window).document.cookie.split(';');
      for (var i = 0; i < cookies.length; i++) {
        var c = cookies[i].trim();
        if (c.startsWith(name + '=')) return c.substring(name.length + 1);
      }
    } catch(e) {}
    return null;
  }
  var token = getCookie('mosh_token');
  var win = window.parent || window;
  var params = new URLSearchParams(win.location.search);

  // cookieにトークンがあり、URLにまだ乗っていない場合だけリダイレクト
  if (token && !params.get('t')) {
    params.set('t', token);
    win.location.search = params.toString();
    return;
  }

  // ─── スクロール位置の復元 ───
  // detail→homeに戻ってきたとき、保存済みスクロール位置を復元
  var isDetail = params.get('p') === 'detail';
  if (!isDetail) {
    var savedScroll = sessionStorage.getItem('mosh_scroll_y');
    if (savedScroll) {
      // 少し遅延させてStreamlitのレンダリング完了後にスクロール
      setTimeout(function() {
        try {
          (win.document.querySelector('.main') || win).scrollTo(0, parseInt(savedScroll));
        } catch(e) {
          win.scrollTo(0, parseInt(savedScroll));
        }
        sessionStorage.removeItem('mosh_scroll_y');
      }, 400);
    }
    // detailページへの遷移前に現在位置を保存するリスナー
    win.document.addEventListener('click', function(e) {
      var btn = e.target && e.target.closest('button');
      if (btn) {
        // ボタンクリック時のスクロール位置を保存
        try {
          var scrollEl = win.document.querySelector('.main') || win;
          sessionStorage.setItem('mosh_scroll_y', scrollEl.scrollTop || win.scrollY || 0);
        } catch(ex) {}
      }
    }, true);
  }

  // ─── detailページ: replaceStateで余分な履歴エントリを削除 ───
  // Streamlitが query_params.update() + rerun() で2回historyをプッシュする問題を解消
  if (isDetail) {
    // 現在のURLで履歴を上書き（pushStateではなくreplaceState）
    try {
      win.history.replaceState(null, '', win.location.href);
    } catch(e) {}
  }

  // スマホ戻るボタン: popstateでリロード
  win.addEventListener('popstate', function(e) {
    win.location.reload();
  });
})();
</script>
""", height=0)

def set_auth_cookie(token: str):
    """ログイントークンをブラウザcookieに保存（30日）"""
    st.components.v1.html(f"""<script>
(function(){{
  var d = new Date();
  d.setTime(d.getTime() + 30*24*60*60*1000);
  var cookie = 'mosh_token={token}; expires=' + d.toUTCString() + '; path=/; SameSite=Lax';
  try {{ (window.parent || window).document.cookie = cookie; }} catch(e) {{}}
}})();
</script>""", height=0)

def clear_auth_cookie():
    """ログアウト時にcookieを削除"""
    st.components.v1.html("""<script>
(function(){
  var cookie = 'mosh_token=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
  try { (window.parent || window).document.cookie = cookie; } catch(e) {}
})();
</script>""", height=0)

RANK_LABEL = {"V": "VIP", "S": "S", "A": "A"}
RANK_DESC  = {
    "V": "VIP（Masons専用）",
    "S": "超常連VIP",
    "A": "名前ありリピーター",
}
RANK_ORDER = {"V": 0, "S": 1, "A": 2}
SERVICE_LABEL = {
    "normal":     "通常",
    "top_change": "🔄 トップ替え",
    "cafe":       "☕ カフェ",
}

# ─────────────────────────────────────────
# ログイン画面
# ─────────────────────────────────────────
def show_login():
    st.markdown("""
    <div class="login-wrap">
      <div style="text-align:center;margin-bottom:4px;">
        <img src="https://shisha-mosh.jp/images/top/logo.png"
             alt="MOSH" style="height:40px;object-fit:contain;" />
      </div>
      <div class="login-sub">顧客管理システム</div>
    </div>
    """, unsafe_allow_html=True)

    with st.container():
        col1, col2, col3 = st.columns([1,2,1])
        with col2:
            st.markdown("#### ログイン")
            username = st.text_input("ユーザー名", placeholder="ユーザー名を入力")
            password = st.text_input("パスワード", type="password", placeholder="パスワードを入力")
            remember = st.checkbox("ログイン状態を保持する（30日間）", value=True)
            if st.button("ログイン", use_container_width=True, type="primary"):
                user = db.verify_user(username, password)
                if user:
                    st.session_state.user = user
                    if remember:
                        token = db.create_session_token(user["id"])
                        st.session_state.login_token = token
                        st.query_params["t"] = token
                        set_auth_cookie(token)
                    st.rerun()
                else:
                    st.error("ユーザー名またはパスワードが違います")

# ─────────────────────────────────────────
# ヘッダー
# ─────────────────────────────────────────
def show_header():
    user = st.session_state.user
    role_label = {"owner":"オーナー","manager":"店長","staff":"スタッフ","executive":"経営陣"}.get(user["role"],"")
    store_label = f" · {user['store']}" if user.get("store") else ""
    st.markdown(f"""
    <div class="mosh-header">
      <div style="display:flex;align-items:center;gap:10px;">
        <img src="https://shisha-mosh.jp/images/top/logo.png"
             alt="MOSH" style="height:28px;object-fit:contain;" />
        <span style="font-size:0.72rem;color:var(--mosh-brown);font-weight:500;letter-spacing:0.5px;">顧客管理</span>
      </div>
      <div class="mosh-user-badge">{user['username']} / {role_label}{store_label}</div>
    </div>
    """, unsafe_allow_html=True)

# ─────────────────────────────────────────
# ホーム（顧客一覧）
# ─────────────────────────────────────────
def show_home():
    from datetime import date as _date
    user = st.session_state.user
    today = _date.today()

    # ── 検索バー（最上部・全幅）──
    search = st.text_input(
        "search", placeholder="🔍 名前で検索...",
        label_visibility="collapsed",
        key="home_search"
    )

    # ── フィルター（店舗・期間、コンパクト2列）──
    stores  = ["全店舗"] + cached_get_stores()
    periods = ["全期間"] + cached_get_available_periods()

    if user["role"] == "manager" and user.get("store"):
        default_store  = user["store"]
        store_disabled = True
    else:
        default_store  = "全店舗"
        store_disabled = False

    fc1, fc2 = st.columns(2)
    with fc1:
        sel_store = st.selectbox(
            "店舗", stores,
            index=stores.index(default_store) if default_store in stores else 0,
            disabled=store_disabled,
            label_visibility="collapsed",
        )
    with fc2:
        sel_period = st.selectbox(
            "期間", periods,
            label_visibility="collapsed",
        )

    store_q  = None if sel_store == "全店舗" else sel_store
    period_q = None if sel_period == "全期間" else sel_period
    search_q = search.strip() if search.strip() else None

    customers = cached_get_customers(store=store_q, period=period_q, search=search_q)

    # 来店ログ0件は非表示（検索時は除く）
    # 期間指定あり → その期間に来店した人のみ表示
    # 期間指定なし（全期間）→ 全員表示（total_visits > 0 は全員該当）
    if not search_q and period_q:
        customers = [c for c in customers if (c.get("period_visits") or 0) > 0]

    # S候補の通知（専用軽量クエリ）
    s_candidates = cached_get_s_candidates()
    if s_candidates and user["role"] in ("owner","manager","executive"):
        with st.expander(f"⚠️ Sランク候補 {len(s_candidates)}名（来店10回以上・未昇格）"):
            # 一括昇格ボタン
            if user["role"] in ("owner","executive"):
                if st.button(f"🚀 {len(s_candidates)}名を全員Sに一括昇格", type="primary", use_container_width=True):
                    ids = [c["id"] for c in s_candidates]
                    db.bulk_set_rank(ids, "S", user["username"])
                    cached_get_customers.clear()
                    st.success(f"{len(s_candidates)}名をSランクに昇格しました")
                    st.rerun()
            for c in s_candidates[:5]:
                col1, col2 = st.columns([4,1])
                with col1:
                    st.write(f"**{c['name']}** ({c['primary_store']}) — {c['total_visits']}回来店")
                with col2:
                    if st.button("S昇格", key=f"promote_{c['id']}"):
                        db.set_rank(c["id"], "S", user["username"])
                        st.cache_data.clear()
                        st.rerun()

    # ── 手動マージ（owner/manager/executive のみ）──
    if user["role"] in ("owner", "manager", "executive"):
        with st.expander("🔗 手動マージ（同一人物の統合）"):
            st.caption("2名を検索して選択し、どちらかにまとめます。統合元の来店履歴が統合先に移動します。")
            mc1, mc2 = st.columns(2)

            with mc1:
                st.markdown("**統合元（消える側）**")
                ma_search = st.text_input("名前で検索", key="merge_search_a", placeholder="例：てらかど")
                ma_results = db.get_customers(search=ma_search.strip() or None, limit=20) if ma_search.strip() else []
                ma_options = {f"{c['name']} / {c['primary_store']} / {c['total_visits']}回": c for c in ma_results}
                ma_sel = st.selectbox("統合元を選択", ["---"] + list(ma_options.keys()), key="merge_sel_a")
                cust_a = ma_options.get(ma_sel)
                if cust_a:
                    st.info(f"🗑 **{cust_a['name']}**\n{cust_a['primary_store']} / {cust_a.get('rank','–')}ランク / {cust_a['total_visits']}回")

            with mc2:
                st.markdown("**統合先（残る側）**")
                mb_search = st.text_input("名前で検索", key="merge_search_b", placeholder="例：てらかど")
                mb_results = db.get_customers(search=mb_search.strip() or None, limit=20) if mb_search.strip() else []
                mb_options = {f"{c['name']} / {c['primary_store']} / {c['total_visits']}回": c for c in mb_results}
                mb_sel = st.selectbox("統合先を選択", ["---"] + list(mb_options.keys()), key="merge_sel_b")
                cust_b = mb_options.get(mb_sel)
                if cust_b:
                    st.success(f"✅ **{cust_b['name']}**\n{cust_b['primary_store']} / {cust_b.get('rank','–')}ランク / {cust_b['total_visits']}回")

            if cust_a and cust_b:
                if cust_a["id"] == cust_b["id"]:
                    st.warning("同じ顧客が選択されています")
                else:
                    st.markdown(f"**{cust_a['name']}** → **{cust_b['name']}** に統合します")
                    if st.button("✅ マージ実行", type="primary", key="manual_merge_btn"):
                        db.merge_customers(cust_a["id"], cust_b["id"], user["username"])
                        st.cache_data.clear()
                        st.success(f"✅ {cust_a['name']} を {cust_b['name']} に統合しました")
                        st.rerun()

    # 件数表示
    st.caption(f"{sel_store} · {sel_period} · {len(customers)}名")

    # ── 顧客カード一覧（st.button + :has() CSS で色分け）──
    PAGE_SIZE = 50
    if "customer_page" not in st.session_state:
        st.session_state.customer_page = 1
    # フィルター変更時にページリセット
    filter_key = f"{store_q}_{period_q}_{search_q}"
    if st.session_state.get("_last_filter") != filter_key:
        st.session_state.customer_page = 1
        st.session_state._last_filter = filter_key

    page = st.session_state.customer_page
    shown = customers[: page * PAGE_SIZE]

    for c in shown:
        name      = c['name']
        store_lbl = c['primary_store'] or '未設定'
        rank      = c.get("rank", "C")
        # 期間指定あり → その期間の来店数、なし（全期間）→ 累計来店数
        visit_cnt = (c.get("period_visits") or 0) if period_q else (c.get("total_visits") or 0)
        label     = f"{name}\n{store_lbl}  ·  {visit_cnt}回"

        st.markdown(f'<div class="rank-{rank.lower()}"></div>', unsafe_allow_html=True)
        if st.button(label, key=f"open_{c['id']}", use_container_width=True):
            st.session_state.selected_customer = c["id"]
            st.session_state.page = "detail"
            new_params = {"p": "detail", "id": str(c["id"])}
            if st.session_state.login_token:
                new_params["t"] = st.session_state.login_token
            st.query_params.update(new_params)
            st.rerun()

    if len(customers) > page * PAGE_SIZE:
        remaining = len(customers) - page * PAGE_SIZE
        if st.button(f"▼ もっと見る（残り {remaining} 名）", use_container_width=True):
            st.session_state.customer_page += 1
            st.rerun()

# ─────────────────────────────────────────
# 顧客詳細
# ─────────────────────────────────────────
def show_detail():
    user = st.session_state.user
    cid  = st.session_state.selected_customer
    c    = cached_get_customer(cid)
    if not c:
        st.error("顧客が見つかりません")
        return

    # 戻るボタン（ヘッダー直下・目立つ位置）
    if st.button("← 顧客一覧に戻る", use_container_width=True):
        st.session_state.page = "home"
        st.session_state.selected_customer = None
        # URLからdetailパラメータを除去
        st.query_params.clear()
        if st.session_state.login_token:
            st.query_params["t"] = st.session_state.login_token
        st.rerun()

    rank = c.get("rank","A")
    member_html = '<span style="color:#5B8F5F;font-size:0.9rem;">✅ 会員（メイソンズ）</span> ' if c["is_member"] and c["primary_store"]=="メイソンズ" else ""

    st.markdown(f"""
    <div class="customer-header">
      <div style="margin-bottom:8px">
        <span class="rank-badge rank-{rank}">{rank} {RANK_DESC.get(rank,'')}</span>
        {member_html}
      </div>
      <div class="customer-name">{c['name']}</div>
      <div style="font-size:0.82rem;color:#888;margin-top:4px">
        {c['primary_store'] or '未設定'} ·
        初来店: {c['first_visit_date'] or '-'} ·
        累計来店: <strong>{c['total_visits']}回</strong>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # クロスストア警告
    if c["cross_store_flag"] and user["role"] in ("owner","manager","executive"):
        st.markdown("""
        <div class="cross-store-banner">
        ⚠️ 他店舗に同じ名前の顧客がいます。同一人物ですか？
        </div>
        """, unsafe_allow_html=True)

        with st.expander("同一人物マージ"):
            stores = cached_get_stores()
            other_stores = [s for s in stores if s != c["primary_store"]]
            if other_stores:
                sel = st.selectbox("対象店舗", other_stores)
                candidates = db.get_customers(store=sel, search=c["name"].replace("さん",""))
                if candidates:
                    names = [f"{x['name']} ({x['total_visits']}回)" for x in candidates[:5]]
                    idx = st.selectbox("マージする顧客", names)
                    target_id = candidates[names.index(idx)]["id"] if idx in names else None
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("✅ 同一人物（マージ）", type="primary"):
                            if target_id:
                                db.merge_customers(target_id, cid, user["username"])
                                st.success("マージしました")
                                st.rerun()
                    with col2:
                        if st.button("❌ 別人"):
                            db.unmerge_customers(cid, user["username"])
                            st.info("別人として記録しました")

    # タブ
    tab1, tab2, tab3 = st.tabs(["📅 来店ログ", "📊 統計", "📝 メモ・設定"])

    # ────── Tab1: 来店ログ ──────
    with tab1:
        visits = cached_get_visits(cid)
        if visits:
            st.caption(f"全 {len(visits)} 件")
            for v in visits:
                stype = SERVICE_LABEL.get(v["service_type"],"通常")
                stype_color = {"🔄 トップ替え":"#5B8F5F","☕ カフェ":"#5B7FA6"}.get(stype,"#ccc")
                st.markdown(f"""
                <div class="visit-row">
                  <span class="visit-date">{v['date']}</span>
                  <span class="visit-store">{v['store']}</span>
                  <span style="color:{stype_color};font-size:0.78rem">{stype}</span>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("来店ログなし")

    # ────── Tab2: 統計 ──────
    with tab2:
        stats = cached_get_visit_stats(cid)

        if stats["by_dow"]:
            fig_dow = go.Figure(go.Bar(
                x=list(stats["by_dow"].keys()),
                y=list(stats["by_dow"].values()),
                marker_color="#5BA4C9",
                marker_line_color="#4A93B8",
                marker_line_width=1,
            ))
            fig_dow.update_layout(
                title="よく来る曜日",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                margin=dict(t=40,b=20,l=10,r=10),
                height=200,
                font=dict(family="Noto Sans JP"),
                yaxis=dict(showgrid=False),
            )
            st.plotly_chart(fig_dow, use_container_width=True,
                            config={"staticPlot": True, "displayModeBar": False})

        if stats["by_month"]:
            months = list(stats["by_month"].keys())
            vals   = list(stats["by_month"].values())
            fig_m = go.Figure(go.Bar(
                x=months, y=vals,
                marker_color="#E8F4FA",
                marker_line_color="#5BA4C9",
                marker_line_width=1.5,
            ))
            fig_m.update_layout(
                title="月別来店（直近6ヶ月）",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                margin=dict(t=40,b=20,l=10,r=10),
                height=200,
                font=dict(family="Noto Sans JP"),
                yaxis=dict(showgrid=False),
            )
            st.plotly_chart(fig_m, use_container_width=True,
                            config={"staticPlot": True, "displayModeBar": False})

        if stats["by_store"] and len(stats["by_store"]) > 1:
            st.caption("店舗別")
            for store, cnt in sorted(stats["by_store"].items(), key=lambda x: -x[1]):
                st.progress(cnt / c["total_visits"], text=f"{store}: {cnt}回")

    # ────── Tab3: メモ・設定 ──────
    with tab3:
        # メモ表示
        if c["notes"]:
            st.markdown("**📝 スタッフメモ**")
            for line in c["notes"].strip().split('\n'):
                if line:
                    st.caption(line)

        # メモ追加（スタッフ以上）
        new_note = st.text_area("メモを追加", placeholder="例: 甘め重め好き、アイスホース常連", height=80)
        if st.button("メモを保存", type="primary"):
            if new_note.strip():
                db.add_note(cid, new_note.strip(), user["username"])
                st.success("保存しました")
                st.rerun()

        # ランク変更（店長・オーナーのみ）
        if user["role"] in ("owner","manager","executive"):
            st.divider()
            st.markdown("**🏷 ランク設定**")
            current_rank = c.get("rank","A")

            # Masonsのみ VIP選択肢を追加
            rank_options = ["V","S","A"] if c["primary_store"] == "メイソンズ" else ["S","A"]
            rank_idx = rank_options.index(current_rank) if current_rank in rank_options else (1 if len(rank_options)>1 else 0)
            new_rank = st.radio(
                "ランク",
                rank_options,
                index=rank_idx,
                horizontal=True,
                help="S=超常連VIP / A=名前ありリピーター / V=VIP(Masons専用)",
            )
            if new_rank != current_rank:
                if st.button(f"{current_rank} → {new_rank} に変更", type="primary"):
                    db.set_rank(cid, new_rank, user["username"])
                    st.success("ランクを更新しました")
                    st.rerun()

            # メイソンズ：会員フラグ + トップ替えカウンター
            if c["primary_store"] == "メイソンズ":
                st.divider()
                is_member = st.checkbox("✅ メイソンズ会員", value=bool(c["is_member"]))
                if is_member != bool(c["is_member"]):
                    if st.button("会員ステータスを更新"):
                        with db.get_conn() as conn:
                            with conn.cursor() as cur:
                                cur.execute(
                                    "UPDATE customers SET is_member=%s WHERE id=%s",
                                    (1 if is_member else 0, cid)
                                )
                        st.rerun()

                # VIP トップ替えカウンター
                st.divider()
                from datetime import date as _date
                this_ym = _date.today().strftime('%Y-%m')
                total_tc, auto_tc, bonus_tc = db.get_monthly_top_changes(cid, this_ym)

                st.markdown(f"**🔄 トップ替え回数（{this_ym}）**")
                if total_tc >= 3:
                    st.markdown(f"""
                    <div class="top-change-alert">
                      🔴 今月 {total_tc}回 ／ 上限3回に到達！
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    remaining = 3 - total_tc
                    st.markdown(f"""
                    <div class="top-change-ok">
                      ✅ 今月 {total_tc}回（残り {remaining}回）
                    </div>
                    """, unsafe_allow_html=True)

                st.caption(f"自動カウント: {auto_tc}回　手動調整: {bonus_tc:+d}回")
                col_m, col_p, col_r = st.columns(3)
                with col_m:
                    if st.button("－1", key="tc_minus", use_container_width=True):
                        db.adjust_top_change_bonus(cid, -1)
                        st.rerun()
                with col_p:
                    if st.button("＋1", key="tc_plus", use_container_width=True):
                        db.adjust_top_change_bonus(cid, 1)
                        st.rerun()
                with col_r:
                    if st.button("リセット", key="tc_reset", use_container_width=True):
                        db.reset_top_change_bonus(cid)
                        st.rerun()

# ─────────────────────────────────────────
# ダッシュボード
# ─────────────────────────────────────────
def show_dashboard():
    user = st.session_state.user
    stores = ["全店舗"] + cached_get_stores()
    periods = ["全期間"] + cached_get_available_periods()

    if user["role"] == "manager" and user.get("store") and user["store"] != "本部":
        default_store = user["store"]
    else:
        default_store = "全店舗"

    c1, c2 = st.columns(2)
    with c1:
        sel_store = st.selectbox("店舗", stores,
            index=stores.index(default_store) if default_store in stores else 0,
            label_visibility="collapsed",
            key="dash_store")
    with c2:
        sel_period = st.selectbox("期間", periods,
            label_visibility="collapsed",
            key="dash_period")

    store_q  = None if sel_store == "全店舗" else sel_store
    period_q = None if sel_period == "全期間" else sel_period

    stats = cached_get_dashboard_stats(store=store_q, period=period_q)
    s = stats.get("summary", {})
    r = stats.get("rank_counts", {})

    # ── 来客数（フロー / スプレッドシート実数）──
    new_c   = s.get("new_total", 0)
    rep_b   = s.get("repeat_b",  0)
    total_c = new_c + rep_b
    st.markdown(
        "<div style='font-size:0.75rem;color:#9E8B7D;font-weight:600;"
        "letter-spacing:0.05em;margin-bottom:6px;'>来客数（スプレッドシート実数）</div>",
        unsafe_allow_html=True
    )
    col1, col2, col3 = st.columns(3)
    for col, (val, label) in zip(
        [col1, col2, col3],
        [(new_c, "新規"), (rep_b, "リピーター"), (total_c, "合計")]
    ):
        with col:
            st.markdown(f"""
            <div class="metric-card">
              <div class="metric-value">{val}</div>
              <div class="metric-label">{label}</div>
            </div>
            """, unsafe_allow_html=True)

    # ── 顧客資産（ストック / 登録済み累計）──
    st.write("")
    rank_a = r.get("A", 0)
    rank_s = r.get("S", 0) + r.get("V", 0)
    st.markdown(
        "<div style='font-size:0.75rem;color:#9E8B7D;font-weight:600;"
        "letter-spacing:0.05em;margin-bottom:6px;'>顧客資産（登録済み累計）</div>",
        unsafe_allow_html=True
    )
    ca, cs = st.columns(2)
    with ca:
        st.markdown(f"""
        <div class="metric-card">
          <div class="metric-value" style="color:#4FB8F0;">{rank_a}</div>
          <div class="metric-label">Aランク 登録人数</div>
        </div>""", unsafe_allow_html=True)
    with cs:
        st.markdown(f"""
        <div class="metric-card">
          <div class="metric-value" style="color:#FFB800;">{rank_s}</div>
          <div class="metric-label">Sランク 登録人数</div>
        </div>""", unsafe_allow_html=True)

    st.write("")

    # ── 来客構成ドーナツ（フローのみ: 新規 vs リピーター）──
    if total_c > 0:
        fig = go.Figure(go.Pie(
            labels=["新規", "リピーター"],
            values=[new_c, rep_b],
            hole=0.45,
            marker=dict(
                colors=["#FF8C69", "#52D68A"],
                line=dict(color="#FFFFFF", width=2)
            ),
            textinfo="label+percent",
            textfont_size=13,
        ))
        fig.update_layout(
            title=f"来客構成 — {sel_store} {sel_period}",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(t=50,b=10,l=10,r=10),
            height=280,
            font=dict(family="Noto Sans JP", color="#2D1F0F"),
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True,
                        config={"staticPlot": True, "displayModeBar": False})

    # 店舗別来店サマリー（全店舗選択時）
    if not store_q:
        st.markdown("#### 店舗別サマリー")
        # 店舗ごとのアクセントカラー
        store_colors = {
            "柏":       "#5BC8F5",  # 水色
            "東村山":   "#2D7A4F",  # 深めの緑
            "おおたか": "#9BC53D",  # 黄緑
            "メイソンズ":"#333333",  # 黒
            "西船橋":   "#FF6B35",  # オレンジ
        }
        # 全店舗を1クエリで取得（N+1解消）
        all_stores_data = cached_get_all_stores_stats(period=period_q)
        for store in cached_get_stores():
            ss     = all_stores_data.get(store, {})
            new_c  = ss.get("new_total", 0)
            rep_b  = ss.get("repeat_b", 0)
            total  = new_c + rep_b
            color  = store_colors.get(store, "#5BA4C9")
            st.markdown(f"""
            <div style="
              background:#FFFFFF;
              border:1px solid #E8E0D4;
              border-left:4px solid {color};
              border-radius:6px;
              padding:14px 18px;
              margin-bottom:10px;
              box-shadow:0 1px 3px rgba(0,0,0,0.04), 0 1px 2px rgba(107,66,38,0.10);
              width:100%;
              box-sizing:border-box;
            ">
              <div style="font-size:1.05rem;font-weight:600;color:#2D1F0F;margin-bottom:8px;">
                🏪 {store}
              </div>
              <div style="display:flex;gap:8px;flex-wrap:nowrap;align-items:flex-start;">
                <div style="text-align:center;flex:1;min-width:0;">
                  <div style="font-size:1.2rem;font-weight:300;color:#FF8C69;">{new_c}</div>
                  <div style="font-size:0.68rem;color:#9E8B7D;">新規</div>
                </div>
                <div style="text-align:center;flex:1;min-width:0;">
                  <div style="font-size:1.2rem;font-weight:300;color:#52D68A;">{rep_b}</div>
                  <div style="font-size:0.68rem;color:#9E8B7D;">リピーター</div>
                </div>
                <div style="text-align:center;flex:1;min-width:0;padding-left:8px;border-left:1px solid #E8E0D4;">
                  <div style="font-size:1.3rem;font-weight:300;color:#2D1F0F;">{total}</div>
                  <div style="font-size:0.68rem;color:#9E8B7D;">合計</div>
                </div>
              </div>
            </div>
            """, unsafe_allow_html=True)

    # ── 曜日別グラフ ──
    st.markdown("#### 曜日別 平均来客数")
    weekday_data = cached_get_weekday_stats(store=store_q, period=period_q)
    if weekday_data and any(d["avg_total"] > 0 for d in weekday_data):
        labels  = [d["label"]     for d in weekday_data]
        totals  = [d["avg_total"] for d in weekday_data]
        news    = [d["avg_new"]   for d in weekday_data]
        repeats = [d["avg_repeat"] for d in weekday_data]

        # 最大値の曜日を強調
        max_val = max(totals) if totals else 1
        bar_colors = [
            "#FF6B35" if v == max_val else "#5BA4C9"
            for v in totals
        ]

        fig_wd = go.Figure()
        fig_wd.add_trace(go.Bar(
            x=labels,
            y=totals,
            marker_color=bar_colors,
            text=[f"{v:.1f}" for v in totals],
            textposition="outside",
            textfont=dict(size=11, color="#2D1F0F"),
            hovertemplate="<b>%{x}曜日</b><br>平均合計: %{y:.1f}人<extra></extra>",
            name="合計",
        ))
        fig_wd.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(t=20, b=10, l=10, r=10),
            height=220,
            font=dict(family="Noto Sans JP", color="#2D1F0F", size=12),
            xaxis=dict(showgrid=False, tickfont=dict(size=14, color="#2D1F0F")),
            yaxis=dict(showgrid=True, gridcolor="#F0EBE3", zeroline=False),
            showlegend=False,
        )
        st.plotly_chart(fig_wd, use_container_width=True,
                        config={"staticPlot": True, "displayModeBar": False})

        # 強い曜日・弱い曜日のサマリー
        sorted_days = sorted(weekday_data, key=lambda d: d["avg_total"], reverse=True)
        if sorted_days[0]["avg_total"] > 0:
            strong = sorted_days[0]
            weak   = sorted_days[-1]
            st.markdown(
                f"<div style='font-size:0.8rem;color:#9E8B7D;text-align:center;'>"
                f"💪 <b>強い曜日</b>: {strong['label']}曜日（平均 {strong['avg_total']:.1f}人）　"
                f"📉 <b>弱い曜日</b>: {weak['label']}曜日（平均 {weak['avg_total']:.1f}人）"
                f"</div>",
                unsafe_allow_html=True,
            )

# ─────────────────────────────────────────
# ユーザー管理（オーナーのみ）
# ─────────────────────────────────────────
import random, string

def generate_password(length=8):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choices(chars, k=length))

def show_user_management():
    st.markdown("#### 👤 スタッフアカウント管理")

    # 現在のユーザー一覧
    users = db.get_all_users()
    role_label = {"owner":"オーナー","manager":"店長","staff":"スタッフ","executive":"経営陣"}
    current_user = st.session_state.user

    st.caption(f"登録済み: {len(users)}名")
    for u in users:
        col1, col2 = st.columns([5, 1])
        with col1:
            role_jp = role_label.get(u["role"], u["role"])
            store_str = f" · {u['store']}" if u.get("store") else ""
            st.markdown(f"**{u['username']}**　{role_jp}{store_str}")
        with col2:
            if u["username"] != current_user["username"]:
                if st.button("削除", key=f"del_user_{u['id']}"):
                    db.delete_user(u["id"])
                    st.success(f"{u['username']} を削除しました")
                    st.rerun()

    st.divider()
    st.markdown("#### ➕ 新しいスタッフを追加")

    STORES = ["", "柏", "東村山", "おおたかの森", "メイソンズ", "西船橋", "本部"]

    st.markdown("役割・店舗を選んで招待URLを発行 → スタッフに送るだけでOK")

    with st.form("invite_form"):
        inv_role = st.selectbox("権限", ["staff", "manager", "executive"],
            format_func=lambda x: {"staff":"スタッフ","manager":"店長","executive":"経営陣"}[x],
            key="inv_role")
        inv_store = st.selectbox("担当店舗", STORES,
            format_func=lambda x: x if x else "（全店舗）",
            key="inv_store")
        inv_submitted = st.form_submit_button("招待URLを発行", type="primary", use_container_width=True)

    if inv_submitted:
        token = db.create_invitation(inv_role, inv_store)
        APP_URL = "https://mosh-customer-app.streamlit.app"
        invite_url = f"{APP_URL}?invite={token}"
        role_jp = {"staff":"スタッフ","manager":"店長","executive":"経営陣"}[inv_role]
        store_str = inv_store if inv_store else "全店舗"
        st.success("✅ 招待URLを発行しました（有効期限: 7日間）")
        st.code(invite_url, language=None)
        st.caption(f"権限: {role_jp}　店舗: {store_str}　← このURLをLINE/Discordで送ってください")

# ─────────────────────────────────────────
# 今日の営業（告知文・終業報告生成）
# ─────────────────────────────────────────

# 店舗別営業情報
STORE_INFO = {
    "柏": {
        "weekday_open": "14:00", "weekend_open": "12:00",
        "close": "24:00", "shisha_lo": "22:45", "drink_lo": "23:30",
        "phone": "08089910031",
    },
    "東村山": {
        "weekday_open": "14:00", "weekend_open": "12:00",
        "close": "24:00", "shisha_lo": "22:45", "drink_lo": "23:30",
        "phone": "07089449770",
    },
    "おおたか": {
        "weekday_open": "14:00", "weekend_open": "12:00",
        "close": "24:00", "shisha_lo": "22:45", "drink_lo": "23:30",
        "phone": "0471999850",
    },
    "西船橋": {
        "weekday_open": "14:00", "weekend_open": "14:00",  # 全日同じ
        "close": "24:00", "shisha_lo": "22:45", "drink_lo": "23:30",
        "phone": "08078120226",
    },
    "メイソンズ": {
        "weekday_open": "19:00",  # 月〜土
        "close": "29:00", "last_entry": "26:00",  # 月〜土
        "sunday_close": "24:00", "sunday_last_entry": "22:45",  # 日曜のみ
        "phone": "08021099722",
    },
}

def get_store_footer(store_name: str) -> str:
    """店舗名と今日の曜日・祝日から営業情報フッターを生成"""
    from datetime import date as _date, timedelta
    info = STORE_INFO.get(store_name)
    if not info:
        return ""
    today = _date.today()
    tomorrow = today + timedelta(days=1)
    is_sunday = today.weekday() == 6
    is_saturday = today.weekday() == 5
    is_monday = today.weekday() == 0
    try:
        import jpholiday
        is_holiday = bool(jpholiday.is_holiday(today))
        is_tomorrow_holiday = bool(jpholiday.is_holiday(tomorrow))
    except ImportError:
        is_holiday = False
        is_tomorrow_holiday = False
    phone = info["phone"]

    if store_name == "メイソンズ":
        # 日曜 かつ 翌日(月曜)が祝日 → 29時まで延長
        if is_sunday and is_tomorrow_holiday:
            lines = [
                "本日もご来店お待ちしております！",
                "19:00~29:00",
                "⚠️最終入店26:00",
                phone,
                "※15分以上返事がない場合はお手数ですがお電話にてお問い合わせください☎",
                "※ご予約の際は📢にあります予約フォーマットをご活用くださいませ！",
            ]
        # 通常の日曜 → MOSHと同じルール（12時オープン・24時クローズ）
        elif is_sunday:
            lines = [
                "本日もご来店お待ちしております！",
                "12:00-24:00",
                "SHISHA LO：22:45",
                "DRINK&SWEETS LO：23:30",
                phone,
                "※15分以上返事がない場合はお手数ですがお電話にてお問い合わせください☎",
                "※ご予約の際は📢にあります予約フォーマットをご活用くださいませ！",
            ]
        # 月曜が祝日 → 12時閉店（日曜深夜からの継続営業）
        elif is_monday and is_holiday:
            lines = [
                "本日もご来店お待ちしております！",
                "〜12:00",
                phone,
                "※15分以上返事がない場合はお手数ですがお電話にてお問い合わせください☎",
                "※ご予約の際は📢にあります予約フォーマットをご活用くださいませ！",
            ]
        # 通常営業（月〜土・祝日以外）
        else:
            lines = [
                "本日もご来店お待ちしております！",
                "19:00~29:00",
                "⚠️最終入店26:00",
                phone,
                "※15分以上返事がない場合はお手数ですがお電話にてお問い合わせください☎",
                "※ご予約の際は📢にあります予約フォーマットをご活用くださいませ！",
            ]
    else:
        open_time = info["weekend_open"] if (is_saturday or is_sunday or is_holiday) else info["weekday_open"]
        close_time = info["close"]
        lines = [
            "本日もご来店お待ちしております！",
            f"{open_time}-{close_time}",
            f"SHISHA LO：{info['shisha_lo']}",
            f"DRINK&SWEETS LO：{info['drink_lo']}",
            phone,
            "※15分以上返事がない場合はお手数ですがお電話にてお問い合わせください☎",
            "※ご予約の際は📢にあります予約フォーマットをご活用くださいませ！",
        ]
    return "\n".join(lines)

# 告知文スタイル定義（1〜5）
# ※実際のMOSHスタッフの過去告知文を分析して分類したスタイル
ANNOUNCE_STYLES = {
    "スタイル1：情景描写・概念型": {
        "label": "スタイル1：情景描写・概念型",
        "description": "フレーバーを情景・イメージ・概念で表現する",
        "prompt": """実際のMOSHスタッフの投稿例（このトーンで書く）：
- 今日のおすすめは 透き通った水の中にひたりと咲き誇る華をイメージした概念系シーシャ🪷 フロラールな香りにメンソール感を加えたmixです！
- open💫 本日のおすすめMIXは【心踊るコパイン】ひと口吸うと南国気分🌴ひんやり爽やかなパイナップルとまろやかなコナッツが絡み合う夢みたいな味わいです。
- open💫 本日のおすすめは「🦋ユリシス🦋」宝石のように鮮やかな蒼い羽を持った蝶をイメージしたミックスです。清涼感のある爽やかなブルーベリーの香りと、ほんのり甘いフルーツが絶妙にマッチ✨想像しただけでうっとりしませんか？
- 今日のおすすめは 数種類のパンラズナ使用！甘くも爽やかなエキゾチックな香りにうっとり癒されませんか？🌙🦋
- 本日おすすめは、 炎と氷と雷、それぞれのイメージを1つにまとめたミックスです 喧嘩せず仲良くなるかは扱うトレーナー(吸い手)次第！
- 今日のおすすめは 華々しいうっとりする香りのスパイス甘いミックスです💭🍨✨

スタイルの特徴：
- フレーバーを「〜をイメージ」「〜みたいな」「概念系」で情景・イメージとして描く
- 「うっとり」「夢みたいな」「絶妙にマッチ」など体験や感情を添える
- 絵文字は2〜3個、テーマに合ったものを選ぶ
- フレーバー名を【】で括ってもOK""",
    },
    "スタイル2：シチュエーション・季節型": {
        "label": "スタイル2：シチュエーション・季節型",
        "description": "今日の天気・気分・場面と絡めて紹介する",
        "prompt": """実際のMOSHスタッフの投稿例（このトーンで書く）：
- open☔️ 今日のおすすめは連休バタバタ人へ【森林緑】深い緑の中にいるような清涼感。疲れた心をすーっとリセットしてくれます🌿雨の日にもぴったり。
- open☁️ 今日のおすすめは気圧に負けない【ミントティー】気圧変化で頭が重い日でもすーっとクリアになる感じ。ミントの清涼感でリフレッシュ✨
- 今日のおすすめは いちごをメインとした甘酸っぱいシーシャ！天気の良い祝日ってなんだか苺吸いたくなるんですよね…🍓 ストロベリーシェイクと一緒にどうぞ！
- 今日のおすすめは 密かに人気なミックスの一つ。 レモングラスのフレッシュな香りが気分も鼻通りも(?)よくしてくれます🫶🏻✨ 天気の良い週末にぴったりなミックス！
- 今日のおすすめは 雨の日って無性に甘いもの食べたくなるんですよね…ぜひスイーツと一緒に吸って甘〜い１日にしちゃいましょ！
- 雨ということはアレが吸える！ 今日のおすすめは ラージ限定で濃い煙吸ってみてね！

スタイルの特徴：
- 天気・季節・気分から入る（「open☁️」「雨の日」「天気の良い」など）
- 「〜な日にぴったり」「〜な人へ」でシチュエーションとフレーバーを結びつける
- 来店したくなる理由を自然に伝える
- コンパクト〜中程度の文量（100〜180文字）""",
    },
    "スタイル3：カジュアル素直型": {
        "label": "スタイル3：カジュアル素直型",
        "description": "感じたままを素直にフレンドリーに伝える",
        "prompt": """実際のMOSHスタッフの投稿例（このトーンで書く）：
- オープンです！きょうのおすすめはアールグレイと甘みの少ないミルクのシンプル甘くないMIX！！上品な紅茶の香りとミルクのやさしさ、シーシャ初心者にもおすすめです☕
- バタバタしてましたがオープンです！！きょうのおすすめはガチでおすすめできるクラフトジンジャーエールMIX！生姜のピリッと感とジンジャーエールの爽快感、これほんとに最高です💪
- モッシュ今週もオープンしました！今日おすすめはグレナデン、ピーチ、ジャスミン、パンラズナMIX！！甘くてフルーティで香りも豊か、全部好きな人集まれ😆
- 今日のおすすめは どうしてもピーチが吸いたくなりました。 たまに吸いたくなるピーチ…重くも甘くもできるよ🍑
- 今日のおすすめは 久々にお菓子甘い系ミックス💭 もったり甘〜いキュートな香りです！
- 今日のおすすめは ボムシェル使ったみどりみどりしたシーシャ！ 一度吸うとクセになるヒノキの香り、ぜひお試しください🌳🌳

スタイルの特徴：
- 「オープンです！」「オープンしました！」または素直な一言から入る
- 「ガチでおすすめ」「ほんとに最高」「どうしても吸いたくなりました」など素直な感情
- ！！で気持ちを表現（「やばい」「えぐい」「アイドルみたいな表現」は使わない）
- フレンドリーで親しみやすい、スタッフの人柄が出る文章""",
    },
    "スタイル4：フレーバー構成詳細型": {
        "label": "スタイル4：フレーバー構成詳細型",
        "description": "フレーバーの組み合わせ・特徴を丁寧に説明する",
        "prompt": """実際のMOSHスタッフの投稿例（このトーンで書く）：
- おすすめは オレンジをベースにシナモンやカルダモンも入れたミックスです✨ ぜひ吸いに来てみてくださいね🙌
- 今日のおすすめは ブラックグレープをベースに甘酸っぱいチェリーと濃厚な香りのカシスをmix 🍇🍒🫐✨
- open☀️ 今日のおすすめは【ジャスミンアップルティー】ジャスミンの上品な香りにアップルの甘みが加わって、気品ある午後のティータイムみたいな一本🍵
- 本日おすすめは、 ミルクティーをメインに、ローズを少しだけいれた、優しい甘めのMIXです。
- 今日のおすすめは ローズ×ブルーベリーをメインにしたミステリアスな華やかシーシャ🫐💭
- 本日おすすめは、 チェリーを使って、バニラや甘めのお菓子系と合わせた海外のお菓子のようなMIXです。

スタイルの特徴：
- 「〜をベースに」「〜をメインに」「〜を合わせた」でフレーバー構成を具体的に説明する
- どんな組み合わせか、どんな味かを丁寧に伝える
- シンプルで読みやすい文章。過剰な感嘆符を使わない
- フレーバー名を「×」や「+」でつないで組み合わせを示してもOK""",
    },
    "スタイル5：エピソード・ストーリー型": {
        "label": "スタイル5：エピソード・ストーリー型",
        "description": "季節・記念日・出来事をストーリーと絡めて紹介する",
        "prompt": """実際のMOSHスタッフの投稿例（このトーンで書く）：
- open🌤️ 2月最終日！あっという間ですね…2月から本オープンして沢山のお客様に来ていただきました🌸ありがとうございます！本日のおすすめは【苺とバラとラズベリー】春を先取りしたような甘くフローラルな一本💐
- open☀️ ハッピーバレンタイン💌 今日のおすすめはmoshの看板スイーツをイメージしたフレーバー🍫チョコの甘さとほんのりビターな大人感。大切な人と一緒に吸いたい一本です。
- 今日のおすすめは さくらんぼをブランデーで漬け込みチョコレートでコーティングした大人なスイーツの香り🍸 下瓶ウイスキーがおすすめです！
- GW最終日、明日からの仕事に備えて家で休むのも良いですが、シーシャを吸いながらのんびりするのも良いですよ 本日のおすすめmixは
- おすすめは 爽やかなジャスミンを始め、様々なフラワー系フレーバーをミックスし、パンラズナのオリエンタルエスニックな香りを合わせた一本💭 夜桜をイメージし、可愛く酔えるシーシャです🍸💓

スタイルの特徴：
- 日付・季節・記念日・出来事を冒頭に入れる
- フレーバーをそのエピソードと自然につなげる
- 「〜な今日だからこそ」「〜をイメージした」で文脈を作る
- 絵文字は季節・テーマに合ったものを選ぶ""",
    },
}

# スタイル別バリエーションヒント（スタイルの特徴を壊さないように各スタイルに合わせたヒントのみ）
_STYLE_VARIATION_HINTS = {
    "スタイル1：情景描写・概念型": [
        "フレーバーに詩的な名前をつけて【】で括る",
        "自然・宇宙・夢の中のようなイメージで情景を描く",
        "「うっとり」「夢みたいな」「想像しただけで」などの表現を使う",
    ],
    "スタイル2：シチュエーション・季節型": [
        "今日の天気・気圧・気温から入ってフレーバーとつなぐ",
        "「〜な日にぴったり」「〜な人へ」でシチュエーションと結ぶ",
        "季節のキーワード（春/雨/暑い/寒い）を自然に入れる",
    ],
    "スタイル3：カジュアル素直型": [
        "「オープンです！」から始めてスタッフの本音を素直に伝える",
        "「ガチでおすすめ」「ほんとに最高」など飾らない感情表現を使う",
        "短い一文のあとに「！！」で気持ちを強調する",
    ],
    "スタイル4：フレーバー構成詳細型": [
        "「〜をベースに〜を加えた」で構成を丁寧に説明する",
        "フレーバー名を「×」や「+」でつないで組み合わせを示す",
        "どんな味・香りか具体的に、シンプルに描写する",
    ],
    "スタイル5：エピソード・ストーリー型": [
        "今日の日付・季節・記念日・出来事を冒頭に入れる",
        "エピソードからフレーバーへ「だからこそ」「だから今日は」でつなぐ",
        "「先取り」「最終日」「はじめて」など特別感のある言葉を使う",
    ],
}

def generate_open_text(flavor: str, style_key: str) -> str:
    if not HAS_ANTHROPIC:
        return "⚠️ AI機能が無効です（ANTHROPIC_API_KEY未設定）"
    from datetime import date as _date
    import random as _random
    today = _date.today()
    weekdays_ja = ["月", "火", "水", "木", "金", "土", "日"]
    weekday_ja = weekdays_ja[today.weekday()]
    # 月末判定
    import calendar as _cal
    last_day = _cal.monthrange(today.year, today.month)[1]
    is_month_end = today.day == last_day
    is_month_start = today.day == 1
    date_context = f"{today.month}月{today.day}日（{weekday_ja}）"
    if is_month_end:
        date_context += f"・{today.month}月最終日"
    elif is_month_start:
        date_context += f"・{today.month}月スタート"
    # 季節
    month = today.month
    if month in (3, 4, 5):
        season = "春"
    elif month in (6, 7, 8):
        season = "夏"
    elif month in (9, 10, 11):
        season = "秋"
    else:
        season = "冬"

    style = ANNOUNCE_STYLES.get(style_key, list(ANNOUNCE_STYLES.values())[0])
    hints_for_style = _STYLE_VARIATION_HINTS.get(style_key, [])
    hint = _random.choice(hints_for_style) if hints_for_style else ""
    hint_line = f"\n今回のバリエーション指示：{hint}" if hint else ""
    try:
        msg = _anthropic_client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=350,
            temperature=1.0,
            system=f"""あなたはシーシャバー「MOSH」のスタッフです。
毎日LINEオープンチャットにオープン告知を投稿します。

【今日の日付】{date_context}　季節：{season}
※日付・曜日・季節の情報は実際のこの日付に合わせて使うこと。架空の日付は書かない。

【今回のスタイル：{style['label']}】
{style['prompt']}

⚠️ 必ず上記スタイルの特徴を守ること。他スタイルの書き方は混ぜない。

【共通ルール】
- 150〜200文字程度
- フレーバーの香り・味・イメージを具体的に表現する{hint_line}""",
            messages=[{"role": "user", "content": f"今日のおすすめフレーバー：{flavor}"}]
        )
        return msg.content[0].text.strip()
    except Exception as e:
        return f"⚠️ 生成エラー: {e}"

def generate_discord_report(store: str, date_str: str, flavor: str,
                             new_count: int, repeat_count: int,
                             visitor_names: str, done_today: str,
                             todo_tomorrow: str, notice: str,
                             register_diff: str) -> str:
    total = new_count + repeat_count
    lines = [
        f"**終業報告** {date_str}",
        f"",
        f"【今日やったこと】",
    ]
    for item in done_today.strip().splitlines():
        if item.strip():
            lines.append(f"・{item.strip()}")
    lines += [f"", f"【明日やってほしいこと】"]
    for item in todo_tomorrow.strip().splitlines():
        if item.strip():
            lines.append(f"・{item.strip()}")
    lines += [
        f"",
        f"【来店人数】",
        f"新規　　　{new_count}名",
        f"リピ　　　{repeat_count}名",
        f"￣￣￣￣￣￣￣￣￣￣￣￣￣",
        f"計　　　　{total}名",
        f"",
        f"【来店者記録】",
    ]
    names_line = "、".join(n.strip() for n in visitor_names.strip().splitlines() if n.strip())
    if names_line:
        lines.append(names_line)
    lines += [
        f"",
        f"【連絡事項】",
        f"①営業の様子",
        f"{notice.strip()}",
        f"",
        f"【レジ締め過不足】",
        f"¥{register_diff}",
    ]
    return "\n".join(lines)

def _get_title_font(size: int):
    """英語大タイトル用フォント（Cormorant Garamond Bold）"""
    from PIL import ImageFont
    base = os.path.dirname(__file__)
    candidates = [
        os.path.join(base, "assets", "fonts", "CormorantGaramond-Bold.ttf"),
        os.path.join(base, "assets", "fonts", "NotoSerifJP.ttf"),
        "/System/Library/Fonts/Optima.ttc",
        "/System/Library/Fonts/Palatino.ttc",
    ]
    for path in candidates:
        try:
            if os.path.exists(path):
                return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _get_jp_font(size: int):
    """日本語テキスト用フォント（Noto Serif JP）"""
    from PIL import ImageFont
    base = os.path.dirname(__file__)
    candidates = [
        os.path.join(base, "assets", "fonts", "NotoSerifJP.ttf"),
        os.path.join(base, "assets", "fonts", "CormorantGaramond-Regular.ttf"),
        "/System/Library/Fonts/Optima.ttc",
        "/usr/share/fonts/truetype/noto/NotoSerifCJKjp-Regular.otf",
        "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    ]
    for path in candidates:
        try:
            if os.path.exists(path):
                return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _add_text_overlay(img_bytes: bytes, title: str, catch_phrase: str = "",
                       flavor_jp: str = "", circle_lines: list = None) -> bytes:
    """参照画像スタイルのエレガントなテキストオーバーレイを追加"""
    if not HAS_PIL:
        return img_bytes
    import io
    from PIL import Image, ImageDraw, ImageFilter

    img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
    W, H = img.size
    s = H / 1024  # スケール係数

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    def _draw_glowing_text(ov, pos, text, font, anchor="lm",
                           glow_radius=10, glow_alpha=130,
                           shadow_offset=3, shadow_alpha=160):
        """グロー＋ドロップシャドウ付きテキストを描画（参照画像の浮き出し効果）"""
        x, y = pos
        # 1. グロー層（ぼかした白テキスト）
        glow = Image.new("RGBA", ov.size, (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        gd.text((x, y), text, fill=(255, 255, 255, glow_alpha), font=font, anchor=anchor)
        glow = glow.filter(ImageFilter.GaussianBlur(radius=int(glow_radius * s)))
        ov_new = Image.alpha_composite(ov, glow)
        d = ImageDraw.Draw(ov_new)
        # 2. ドロップシャドウ（わずかにオフセットした暗い影）
        so = int(shadow_offset * s)
        d.text((x + so, y + so), text, fill=(0, 0, 0, shadow_alpha), font=font, anchor=anchor)
        # 3. メインテキスト（鮮明な白）
        d.text((x, y), text, fill=(255, 255, 255, 252), font=font, anchor=anchor)
        return ov_new

    has_title = bool(title.strip())

    # ── タイトルブロック（左上寄り）──
    if has_title:
        # キャッチフレーズ（タイトル上の小さな日本語）- 軽いグローのみ
        if catch_phrase:
            font_catch = _get_jp_font(int(26 * s))
            overlay = _draw_glowing_text(
                overlay, (int(85 * s), int(168 * s)), catch_phrase, font_catch,
                anchor="lm", glow_radius=6, glow_alpha=90, shadow_offset=1, shadow_alpha=100
            )
            draw = ImageDraw.Draw(overlay)

        # 大タイトル - 日本語含む場合はNotoSerifJP、英語はCormorant Garamond
        import unicodedata
        def _has_wide_chars(t):
            return any(unicodedata.east_asian_width(c) in ('W', 'F', 'A') for c in t)
        is_jp = _has_wide_chars(title)
        _font_getter = _get_jp_font if is_jp else _get_title_font
        # 参照画像に合わせ、タイトルは画幅60%以内に収める（余白を大事に）
        font_size_t = int((80 if is_jp else 128) * s)
        font_title = _font_getter(font_size_t)
        max_title_w = int(W * 0.62)
        min_size = int(36 * s)
        for _ in range(30):
            try:
                bbox = draw.textbbox((0, 0), title, font=font_title)
                text_w = bbox[2] - bbox[0]
            except Exception:
                text_w = max_title_w + 1
            if text_w <= max_title_w or font_size_t <= min_size:
                break
            font_size_t = max(int(font_size_t * 0.90), min_size)
            font_title = _font_getter(font_size_t)
        # グロー強め・シャドウ明確 → 浮き出し感
        overlay = _draw_glowing_text(
            overlay, (int(75 * s), int(295 * s)), title, font_title,
            anchor="lm", glow_radius=12, glow_alpha=150, shadow_offset=3, shadow_alpha=180
        )
        draw = ImageDraw.Draw(overlay)

        # 日本語サブタイトル（タイトル直下）- 文字間スペースを追加して優雅に
        if flavor_jp:
            font_jp = _get_jp_font(int(28 * s))
            spaced = "  ".join(flavor_jp)  # 文字間にスペース
            overlay = _draw_glowing_text(
                overlay, (int(90 * s), int(378 * s)), spaced, font_jp,
                anchor="lm", glow_radius=5, glow_alpha=80, shadow_offset=1, shadow_alpha=100
            )
            draw = ImageDraw.Draw(overlay)

    # ── 円形バッジ（左中央）──
    if circle_lines and has_title:
        cx, cy, r = int(168 * s), int(572 * s), int(112 * s)

        # 半透明の円背景
        badge_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        badge_draw = ImageDraw.Draw(badge_layer)
        badge_draw.ellipse(
            [(cx - r, cy - r), (cx + r, cy + r)],
            fill=(0, 0, 0, 90)
        )
        overlay = Image.alpha_composite(overlay, badge_layer)
        draw = ImageDraw.Draw(overlay)

        # 円の縁線
        draw.ellipse(
            [(cx - r, cy - r), (cx + r, cy + r)],
            outline=(255, 255, 255, 150), width=max(1, int(1.5 * s))
        )

        # テキスト - 各行が円内に収まるようにフォントサイズ自動縮小
        max_line_w = int(r * 1.55)  # 円直径の約78%
        badge_size = int(22 * s)
        font_badge = _get_jp_font(badge_size)
        for _ in range(15):
            too_wide = False
            for line in circle_lines:
                try:
                    bbox = draw.textbbox((0, 0), line, font=font_badge)
                    if (bbox[2] - bbox[0]) > max_line_w:
                        too_wide = True
                        break
                except Exception:
                    break
            if not too_wide or badge_size <= int(14 * s):
                break
            badge_size = max(int(badge_size * 0.88), int(14 * s))
            font_badge = _get_jp_font(badge_size)
        lh = int(badge_size * 1.45)
        total_h = len(circle_lines) * lh
        y0 = cy - total_h // 2 + lh // 2
        for i, line in enumerate(circle_lines):
            draw.text((cx, y0 + i * lh), line,
                      fill=(255, 255, 255, 230), font=font_badge, anchor="mm")

    # ── 下部：ブランド名 + デコレーションライン + タグライン ──
    # ブランド名（グロー付き）
    font_brand = _get_title_font(int(36 * s))
    brand_y = int(888 * s)
    overlay = _draw_glowing_text(
        overlay, (W // 2, brand_y), "shisha & sweets  MOSH", font_brand,
        anchor="mm", glow_radius=8, glow_alpha=110, shadow_offset=2, shadow_alpha=140
    )
    draw = ImageDraw.Draw(overlay)

    # デコレーションライン ──── ◆ ────
    line_y = int(924 * s)
    llen = int(115 * s)
    lw = max(1, int(s))
    draw.line([(W // 2 - llen - 14, line_y), (W // 2 - 10, line_y)],
              fill=(255, 255, 255, 170), width=lw)
    d = int(5 * s)
    diamond = [
        (W // 2, line_y - d), (W // 2 + d, line_y),
        (W // 2, line_y + d), (W // 2 - d, line_y)
    ]
    draw.polygon(diamond, fill=(255, 255, 255, 200))
    draw.line([(W // 2 + 10, line_y), (W // 2 + llen + 14, line_y)],
              fill=(255, 255, 255, 170), width=lw)

    # タグライン
    font_tag = _get_jp_font(int(22 * s))
    draw.text((W // 2, int(960 * s)), "特別な香りを、あなたの時間に",
              fill=(255, 255, 255, 195), font=font_tag, anchor="mm")

    composite = Image.alpha_composite(img, overlay).convert("RGB")
    out = io.BytesIO()
    composite.save(out, format="JPEG", quality=95)
    return out.getvalue()


def _generate_with_nano_banana(prompt: str) -> bytes | None:
    """Nano Banana 2 (gemini-3.1-flash-image-preview) で画像を生成し、バイトを返す"""
    import io as _io

    if _gemini_use_new_sdk:
        # 新SDK: google.genai.Client
        from google.genai import types
        response = _gemini_client.models.generate_content(
            model="gemini-3.1-flash-image-preview",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
                image_config=types.ImageConfig(
                    aspect_ratio="1:1",
                ),
            ),
        )
        for part in response.candidates[0].content.parts:
            if part.inline_data is not None:
                img = Image.open(_io.BytesIO(part.inline_data.data))
                buf = _io.BytesIO()
                img.convert("RGB").save(buf, format="JPEG", quality=95)
                return buf.getvalue()
    else:
        # 旧SDK: google.generativeai
        model = _gemini_client.GenerativeModel(
            "gemini-3.1-flash-image-preview",
            generation_config={"response_modalities": ["IMAGE"]},
        )
        response = model.generate_content(prompt)
        if response.candidates and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if hasattr(part, "inline_data") and part.inline_data:
                    img = Image.open(_io.BytesIO(part.inline_data.data))
                    buf = _io.BytesIO()
                    img.convert("RGB").save(buf, format="JPEG", quality=95)
                    return buf.getvalue()
    return None


def generate_flavor_image(flavor: str, title: str = ""):
    if not HAS_GEMINI:
        return None
    try:
        # Claude HaikuでFLAVOR_INGREDIENTS / BACKGROUND_SCENE / テキスト要素を決定
        flavor_ingredients = f"fresh {flavor} ingredients, sliced fruits, ice cubes"
        background_scene = f"moody dark studio with {flavor}-themed natural elements"
        catch_phrase = ""
        flavor_jp = ""
        circle_lines: list = []

        if HAS_ANTHROPIC:
            v = _anthropic_client.messages.create(
                model="claude-haiku-4-5",
                max_tokens=220,
                system="""You are an art director for a premium Japanese shisha bar.
Given a shisha flavor name, respond in this EXACT format with NO extra words or prefixes:
FLAVOR_INGREDIENTS: sliced peaches, fresh mint, ice cubes, honey jar, dried black tea leaves
BACKGROUND_SCENE: deep amber candlelit interior with vintage copper tones and soft bokeh
CATCH_PHRASE: やさしい甘さ、心ほどけるひととき
FLAVOR_JP: ピーチティー
CIRCLE_LINE1: フルーティーな
CIRCLE_LINE2: ピーチの香りと
CIRCLE_LINE3: 紅茶の深み

Rules:
- FLAVOR_INGREDIENTS and BACKGROUND_SCENE: English only
- CATCH_PHRASE: Japanese only, ≤16 chars, elegant poetic copy
- FLAVOR_JP: Japanese katakana reading of the flavor name, ≤12 chars
- CIRCLE_LINE1/2/3: Japanese only, ≤10 chars each, describing the flavor
- Do NOT include the word "Japanese:" anywhere in your response""",
                messages=[{"role": "user", "content": f"Flavor: {flavor}"}]
            )
            result = v.content[0].text.strip()
            c_lines = []
            for line in result.splitlines():
                def _clean(val: str) -> str:
                    import re
                    return re.sub(r'^(Japanese|English)\s*:\s*', '', val).strip().strip('"')
                if line.startswith("FLAVOR_INGREDIENTS:"):
                    flavor_ingredients = _clean(line.replace("FLAVOR_INGREDIENTS:", "").strip())
                elif line.startswith("BACKGROUND_SCENE:"):
                    background_scene = _clean(line.replace("BACKGROUND_SCENE:", "").strip())
                elif line.startswith("CATCH_PHRASE:"):
                    catch_phrase = _clean(line.replace("CATCH_PHRASE:", "").strip())
                elif line.startswith("FLAVOR_JP:"):
                    flavor_jp = _clean(line.replace("FLAVOR_JP:", "").strip())
                elif line.startswith("CIRCLE_LINE"):
                    c_lines.append(_clean(line.split(":", 1)[1].strip()))
            circle_lines = [l for l in c_lines if l] if c_lines else []

        prompt = (
            f"Hyper-realistic luxury product photography for a premium Japanese shisha bar. "
            f"Scene: a beautifully crafted ornate hookah in antique brass and gold "
            f"positioned on the RIGHT side, its glass base catching the light, "
            f"with thick white smoke curling upward dramatically. "
            f"On the CENTER and LEFT: an exquisite still-life on a dark hammered-brass tray — "
            f"{flavor_ingredients} — arranged with refined precision: "
            f"glistening ice cubes, fresh ingredients with visible moisture droplets, "
            f"a crystal cocktail glass with condensation. "
            f"Background: {background_scene}, with deep natural bokeh. "
            f"Lighting: single warm key light from upper-left creating dramatic "
            f"chiaroscuro shadows, golden rim lighting on the hookah, "
            f"subtle lens flare for cinematic depth. "
            f"Color grading: rich amber, deep burgundy, warm copper tones, "
            f"high contrast, shadows with cool blue undertones. "
            f"The upper-left area fades into atmospheric dark bokeh — ideal for text. "
            f"Absolutely NO text, NO watermarks, NO logos anywhere. "
            f"Style: high-end Japanese lifestyle magazine editorial, "
            f"similar to Monocle or Kinfolk magazine cover quality. "
            f"Ultra-sharp focus on hero items, silky smooth bokeh background. "
            f"Shot on Phase One IQ4 150MP, 110mm f/2.8 Schneider lens, "
            f"tethered studio with Profoto B10 key light and silver reflector fill. "
            f"8K resolution, commercial retouching, impeccable detail."
        )
        img_bytes = _generate_with_nano_banana(prompt)
        if not img_bytes:
            st.error("画像生成に失敗しました")
            return None
        return _add_text_overlay(img_bytes, title, catch_phrase, flavor_jp, circle_lines)
    except Exception as e:
        st.error(f"画像生成エラー: {e}")
        return None

def generate_free_image(user_prompt: str, title: str = ""):
    """自由プロンプトで画像を生成し、テキストオーバーレイを適用"""
    if not HAS_GEMINI:
        return None
    try:
        base_prompt = (
            f"{user_prompt}. "
            f"Absolutely NO text, NO watermarks, NO logos anywhere. "
            f"Photorealistic, ultra-high detail, luxury editorial photography, "
            f"8K resolution, shallow depth of field, commercial retouching."
        )
        img_bytes = _generate_with_nano_banana(base_prompt)
        if not img_bytes:
            st.error("画像生成に失敗しました")
            return None
        if title.strip():
            return _add_text_overlay(img_bytes, title)
        return img_bytes
    except Exception as e:
        st.error(f"画像生成エラー: {e}")
        return None


def show_operations():
    user = st.session_state.user
    store = user.get("store", "") or ""
    store_label = store if store else "MOSH"
    st.markdown("### 📢 今日の営業")
    op_tab1, op_tab2, op_tab3 = st.tabs(["🟢 オープン告知", "🌙 終業報告", "🖼 フリー画像生成"])

    with op_tab1:
        st.markdown("**今日のおすすめフレーバーを入力してください**")

        # 店舗選択（自分の店舗が設定されていない場合は手動選択）
        known_stores = list(STORE_INFO.keys())
        if store and store in known_stores:
            ops_store = store
        else:
            ops_store = st.selectbox(
                "🏪 店舗を選んでください",
                options=known_stores,
                key="ops_store"
            )

        flavor_input = st.text_input("フレーバー",
            placeholder="例：レモンミント、ピーチ、グレープ", key="ops_flavor")
        # フレーバー入力欄のオートコンプリートを無効化（ログイン画面に混入防止）
        st.components.v1.html(
            '<script>window.parent.document.querySelectorAll'
            '("input[placeholder=\'例：レモンミント、ピーチ、グレープ\']")'
            '.forEach(function(el){el.setAttribute("autocomplete","off");});</script>',
            height=0
        )
        title_input = st.text_input("画像タイトル（任意）",
            placeholder="例：本日のおすすめ、OPEN、NEW FLAVOR", key="ops_title")

        # スタイル選択（1〜5）
        style_options = list(ANNOUNCE_STYLES.keys())
        selected_style = st.selectbox(
            "📝 文体スタイルを選んでください",
            options=style_options,
            format_func=lambda k: f"{ANNOUNCE_STYLES[k]['label']} — {ANNOUNCE_STYLES[k]['description']}",
            key="ops_style"
        )

        col1, col2 = st.columns(2)
        with col1:
            gen_text = st.button("📝 告知文を生成", use_container_width=True, type="primary")
        with col2:
            gen_img = st.button("🎨 画像を生成", use_container_width=True, disabled=not HAS_GEMINI)
        if gen_text and flavor_input:
            with st.spinner("告知文を生成中..."):
                text = generate_open_text(flavor_input, selected_style)
            footer = get_store_footer(ops_store)
            full_text = f"{text}\n\n{footer}" if footer else text
            st.session_state["ops_generated_text"] = full_text
            # key="ops_text_area" が既にsession_stateにあるとvalueが無視されるため、両方更新する
            st.session_state["ops_text_area"] = full_text
        if "ops_generated_text" in st.session_state:
            st.markdown("**生成された告知文：**")
            st.text_area("告知文", height=150, key="ops_text_area")
            st.caption("👆 長押し→全選択→コピーしてLINEに貼り付けてください")
        if gen_img and flavor_input:
            with st.spinner("画像を生成中...（30秒ほどかかります）"):
                img_bytes = generate_flavor_image(flavor_input, title_input)
            if img_bytes:
                st.session_state["ops_generated_img"] = img_bytes
        if "ops_generated_img" in st.session_state:
            st.image(st.session_state["ops_generated_img"], use_column_width=True)
            fname = flavor_input if "ops_flavor" in st.session_state else "flavor"
            st.download_button("📥 画像をダウンロード",
                data=st.session_state["ops_generated_img"],
                file_name=f"mosh_{fname}_{date.today()}.jpg",
                mime="image/jpeg", use_container_width=True)
        if not HAS_GEMINI:
            st.info("💡 画像生成にはGoogle AI APIキーの設定が必要です")

    with op_tab2:
        col_title, col_clear_all = st.columns([3, 1])
        with col_title:
            st.markdown("**終業報告フォームに入力してください**")
        with col_clear_all:
            if st.button("🗑 全部クリア", key="ops_clear_all", use_container_width=True):
                st.session_state["ops_new"]            = 0
                st.session_state["ops_repeat"]         = 0
                st.session_state["ops_visitor_search"] = ""
                st.session_state["ops_done"]           = ""
                st.session_state["ops_todo"]           = ""
                st.session_state["ops_notice"]         = ""
                st.session_state["ops_register"]       = ""
                for k in ["ops_report", "ops_report_area", "ops_generated_text"]:
                    st.session_state.pop(k, None)
                st.rerun()
        today_str = date.today().strftime("%Y/%m/%d")
        col_a, col_b = st.columns(2)
        with col_a:
            new_count = st.number_input("新規来店", min_value=0, step=1, key="ops_new")
        with col_b:
            repeat_count = st.number_input("リピート来店", min_value=0, step=1, key="ops_repeat")
        all_visitor_names = st.text_area(
            "来店者（読点・改行で区切る）",
            placeholder="てらかどさん、かいとさん\nもひかんさん",
            height=80, key="ops_visitor_search"
        )
        done_today    = st.text_area("今日やったこと（1行1項目）",
            placeholder="・清掃\n・SNS投稿", height=100, key="ops_done")
        todo_tomorrow = st.text_area("明日やってほしいこと（1行1項目）",
            placeholder="・○○の補充", height=80, key="ops_todo")
        notice        = st.text_area("連絡事項（営業の様子・気づき）",
            placeholder="今日は○○でした", height=80, key="ops_notice")
        register_diff = st.text_input("レジ締め過不足",
            placeholder="0（不足の場合は -500 など）", key="ops_register")
        def _add_san(raw: str) -> str:
            """読点・カンマ・改行で区切られた名前に「さん」を自動付与"""
            import re
            names = re.split(r"[、,，\n]", raw)
            result = []
            for n in names:
                n = n.strip()
                if not n:
                    continue
                if not re.search(r"(さん|くん|ちゃん|様|氏)$", n):
                    n += "さん"
                result.append(n)
            return "、".join(result)

        if st.button("📋 終業報告を生成", type="primary", use_container_width=True):
            flavor_for_report = st.session_state.get("ops_flavor", "")
            report = generate_discord_report(
                store_label, today_str, flavor_for_report,
                int(new_count), int(repeat_count),
                _add_san(all_visitor_names), done_today, todo_tomorrow, notice, register_diff)
            st.session_state["ops_report"] = report
        if "ops_report" in st.session_state:
            st.markdown("**生成された終業報告：**")
            st.code(st.session_state["ops_report"], language=None)
            st.caption("↑ 右上の📋アイコンをタップしてDiscordに貼り付けてください")

    with op_tab3:
        st.markdown("**自由にプロンプトを入力して画像を生成できます**")
        free_prompt = st.text_area(
            "画像プロンプト",
            placeholder="例：暗い雰囲気のバーで、レモンとミントが入ったグラスとシーシャが並んでいる写真",
            height=120, key="free_prompt"
        )
        free_title = st.text_input("画像タイトル（任意）",
            placeholder="例：Lemon Mint、本日のおすすめ", key="free_title")
        gen_free = st.button("🎨 画像を生成", use_container_width=True,
                             disabled=not HAS_OPENAI, key="free_gen_btn", type="primary")
        if gen_free and free_prompt.strip():
            with st.spinner("画像を生成中...（40〜60秒ほどかかります）"):
                img_bytes = generate_free_image(free_prompt.strip(), free_title)
            if img_bytes:
                st.session_state["free_generated_img"] = img_bytes
        if "free_generated_img" in st.session_state:
            st.image(st.session_state["free_generated_img"], use_column_width=True)
            st.download_button("📥 画像をダウンロード",
                data=st.session_state["free_generated_img"],
                file_name=f"mosh_free_{date.today()}.jpg",
                mime="image/jpeg", use_container_width=True)
        if not HAS_GEMINI:
            st.info("💡 画像生成にはGoogle AI APIキーの設定が必要です")

# ─────────────────────────────────────────
# メインルーティング
# ─────────────────────────────────────────
_invite_token = st.query_params.get("invite", None)

if _invite_token and not st.session_state.user:
    # ── 招待URL経由のランディング ──
    inv = db.get_invitation(_invite_token)

    # ロゴ共通表示
    st.markdown("""
    <div style="text-align:center;padding:24px 0 8px;">
      <img src="https://shisha-mosh.jp/images/top/logo.png"
           alt="MOSH" style="height:44px;object-fit:contain;" />
      <div style="margin-top:6px;font-size:0.85rem;color:#666;">顧客管理システム</div>
    </div>
    """, unsafe_allow_html=True)

    if not inv:
        st.error("この招待リンクは無効か期限切れです。オーナーに新しいリンクを発行してもらってください。")

    elif st.session_state.invite_action is None:
        # ── ① ボタン選択画面 ──
        st.markdown("<div style='text-align:center;font-size:1.1rem;font-weight:600;margin-bottom:20px;'>はじめてですか？</div>", unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🆕 新規登録", use_container_width=True, type="primary"):
                st.session_state.invite_action = "register"
                st.rerun()
        with col2:
            if st.button("🔑 ログイン", use_container_width=True):
                st.session_state.invite_action = "login"
                st.rerun()

    elif st.session_state.invite_action == "register":
        # ── ② 新規登録：IDだけ決める ──
        role_jp   = {"staff":"スタッフ","manager":"店長","owner":"オーナー","executive":"経営陣"}.get(inv["role"],"スタッフ")
        store_str = inv["store"] if inv["store"] else "全店舗"
        st.markdown("#### 🎉 アカウント登録")
        st.caption(f"権限: **{role_jp}**　担当: **{store_str}**")
        with st.form("register_form"):
            reg_username = st.text_input("自分のID（ログインIDになります）", placeholder="例: tanaka")
            reg_submit = st.form_submit_button("登録してはじめる", type="primary", use_container_width=True)
        if reg_submit:
            if not reg_username.strip():
                st.error("IDを入力してください")
            else:
                ok = db.add_user(reg_username.strip(), SHARED_PASSWORD, inv["role"], inv["store"])
                if ok:
                    db.use_invitation(_invite_token)
                    user = db.verify_user(reg_username.strip(), SHARED_PASSWORD)
                    if user:
                        token = db.create_session_token(user["id"])
                        st.session_state.user = user
                        st.session_state.login_token = token
                        set_auth_cookie(token)
                        st.query_params.clear()
                        st.query_params["t"] = token
                        st.rerun()
                else:
                    st.error("そのIDはすでに使われています。別のIDを試してください。")
        if st.button("← 戻る", key="back_from_register"):
            st.session_state.invite_action = None
            st.rerun()

    elif st.session_state.invite_action == "login":
        # ── ③ ログインフォーム（既存アカウント） ──
        st.markdown("#### 🔑 ログイン")
        with st.form("invite_login_form"):
            username = st.text_input("ユーザーID", placeholder="自分のIDを入力")
            password = st.text_input("パスワード", type="password", placeholder="パスワードを入力")
            remember = st.checkbox("ログイン状態を保持する（30日間）", value=True)
            login_submit = st.form_submit_button("ログイン", type="primary", use_container_width=True)
        if login_submit:
            user = db.verify_user(username, password)
            if user:
                st.session_state.user = user
                if remember:
                    token = db.create_session_token(user["id"])
                    st.session_state.login_token = token
                    st.query_params["t"] = token
                    set_auth_cookie(token)
                st.rerun()
            else:
                st.error("IDまたはパスワードが違います")
        if st.button("← 戻る", key="back_from_login"):
            st.session_state.invite_action = None
            st.rerun()

elif not st.session_state.user:
    show_login()
else:
    show_header()

    if st.session_state.page == "detail":
        show_detail()
    else:
        user = st.session_state.user
        if user["role"] == "owner":
            tab_home, tab_dash, tab_ops, tab_users = st.tabs(["👥 顧客一覧", "📊 ダッシュボード", "📢 今日の営業", "⚙️ ユーザー管理"])
            with tab_home:
                show_home()
            with tab_dash:
                show_dashboard()
            with tab_ops:
                show_operations()
            with tab_users:
                show_user_management()
        else:
            tab_home, tab_dash, tab_ops = st.tabs(["👥 顧客一覧", "📊 ダッシュボード", "📢 今日の営業"])
            with tab_home:
                show_home()
            with tab_dash:
                show_dashboard()
            with tab_ops:
                show_operations()
