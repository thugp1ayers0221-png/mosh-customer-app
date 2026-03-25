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

# ─────────────────────────────────────────
# MOSHブランドCSS（スマホ対応）
# ─────────────────────────────────────────
st.markdown("""
<style>
/* Google Fonts */
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@300;400;500;700&display=swap');

/* カラー変数 */
:root {
  --mosh-sky:    #A8D8EA;
  --mosh-cream:  #F5EFE0;
  --mosh-brown:  #6B4226;
  --mosh-dark:   #2D1F0F;
  --mosh-green:  #5B8F5F;
  --rank-s:      #C8922A;
  --rank-a:      #4AA8D8;
  --rank-b:      #c8b89a;
  --rank-c:      #AAAAAA;
  --bg:          #F0F7FA;
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
}

/* ヘッダーバー */
.mosh-header {
  background: linear-gradient(135deg, var(--mosh-sky) 0%, #C5E8F5 100%);
  padding: 16px 20px 12px;
  border-radius: 0 0 20px 20px;
  margin: -1rem -1rem 1.5rem;
  display: flex;
  align-items: center;
  gap: 12px;
  box-shadow: 0 2px 12px rgba(106,66,38,0.12);
}
.mosh-logo {
  font-size: 1.6rem;
  font-weight: 700;
  color: var(--mosh-dark);
  letter-spacing: -0.5px;
  line-height: 1;
}
.mosh-logo span {
  font-size: 0.75rem;
  font-weight: 400;
  color: var(--mosh-brown);
  display: block;
  letter-spacing: 0.5px;
}
.mosh-user-badge {
  margin-left: auto;
  font-size: 0.8rem;
  background: white;
  padding: 4px 12px;
  border-radius: 20px;
  color: var(--mosh-brown);
  font-weight: 500;
}

/* 検索バー */
.search-wrap input {
  font-size: 1rem !important;
  border-radius: 12px !important;
  border: 2px solid var(--mosh-sky) !important;
  padding: 10px 16px !important;
}

/* カード（ランク色帯つき） */
.customer-card {
  background: white;
  border-radius: 14px;
  margin-bottom: 8px;
  box-shadow: 0 1px 6px rgba(106,66,38,0.08);
  display: flex;
  overflow: hidden;
  cursor: pointer;
  transition: box-shadow 0.15s;
}
.customer-card:active { box-shadow: 0 2px 10px rgba(106,66,38,0.18); }
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
  background: var(--mosh-cream);
  padding: 1px 7px;
  border-radius: 8px;
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
  background: white !important;
  border: 1px solid #eee !important;
  border-radius: 0 12px 12px 0 !important;
  padding: 10px 14px !important;
  box-shadow: 0 1px 4px rgba(106,66,38,0.07) !important;
  height: auto !important;
  min-height: 64px !important;
  white-space: pre-line !important;
  color: var(--mosh-dark) !important;
  font-size: 0.9rem !important;
  line-height: 1.6 !important;
}
.card-list .stButton button:hover {
  background: #fafafa !important;
  box-shadow: 0 2px 8px rgba(106,66,38,0.12) !important;
}

/* ランクバッジ */
.rank-badge {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 20px;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.5px;
}
.rank-V { background: linear-gradient(135deg,#6B21A8,#A855F7); color: white; letter-spacing:1px; }
.rank-S { background: var(--rank-s); color: #fff; }
.rank-A { background: var(--rank-a); color: #fff; }
.rank-B { background: var(--rank-b); color: #6B4226; }
.rank-C { background: var(--rank-c); color: #555; }

/* トレンド表示 */
.trend-up   { color: #16A34A; font-weight:700; font-size:1rem; }
.trend-down { color: #DC2626; font-weight:700; font-size:1rem; }
.trend-flat { color: #9CA3AF; font-size:0.9rem; }

/* トップ替え警告（3回到達） */
.top-change-alert {
  background: #FEE2E2;
  border: 2px solid #EF4444;
  border-radius: 10px;
  padding: 10px 14px;
  color: #991B1B;
  font-weight: 700;
  text-align: center;
  margin-bottom: 10px;
}
.top-change-ok {
  background: #F0FDF4;
  border: 1.5px solid #86EFAC;
  border-radius: 10px;
  padding: 10px 14px;
  color: #166534;
  text-align: center;
  margin-bottom: 10px;
}

/* フィルターバー */
.filter-bar {
  background: var(--mosh-cream);
  border-radius: 12px;
  padding: 12px 14px;
  margin-bottom: 16px;
}

/* メトリクスカード */
.metric-card {
  background: white;
  border-radius: 12px;
  padding: 14px 16px;
  text-align: center;
  box-shadow: 0 1px 6px rgba(0,0,0,0.06);
}
.metric-value {
  font-size: 2rem;
  font-weight: 700;
  color: var(--mosh-brown);
  line-height: 1.1;
}
.metric-label {
  font-size: 0.78rem;
  color: #888;
  margin-top: 2px;
}

/* ナビゲーションタブ */
.nav-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}
.nav-tab {
  flex: 1;
  text-align: center;
  padding: 10px 8px;
  border-radius: 10px;
  font-size: 0.82rem;
  font-weight: 500;
  cursor: pointer;
  background: white;
  color: #888;
  border: 1.5px solid #eee;
}
.nav-tab.active {
  background: var(--mosh-sky);
  color: var(--mosh-dark);
  border-color: var(--mosh-sky);
  font-weight: 700;
}

/* 顧客詳細 */
.customer-header {
  background: linear-gradient(135deg, var(--mosh-cream), white);
  border-radius: 14px;
  padding: 18px;
  margin-bottom: 14px;
  border: 1.5px solid #e8ddd0;
}
.customer-name {
  font-size: 1.4rem;
  font-weight: 700;
  color: var(--mosh-dark);
}
.visit-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px solid #f0e8e0;
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
  border-radius: 10px;
  padding: 10px 14px;
  font-size: 0.82rem;
  color: #92400E;
  margin-bottom: 12px;
}

/* ログイン画面 */
.login-wrap {
  max-width: 360px;
  margin: 60px auto 0;
  padding: 32px 28px;
  background: white;
  border-radius: 20px;
  box-shadow: 0 4px 24px rgba(106,66,38,0.12);
}
.login-logo {
  text-align: center;
  font-size: 2rem;
  font-weight: 700;
  color: var(--mosh-dark);
  margin-bottom: 6px;
}
.login-sub {
  text-align: center;
  font-size: 0.8rem;
  color: var(--mosh-brown);
  margin-bottom: 24px;
}

/* Streamlitデフォルト上書き */
.stButton > button {
  border-radius: 10px !important;
  font-family: 'Noto Sans JP', sans-serif !important;
  font-weight: 500 !important;
}
/* 顧客カードボタン 共通 */
[data-testid="baseButton-secondary"] {
  width: 100% !important;
  border-radius: 12px !important;
  padding: 12px 16px !important;
  text-align: center !important;
  font-size: 15px !important;
  font-weight: 600 !important;
  line-height: 1.6 !important;
  min-height: 56px !important;
  box-shadow: 0 2px 5px rgba(0,0,0,0.08) !important;
  margin-bottom: 6px !important;
  transition: filter 0.15s ease !important;
}
[data-testid="baseButton-secondary"] p {
  white-space: pre-line !important;
  text-align: center !important;
  margin: 0 !important;
}
[data-testid="baseButton-secondary"]:hover {
  filter: brightness(0.94) !important;
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
  border-radius: 10px !important;
  font-family: 'Noto Sans JP', sans-serif !important;
}
div[data-testid="stTabs"] button {
  font-family: 'Noto Sans JP', sans-serif !important;
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
  0%   { transform: rotate(-8deg) scale(1);   }
  25%  { transform: rotate( 8deg) scale(1.08);}
  50%  { transform: rotate(-5deg) scale(1);   }
  75%  { transform: rotate( 5deg) scale(1.05);}
  100% { transform: rotate(-8deg) scale(1);   }
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
  color: var(--mosh-brown) !important;
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
  border-radius: 16px;
  animation: mosh-wobble 0.6s ease-in-out infinite, mosh-float 1.4s ease-in-out infinite;
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
  animation: mosh-wobble 0.6s ease-in-out infinite, mosh-float 1.4s ease-in-out infinite;
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

    # S候補の通知（全顧客から検索）
    all_customers_for_s = cached_get_customers(limit=9999)
    s_candidates = [c for c in all_customers_for_s if c["total_visits"] >= 10 and c["rank"] == "A"]
    if s_candidates and user["role"] in ("owner","manager","executive"):
        with st.expander(f"⚠️ Sランク候補 {len(s_candidates)}名（来店10回以上・未昇格）"):
            # 一括昇格ボタン
            if user["role"] in ("owner","executive"):
                if st.button(f"🚀 {len(s_candidates)}名を全員Sに一括昇格", type="primary", use_container_width=True):
                    for c in s_candidates:
                        db.set_rank(c["id"], "S", user["username"])
                    st.success(f"{len(s_candidates)}名をSランクに昇格しました")
                    st.rerun()
            for c in s_candidates[:5]:
                col1, col2 = st.columns([4,1])
                with col1:
                    st.write(f"**{c['name']}** ({c['primary_store']}) — {c['total_visits']}回来店")
                with col2:
                    if st.button("S昇格", key=f"promote_{c['id']}"):
                        db.set_rank(c["id"], "S", user["username"])
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
    c    = db.get_customer(cid)
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
        visits = db.get_visits(cid)
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
        stats = db.get_visit_stats(cid)

        if stats["by_dow"]:
            fig_dow = go.Figure(go.Bar(
                x=list(stats["by_dow"].keys()),
                y=list(stats["by_dow"].values()),
                marker_color="#A8D8EA",
                marker_line_color="#6B4226",
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
                marker_color="#F5EFE0",
                marker_line_color="#6B4226",
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
                            conn.execute(
                                "UPDATE customers SET is_member=? WHERE id=?",
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

    # メトリクス
    col1, col2, col3, col4 = st.columns(4)
    metrics = [
        (s.get("new_total",0),                       "新規"),
        (s.get("repeat_b",0),                        "リピーター"),
        (r.get("A",0) + s.get("repeat_a",0),         "A（名前あり）"),
        (r.get("S",0) + r.get("V",0),                "S（超常連）"),
    ]
    for col, (val, label) in zip([col1,col2,col3,col4], metrics):
        with col:
            st.markdown(f"""
            <div class="metric-card">
              <div class="metric-value">{val}</div>
              <div class="metric-label">{label}</div>
            </div>
            """, unsafe_allow_html=True)

    st.write("")

    # ランク分布パイチャート
    # ラベル → (表示名, 色)
    rank_color_map = {
        "S": ("#FFB800", r.get("S",0) + r.get("V",0)),
        "A": ("#4FB8F0", r.get("A",0)),
        "B": ("#52D68A", s.get("repeat_b",0)),
        "C": ("#FF8C69", s.get("new_total",0)),
    }
    rank_labels  = [k for k, (_, v) in rank_color_map.items() if v > 0]
    rank_values  = [v for _, (_, v) in rank_color_map.items() if v > 0]
    rank_colors  = [c for _, (c, v) in rank_color_map.items() if v > 0]

    if rank_labels:
        fig = go.Figure(go.Pie(
            labels=rank_labels,
            values=rank_values,
            hole=0.45,
            marker=dict(
                colors=rank_colors,
                line=dict(color="#FFFFFF", width=2)
            ),
            textinfo="label+percent",
            textfont_size=13,
        ))
        fig.update_layout(
            title=f"ランク分布 — {sel_store} {sel_period}",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(t=50,b=10,l=10,r=10),
            height=300,
            font=dict(family="Noto Sans JP", color="#4A3728"),
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
            ss = all_stores_data.get(store, {})
            new_c  = ss.get("new_total", 0)
            rep_b  = ss.get("repeat_b", 0)
            rep_a  = ss.get("repeat_a", 0)
            total  = new_c + rep_b + rep_a + ss.get("cafe_total", 0)
            color  = store_colors.get(store, "#A8D8EA")
            st.markdown(f"""
            <div style="
              background:#fff;
              border:1px solid #e8ddd4;
              border-left:5px solid {color};
              border-radius:10px;
              padding:14px 18px;
              margin-bottom:10px;
              box-shadow:0 1px 4px rgba(106,66,38,0.07);
              width:100%;
              box-sizing:border-box;
            ">
              <div style="font-size:1.05rem;font-weight:700;color:#4A3728;margin-bottom:8px;">
                🏪 {store}
              </div>
              <div style="display:flex;gap:8px;flex-wrap:nowrap;align-items:flex-start;">
                <div style="text-align:center;flex:1;min-width:0;">
                  <div style="font-size:1.2rem;font-weight:700;color:#FF8C69;">{new_c}</div>
                  <div style="font-size:0.68rem;color:#9E8B7D;">C 新規</div>
                </div>
                <div style="text-align:center;flex:1;min-width:0;">
                  <div style="font-size:1.2rem;font-weight:700;color:#4FB8F0;">{rep_b}</div>
                  <div style="font-size:0.68rem;color:#9E8B7D;">B リピーター</div>
                </div>
                <div style="text-align:center;flex:1;min-width:0;">
                  <div style="font-size:1.2rem;font-weight:700;color:#52D68A;">{rep_a}</div>
                  <div style="font-size:0.68rem;color:#9E8B7D;">A 名前あり</div>
                </div>
                <div style="text-align:center;flex:1;min-width:0;padding-left:8px;border-left:1px solid #e8ddd4;">
                  <div style="font-size:1.3rem;font-weight:800;color:#4A3728;">{total}</div>
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
            "#FF6B35" if v == max_val else "#A8D8EA"
            for v in totals
        ]

        fig_wd = go.Figure()
        fig_wd.add_trace(go.Bar(
            x=labels,
            y=totals,
            marker_color=bar_colors,
            text=[f"{v:.1f}" for v in totals],
            textposition="outside",
            textfont=dict(size=11, color="#4A3728"),
            hovertemplate="<b>%{x}曜日</b><br>平均合計: %{y:.1f}人<extra></extra>",
            name="合計",
        ))
        fig_wd.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(t=20, b=10, l=10, r=10),
            height=220,
            font=dict(family="Noto Sans JP", color="#4A3728", size=12),
            xaxis=dict(showgrid=False, tickfont=dict(size=14, color="#4A3728")),
            yaxis=dict(showgrid=True, gridcolor="#f0e8df", zeroline=False),
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
LINE_SAMPLES = """
- open💭💫 こんばんは、ﾐｷです。本日のおすすめは「チェリースカイ」チェリーを使ったカクテルミックスです🍸🍒 フルーティで甘酸っぱい香りがふわっと広がって、気分がぱっと明るくなる一本！ぜひ試してみてください🫧
- Open💭💫 本日のおすすめは「🦋ユリシス🦋」宝石のように鮮やかな蒼い羽を持った蝶をイメージしたミックス。清涼感のある爽やかなブルーベリーの香りと、ほんのり甘いフルーツが絶妙にマッチ✨想像しただけでうっとりしませんか？
- おーぷん！！本日のおすすめはグアバとバニラ！会わなそうでとてもよく合う魔法のMIX！グアバの甘みとバニラのまろやかさが合わさって、不思議と落ち着く味わいです🧡ぜひ🫶
- 本日も20時よりオープン！おすすめは「完熟メロンボトル」🍈口に入れた瞬間、みずみずしい甘さがじゅわっと広がります。これは実物見てほしい一品😳限定2台なのでお早めに！
- オープンしました！今日のオススメは「正座」🍵シーシャでは珍しい和風なお茶と和菓子の香り。どこかなつかしくてほっこりする一本です。ぜひ体験しにきてください！
- メイソンズオープン！本日のおすすめは「ボムシェル×柑橘フルーツ」🍊ボムシェルのトロピカルな甘さに柑橘のさっぱり感が加わって、最高にバランスのいい組み合わせです。ご来店お待ちしております。
""".strip()

# 店舗別フォールバックサンプル（DBにデータがない場合に使用）
_STORE_FALLBACK_SAMPLES = {
    "メイソンズ": """
- メイソンズオープン！本日のおすすめは「ボムシェル×柑橘フルーツ」🍊ボムシェルのトロピカルな甘さに柑橘のさっぱり感が加わって、最高にバランスのいい組み合わせです。ご来店お待ちしております。
- open💭💫 こんばんはMIKIです✨本日のおすすめは「チェリースカイ」🍒チェリーを使ったカクテルミックスです。フルーティで甘酸っぱい香りがふわっと広がって気分がぱっと明るくなる一本！ぜひ🫧
- Open💭💫 本日のおすすめは「🦋ユリシス🦋」宝石のように鮮やかな蒼い羽を持った蝶をイメージしたミックス。清涼感のある爽やかなブルーベリーの香りと、ほんのり甘いフルーツが絶妙にマッチ✨
""".strip(),
    "柏": """
- 柏店オープンしました🫧本日のおすすめは「{flavor}」です！ぜひ遊びに来てください。お待ちしております🙌
- こんばんは〜！柏MOSHです🌙今日のイチオシフレーバーをご紹介します✨ひと口吸うと…広がる香りをぜひ体感してください！
- 柏店、本日もオープン！スタッフ一同お待ちしています🔥今日のおすすめフレーバーは必見です。ぜひお気軽にお立ち寄りください☕
""".strip(),
    "東村山": """
- 東村山オープン！本日もスタッフ一同お待ちしております🫧今日のおすすめをぜひ試してみてください✨
- こんばんは！東村山MOSHです🌙本日のイチオシフレーバー、ぜひ体験しにきてください🔥
- 東村山店オープンしました〜！今日も居心地よい空間でお待ちしてます。おすすめフレーバーについてはぜひ直接聞いてください😊
""".strip(),
    "おおたか": """
- おおたかの森店オープン！本日もシーシャを楽しみに来てください🫧おすすめフレーバーは必見です✨
- こんばんは、おおたかMOSHです🌙今日のイチオシをご紹介します！ひと口で気分が上がる一本です🔥ぜひ。
- おおたか店、本日もオープンしました！ゆったりとした時間をぜひMOSHで。スタッフ一同お待ちしてます🙌
""".strip(),
    "西船橋": """
- 西船橋オープン！本日もご来店お待ちしております🫧今日のおすすめフレーバーもぜひ✨
- こんばんは！西船橋MOSHです🌙本日のイチオシ、ぜひ体験しに来てください😊スタッフ一同お待ちしてます。
- 西船橋店オープンしました！今日も居心地のよい空間でのんびりシーシャを楽しんでいただけます🔥お気軽にどうぞ。
""".strip(),
}

@st.cache_data(ttl=3600, show_spinner=False)
def _cached_line_samples(store: str) -> str:
    """店舗のサンプル告知文をキャッシュ付きで取得（1時間TTL）"""
    try:
        rows = db.get_line_samples(store)
        if rows:
            return "\n".join(f"- {t}" for t in rows)
    except Exception:
        pass
    # 店舗別フォールバック → 共通フォールバックの順
    return _STORE_FALLBACK_SAMPLES.get(store, LINE_SAMPLES)

def generate_open_text(flavor: str, style_store: str) -> str:
    if not HAS_ANTHROPIC:
        return "⚠️ AI機能が無効です（ANTHROPIC_API_KEY未設定）"
    samples = _cached_line_samples(style_store)
    import random as _random
    variation_hints = [
        "出だしは天気・季節の話題から入る",
        "出だしはオープンの一言からシンプルに始める",
        "出だしは今日の気分・気持ちを表す言葉から",
        "出だしはフレーバー名を最初に出す",
        "出だしはお客さんへの呼びかけから始める",
    ]
    hint = _random.choice(variation_hints)
    try:
        msg = _anthropic_client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=350,
            system=f"""あなたはシーシャバー「MOSH {style_store}」のスタッフです。
毎日LINEオープンチャットにオープン告知を投稿します。

【{style_store}の過去の投稿サンプル（この文体・トーン・絵文字を継承）】
{samples}

【必須ルール】
- サンプルの文体・絵文字パターンを継承する
- 構成：①オープンの一言 ②フレーバー名 ③味わい・香り・イメージを2〜3文で描写 ④来店を促す一言
- ③「ひと口吸うと〜」「〜な香りが」「〜をイメージした」などで具体的に
- 150〜200文字程度
- 今回のバリエーション指示：{hint}""",
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

def generate_flavor_image(flavor: str):
    if not HAS_OPENAI:
        return None
    try:
        prompt = (
            f"Premium shisha hookah with {flavor} flavor. "
            f"Beautiful fruits and ingredients surrounding an elegant hookah pipe. "
            f"Smoke atmosphere, dark moody background, professional food photography style. "
            f"High quality, appetizing, Instagram-worthy image."
        )
        response = _openai_client.images.generate(
            model="dall-e-3", prompt=prompt,
            size="1024x1024", quality="standard", n=1,
        )
        import requests as _requests
        img_url = response.data[0].url
        return _requests.get(img_url).content
    except Exception as e:
        st.error(f"画像生成エラー: {e}")
        return None

def show_operations():
    user = st.session_state.user
    store = user.get("store", "") or ""
    store_label = store if store else "MOSH"
    st.markdown("### 📢 今日の営業")
    op_tab1, op_tab2 = st.tabs(["🟢 オープン告知", "🌙 終業報告"])

    with op_tab1:
        st.markdown("**今日のおすすめフレーバーを入力してください**")
        flavor_input = st.text_input("フレーバー",
            placeholder="例：レモンミント、ピーチ、グレープ", key="ops_flavor")

        # 店舗スタイル選択
        try:
            style_stores = db.get_line_sample_stores()
        except Exception:
            style_stores = []
        style_options = style_stores if style_stores else ["メイソンズ", "西船橋", "おおたか", "東村山", "柏"]
        default_idx = style_options.index(store_label) if store_label in style_options else 0
        selected_style = st.selectbox(
            "📝 文体スタイル（どの店舗風で書きますか？）",
            options=style_options,
            index=default_idx,
            key="ops_style"
        )

        col1, col2 = st.columns(2)
        with col1:
            gen_text = st.button("📝 告知文を生成", use_container_width=True, type="primary")
        with col2:
            gen_img = st.button("🎨 画像を生成", use_container_width=True, disabled=not HAS_OPENAI)
        if gen_text and flavor_input:
            with st.spinner("告知文を生成中..."):
                text = generate_open_text(flavor_input, selected_style)
            st.session_state["ops_generated_text"] = text
        if "ops_generated_text" in st.session_state:
            st.markdown("**生成された告知文：**")
            st.text_area("告知文", value=st.session_state["ops_generated_text"],
                         height=150, key="ops_text_area")
            st.caption("👆 長押し→全選択→コピーしてLINEに貼り付けてください")
        if gen_img and flavor_input:
            with st.spinner("画像を生成中...（30秒ほどかかります）"):
                img_bytes = generate_flavor_image(flavor_input)
            if img_bytes:
                st.session_state["ops_generated_img"] = img_bytes
        if "ops_generated_img" in st.session_state:
            st.image(st.session_state["ops_generated_img"], use_column_width=True)
            fname = flavor_input if "ops_flavor" in st.session_state else "flavor"
            st.download_button("📥 画像をダウンロード",
                data=st.session_state["ops_generated_img"],
                file_name=f"mosh_{fname}_{date.today()}.jpg",
                mime="image/jpeg", use_container_width=True)
        if not HAS_OPENAI:
            st.info("💡 画像生成にはOpenAI APIキーの設定が必要です")

    with op_tab2:
        col_title, col_clear_all = st.columns([3, 1])
        with col_title:
            st.markdown("**終業報告フォームに入力してください**")
        with col_clear_all:
            if st.button("🗑 全部クリア", key="ops_clear_all", use_container_width=True):
                for k in ["ops_new", "ops_repeat", "ops_visitor_list", "ops_visitor_search",
                          "ops_done", "ops_todo", "ops_notice", "ops_register", "ops_report",
                          "ops_report_area", "ops_generated_text"]:
                    st.session_state.pop(k, None)
                st.session_state.ops_visitor_list = []
                st.rerun()
        today_str = date.today().strftime("%Y/%m/%d")
        col_a, col_b = st.columns(2)
        with col_a:
            new_count = st.number_input("新規来店", min_value=0, value=0, step=1, key="ops_new")
        with col_b:
            repeat_count = st.number_input("リピート来店", min_value=0, value=0, step=1, key="ops_repeat")
        try:
            all_customers = db.get_all_customers(store if store and store != "本部" else None)
            customer_names = sorted([c["name"] for c in all_customers if c.get("name")])
        except Exception:
            customer_names = []

        # 来店者リスト（session_stateで管理）
        if "ops_visitor_list" not in st.session_state:
            st.session_state.ops_visitor_list = []

        st.markdown("**来店者**")
        visitor_search = st.text_input(
            "名前を入力（予測変換）",
            placeholder="あ → 朝見さん…",
            key="ops_visitor_search"
        )
        # 入力に応じて候補を表示
        if visitor_search:
            candidates = [n for n in customer_names if visitor_search in n][:8]
            if candidates:
                cols = st.columns(min(len(candidates), 4))
                for i, name in enumerate(candidates):
                    with cols[i % 4]:
                        if st.button(name, key=f"cand_{name}", use_container_width=True):
                            if name not in st.session_state.ops_visitor_list:
                                st.session_state.ops_visitor_list.append(name)
                            st.rerun()
            else:
                # DBにない名前はそのまま追加できる
                if st.button(f"「{visitor_search}」を追加", key="cand_new", use_container_width=True):
                    if visitor_search not in st.session_state.ops_visitor_list:
                        st.session_state.ops_visitor_list.append(visitor_search)
                    st.rerun()

        # 選択済みリスト表示
        if st.session_state.ops_visitor_list:
            st.markdown("**追加済み：**")
            for name in list(st.session_state.ops_visitor_list):
                c1, c2 = st.columns([5, 1])
                with c1:
                    st.markdown(f"• {name}")
                with c2:
                    if st.button("✕", key=f"del_{name}"):
                        st.session_state.ops_visitor_list.remove(name)
                        st.rerun()
            if st.button("🗑 リストをクリア", key="ops_clear_visitors"):
                st.session_state.ops_visitor_list = []
                st.rerun()

        all_visitor_names = "\n".join(st.session_state.ops_visitor_list)
        done_today    = st.text_area("今日やったこと（1行1項目）",
            placeholder="・清掃\n・SNS投稿", height=100, key="ops_done")
        todo_tomorrow = st.text_area("明日やってほしいこと（1行1項目）",
            placeholder="・○○の補充", height=80, key="ops_todo")
        notice        = st.text_area("連絡事項（営業の様子・気づき）",
            placeholder="今日は○○でした", height=80, key="ops_notice")
        register_diff = st.text_input("レジ締め過不足",
            placeholder="0（不足の場合は -500 など）", key="ops_register")
        if st.button("📋 終業報告を生成", type="primary", use_container_width=True):
            flavor_for_report = st.session_state.get("ops_flavor", "")
            report = generate_discord_report(
                store_label, today_str, flavor_for_report,
                int(new_count), int(repeat_count),
                all_visitor_names, done_today, todo_tomorrow, notice, register_diff)
            st.session_state["ops_report"] = report
        if "ops_report" in st.session_state:
            st.markdown("**生成された終業報告：**")
            st.code(st.session_state["ops_report"], language=None)
            st.caption("↑ 右上の📋アイコンをタップしてDiscordに貼り付けてください")

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
