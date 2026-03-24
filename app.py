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
import db

# ─────────────────────────────────────────
# ページ設定
# ─────────────────────────────────────────
st.set_page_config(
    page_title="MOSH 顧客管理",
    page_icon="🫧",
    layout="wide",
    initial_sidebar_state="collapsed",
)

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
  --rank-s:      #C9A84C;
  --rank-a:      #7B5230;
  --rank-b:      #5B7FA6;
  --rank-c:      #9E9E9E;
  --bg:          #F0F7FA;
}

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

/* カード */
.mosh-card {
  background: white;
  border-radius: 14px;
  padding: 14px 16px;
  margin-bottom: 10px;
  box-shadow: 0 1px 6px rgba(106,66,38,0.08);
  border-left: 4px solid var(--mosh-sky);
  cursor: pointer;
  transition: transform 0.1s, box-shadow 0.1s;
}
.mosh-card:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 14px rgba(106,66,38,0.14);
}
.mosh-card-name {
  font-size: 1.05rem;
  font-weight: 600;
  color: var(--mosh-dark);
}
.mosh-card-meta {
  font-size: 0.78rem;
  color: #888;
  margin-top: 3px;
}
.mosh-card-visits {
  font-size: 1.4rem;
  font-weight: 700;
  color: var(--mosh-brown);
  float: right;
  line-height: 1.2;
}
.mosh-card-visits span {
  font-size: 0.7rem;
  font-weight: 400;
  display: block;
  text-align: right;
  color: #aaa;
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
.rank-S { background: var(--rank-s); color: white; }
.rank-A { background: var(--rank-a); color: white; }
.rank-B { background: var(--rank-b); color: white; }
.rank-C { background: var(--rank-c); color: white; }

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
/* アプリ下部のStreamlit広告バナー */
[data-testid="stBottom"]               { display: none !important; }
.viewerBadge_container__r5tak         { display: none !important; }
#stDecoration                          { display: none !important; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────
# セッション初期化
# ─────────────────────────────────────────
if "user" not in st.session_state:
    st.session_state.user = None
if "page" not in st.session_state:
    st.session_state.page = "home"
if "selected_customer" not in st.session_state:
    st.session_state.selected_customer = None

RANK_LABEL = {"V": "💎 VIP", "S": "🏆 S", "A": "⭐ A", "B": "🔵 B", "C": "🆕 C"}
RANK_DESC  = {
    "V": "VIP会員（Masons専用）",
    "S": "ロイヤル（10回以上）",
    "A": "顔なじみリピーター",
    "B": "名前不明リピーター",
    "C": "新規",
}
RANK_ORDER = {"V": 0, "S": 1, "A": 2, "B": 3, "C": 4}
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
            if st.button("ログイン", use_container_width=True, type="primary"):
                user = db.verify_user(username, password)
                if user:
                    st.session_state.user = user
                    st.rerun()
                else:
                    st.error("ユーザー名またはパスワードが違います")

# ─────────────────────────────────────────
# ヘッダー
# ─────────────────────────────────────────
def show_header():
    user = st.session_state.user
    role_label = {"owner":"オーナー","manager":"店長","staff":"スタッフ"}.get(user["role"],"")
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
    user = st.session_state.user

    # フィルター
    stores = ["全店舗"] + db.get_stores()
    periods = ["全期間"] + db.get_available_periods()

    # 店長は自店舗固定
    if user["role"] == "manager" and user.get("store"):
        default_store = user["store"]
        store_disabled = True
    else:
        default_store = "全店舗"
        store_disabled = False

    with st.container():
        c1, c2, c3 = st.columns([2, 2, 2])
        with c1:
            sel_store = st.selectbox(
                "店舗", stores,
                index=stores.index(default_store) if default_store in stores else 0,
                disabled=store_disabled,
                label_visibility="collapsed",
            )
        with c2:
            sel_period = st.selectbox(
                "期間", periods,
                label_visibility="collapsed",
            )
        with c3:
            search = st.text_input(
                "検索", placeholder="🔍 名前で検索",
                label_visibility="collapsed",
            )

    store_q  = None if sel_store == "全店舗" else sel_store
    period_q = None if sel_period == "全期間" else sel_period
    search_q = search if search else None

    customers = db.get_customers(
        store=store_q,
        period=period_q,
        search=search_q,
    )

    # S候補の通知
    s_candidates = [c for c in customers if c["total_visits"] >= 10 and c["rank"] == "A"]
    if s_candidates and user["role"] in ("owner","manager"):
        with st.expander(f"⚠️ Sランク候補 {len(s_candidates)}名（来店10回以上・未昇格）"):
            for c in s_candidates[:5]:
                col1, col2 = st.columns([4,1])
                with col1:
                    st.write(f"**{c['name']}** ({c['primary_store']}) — {c['total_visits']}回来店")
                with col2:
                    if st.button("S昇格", key=f"promote_{c['id']}"):
                        db.set_rank(c["id"], "S", user["username"])
                        st.rerun()

    # 件数表示
    period_str = f"{sel_period}" if sel_period != "全期間" else "全期間"
    store_str  = sel_store
    st.caption(f"{store_str} · {period_str} · {len(customers)}名")

    # 一覧（カード全体をボタンに・トレンド表示付き）
    for c in customers:
        visits_n = c.get("period_visits") or c["total_visits"]
        last_date = c["last_visit_date"] or "-"

        rank = c.get("rank","A")
        rank_emoji = {"V":"💎","S":"🏆","A":"⭐","B":"🔵","C":"🆕"}.get(rank, rank)
        member_mark = " ✅" if c["is_member"] and c["primary_store"]=="メイソンズ" else ""
        cross_mark  = " ⚠️" if c["cross_store_flag"] else ""
        store_label = c['primary_store'] or '未設定'

        # 前月比トレンド
        this_m = c.get("visits_this_month") or 0
        last_m = c.get("visits_last_month") or 0
        if this_m > last_m and last_m > 0:
            trend = f"↑+{this_m - last_m}"
        elif this_m < last_m and this_m > 0:
            trend = f"↓{this_m - last_m}"
        elif this_m > 0 and last_m == 0:
            trend = "✨新"
        else:
            trend = ""

        btn_label = (
            f"{rank_emoji} **{c['name']}**{member_mark}{cross_mark}　{trend}\n"
            f"{store_label}　最終: {last_date}　来店 **{visits_n}回**"
        )
        if st.button(btn_label, key=f"open_{c['id']}", use_container_width=True):
            st.session_state.selected_customer = c["id"]
            st.session_state.page = "detail"
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

    # 戻るボタン
    if st.button("← 一覧に戻る"):
        st.session_state.page = "home"
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
    if c["cross_store_flag"] and user["role"] in ("owner","manager"):
        st.markdown("""
        <div class="cross-store-banner">
        ⚠️ 他店舗に同じ名前の顧客がいます。同一人物ですか？
        </div>
        """, unsafe_allow_html=True)

        with st.expander("同一人物マージ"):
            stores = db.get_stores()
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
            st.plotly_chart(fig_dow, use_container_width=True)

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
            st.plotly_chart(fig_m, use_container_width=True)

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
        if user["role"] in ("owner","manager"):
            st.divider()
            st.markdown("**🏷 ランク設定**")
            current_rank = c.get("rank","A")

            # Masonsのみ VIP選択肢を追加
            rank_options = ["V","S","A","B","C"] if c["primary_store"] == "メイソンズ" else ["S","A","B","C"]
            rank_idx = rank_options.index(current_rank) if current_rank in rank_options else 1
            new_rank = st.radio(
                "ランク",
                rank_options,
                index=rank_idx,
                horizontal=True,
                help="V=VIP(Masons専用) / S=ロイヤル(10回以上) / A=顔なじみ / B=名前不明 / C=新規",
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
    stores = ["全店舗"] + db.get_stores()
    periods = ["全期間"] + db.get_available_periods()

    if user["role"] == "manager" and user.get("store"):
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

    stats = db.get_dashboard_stats(store=store_q, period=period_q)
    s = stats.get("summary", {})
    r = stats.get("rank_counts", {})

    # メトリクス
    col1, col2, col3, col4 = st.columns(4)
    metrics = [
        (s.get("new_total",0),      "🆕 新規（C）"),
        (s.get("repeat_b",0),       "🔵 リピーター（B）"),
        (s.get("repeat_a",0),       "⭐ 顔なじみ（A）"),
        (r.get("S",0),              "🏆 ロイヤル（S）"),
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
    rank_data = {
        "S（ロイヤル）":   r.get("S",0),
        "A（顔なじみ）":   r.get("A",0),
        "B（名前不明）":   r.get("B",0) + s.get("repeat_b",0),
        "C（新規）":       s.get("new_total",0),
    }
    rank_data = {k:v for k,v in rank_data.items() if v > 0}

    if rank_data:
        fig = go.Figure(go.Pie(
            labels=list(rank_data.keys()),
            values=list(rank_data.values()),
            hole=0.45,
            marker_colors=["#C9A84C","#7B5230","#5B7FA6","#9E9E9E"],
            textinfo="label+percent",
            textfont_size=11,
        ))
        fig.update_layout(
            title=f"ランク分布 — {sel_store} {sel_period}",
            paper_bgcolor="rgba(0,0,0,0)",
            margin=dict(t=50,b=10,l=10,r=10),
            height=300,
            font=dict(family="Noto Sans JP"),
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)

    # 店舗別来店サマリー（全店舗選択時）
    if not store_q:
        st.markdown("#### 店舗別サマリー")
        for store in db.get_stores():
            st_stats = db.get_dashboard_stats(store=store, period=period_q)
            ss = st_stats.get("summary", {})
            total = (ss.get("new_total",0) + ss.get("repeat_b",0) +
                     ss.get("repeat_a",0) + ss.get("cafe_total",0))
            st.markdown(f"""
            <div class="mosh-card">
              <div class="mosh-card-name">{store}</div>
              <div class="mosh-card-meta">
                新規 {ss.get('new_total',0)}名 ·
                リピ {ss.get('repeat_b',0)+ss.get('repeat_a',0)}名 ·
                合計 {total}名
              </div>
            </div>
            """, unsafe_allow_html=True)

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
    role_label = {"owner":"オーナー","manager":"店長","staff":"スタッフ"}
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

    STORES = ["", "柏", "東村山", "おおたかの森", "メイソンズ", "西船橋"]

    with st.form("add_user_form"):
        new_username = st.text_input("ユーザー名（ログインID）", placeholder="例: tanaka_kashiwa")
        new_role = st.selectbox("権限", ["staff","manager","owner"],
            format_func=lambda x: {"staff":"スタッフ","manager":"店長","owner":"オーナー"}[x],
            key="new_user_role")
        new_store = st.selectbox("担当店舗", STORES,
            format_func=lambda x: x if x else "（全店舗）",
            key="new_user_store")
        auto_pw = generate_password()
        new_password = st.text_input("パスワード", value=auto_pw,
            help="自動生成されています。変更可能です。")
        submitted = st.form_submit_button("アカウントを作成", type="primary", use_container_width=True)

    if submitted:
        if not new_username.strip():
            st.error("ユーザー名を入力してください")
        else:
            ok = db.add_user(new_username.strip(), new_password, new_role, new_store)
            if ok:
                role_jp = {"staff":"スタッフ","manager":"店長","owner":"オーナー"}[new_role]
                st.success(f"✅ アカウントを作成しました")
                st.info(
                    f"**招待情報（本人に伝えてください）**\n\n"
                    f"🌐 URL: https://mosh-customer-app.streamlit.app\n\n"
                    f"👤 ユーザー名: `{new_username.strip()}`\n\n"
                    f"🔑 パスワード: `{new_password}`\n\n"
                    f"役割: {role_jp}"
                    + (f"　店舗: {new_store}" if new_store else "")
                )
                st.rerun()
            else:
                st.error("そのユーザー名はすでに使われています")

# ─────────────────────────────────────────
# メインルーティング
# ─────────────────────────────────────────
if not st.session_state.user:
    show_login()
else:
    show_header()

    if st.session_state.page == "detail":
        show_detail()
    else:
        user = st.session_state.user
        if user["role"] == "owner":
            tab_home, tab_dash, tab_users = st.tabs(["👥 顧客一覧", "📊 ダッシュボード", "⚙️ ユーザー管理"])
            with tab_home:
                show_home()
            with tab_dash:
                show_dashboard()
            with tab_users:
                show_user_management()
        else:
            tab_home, tab_dash = st.tabs(["👥 顧客一覧", "📊 ダッシュボード"])
            with tab_home:
                show_home()
            with tab_dash:
                show_dashboard()
