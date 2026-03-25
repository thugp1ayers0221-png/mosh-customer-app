"""DB操作ヘルパー (PostgreSQL / Supabase対応版)"""
import os
import psycopg2
import psycopg2.extras
import psycopg2.pool
from contextlib import contextmanager
import threading

_pool = None
_pool_lock = threading.Lock()


def _get_database_url():
    """DATABASE_URLを環境変数 or Streamlit Secretsから取得"""
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    try:
        import streamlit as st
        return st.secrets["DATABASE_URL"]
    except Exception:
        raise RuntimeError(
            "DATABASE_URL が設定されていません。"
            "Streamlit Secrets または環境変数に DATABASE_URL を設定してください。"
        )


def _get_pool():
    """接続プールをシングルトンで返す"""
    global _pool
    with _pool_lock:
        if _pool is None:
            _pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=1, maxconn=5,
                dsn=_get_database_url(),
                cursor_factory=psycopg2.extras.RealDictCursor,
                connect_timeout=10,
                keepalives=1,
                keepalives_idle=30,
                keepalives_interval=10,
                keepalives_count=3,
                options="-c statement_timeout=60000"
            )
    return _pool


@contextmanager
def get_conn():
    pool = _get_pool()
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def migrate_db():
    """DBスキーマの自動マイグレーション（起動時に必ず実行）"""
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                # ── テーブル作成（IF NOT EXISTS で冪等） ──
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS customers (
                        id SERIAL PRIMARY KEY,
                        name TEXT NOT NULL,
                        aliases TEXT DEFAULT '',
                        primary_store TEXT DEFAULT '',
                        rank TEXT DEFAULT 'A',
                        first_visit_date TEXT,
                        last_visit_date TEXT,
                        total_visits INTEGER DEFAULT 0,
                        is_member INTEGER DEFAULT 0,
                        notes TEXT DEFAULT '',
                        cross_store_flag INTEGER DEFAULT 0,
                        merged_into INTEGER DEFAULT NULL,
                        top_change_bonus INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW()
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS visits (
                        id SERIAL PRIMARY KEY,
                        customer_id INTEGER,
                        store TEXT NOT NULL,
                        date TEXT NOT NULL,
                        service_type TEXT DEFAULT 'normal',
                        memo TEXT DEFAULT '',
                        source_file TEXT DEFAULT '',
                        FOREIGN KEY (customer_id) REFERENCES customers(id)
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS daily_summary (
                        id SERIAL PRIMARY KEY,
                        store TEXT NOT NULL,
                        date TEXT NOT NULL,
                        new_count INTEGER DEFAULT 0,
                        repeat_unnamed_count INTEGER DEFAULT 0,
                        repeat_named_count INTEGER DEFAULT 0,
                        cafe_count INTEGER DEFAULT 0,
                        source_file TEXT DEFAULT '',
                        UNIQUE(store, date)
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS merge_log (
                        id SERIAL PRIMARY KEY,
                        merged_customer_id INTEGER,
                        into_customer_id INTEGER,
                        merged_by TEXT,
                        merged_at TIMESTAMP DEFAULT NOW()
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id SERIAL PRIMARY KEY,
                        username TEXT UNIQUE NOT NULL,
                        password_hash TEXT NOT NULL,
                        role TEXT NOT NULL DEFAULT 'staff',
                        store TEXT DEFAULT '',
                        email TEXT DEFAULT '',
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS invitations (
                        token TEXT PRIMARY KEY,
                        role TEXT NOT NULL DEFAULT 'staff',
                        store TEXT DEFAULT '',
                        created_at TIMESTAMP DEFAULT NOW(),
                        expires_at TIMESTAMP DEFAULT NOW() + INTERVAL '7 days',
                        used INTEGER DEFAULT 0
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS session_tokens (
                        token TEXT PRIMARY KEY,
                        user_id INTEGER NOT NULL,
                        created_at TIMESTAMP DEFAULT NOW(),
                        expires_at TIMESTAMP DEFAULT NOW() + INTERVAL '30 days'
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS line_samples (
                        id SERIAL PRIMARY KEY,
                        store TEXT NOT NULL,
                        sample_text TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                """)

                # インデックス
                cur.execute("CREATE INDEX IF NOT EXISTS idx_visits_customer ON visits(customer_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_visits_store_date ON visits(store, date)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_customers_name ON customers(name)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_customers_store ON customers(primary_store)")

                # ── カラム追加（既存DBへの互換対応） ──
                cur.execute("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name='customers' AND table_schema='public'
                """)
                cust_cols = [row['column_name'] for row in cur.fetchall()]
                if 'top_change_bonus' not in cust_cols:
                    cur.execute("ALTER TABLE customers ADD COLUMN top_change_bonus INTEGER DEFAULT 0")

                cur.execute("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name='users' AND table_schema='public'
                """)
                user_cols = [row['column_name'] for row in cur.fetchall()]
                if 'email' not in user_cols:
                    cur.execute("ALTER TABLE users ADD COLUMN email TEXT DEFAULT ''")

    except Exception as e:
        import sys
        print(f"[migrate_db] warning: {e}", file=sys.stderr)


def get_all_customers(store=None) -> list:
    """顧客名一覧を取得（来店者名予測変換用・軽量クエリ）"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            if store:
                cur.execute(
                    "SELECT name FROM customers WHERE merged_into IS NULL AND primary_store=%s ORDER BY name",
                    (store,)
                )
            else:
                cur.execute(
                    "SELECT name FROM customers WHERE merged_into IS NULL ORDER BY name"
                )
            return cur.fetchall()


def get_customers(store=None, period=None, rank=None, search=None,
                  order_by="total_visits", limit=200):
    """顧客一覧を取得（フィルタ・ソート・前月比トレンド対応）"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            base = """
                SELECT c.*,
                    COUNT(DISTINCT v.date) as period_visits,
                    (SELECT COUNT(*) FROM visits
                     WHERE customer_id=c.id
                     AND LEFT(date,7)=TO_CHAR(NOW(),'YYYY-MM')) as visits_this_month,
                    (SELECT COUNT(*) FROM visits
                     WHERE customer_id=c.id
                     AND LEFT(date,7)=TO_CHAR(NOW() - INTERVAL '1 month','YYYY-MM')) as visits_last_month
                FROM customers c
                LEFT JOIN visits v ON c.id = v.customer_id
                    AND (%s IS NULL OR v.store = %s)
                    AND (%s IS NULL OR LEFT(v.date,7) = %s)
                WHERE c.merged_into IS NULL
            """
            params = [store, store, period, period]

            if store:
                base += " AND (c.primary_store = %s OR %s IS NULL)"
                params += [store, store]
            if rank:
                base += " AND c.rank = %s"
                params.append(rank)
            if search:
                base += " AND (c.name LIKE %s OR c.aliases LIKE %s)"
                params += [f"%{search}%", f"%{search}%"]

            # 期間指定あり → その期間の来店数順、なし → 全期間累計来店数順
            if period:
                base += " GROUP BY c.id ORDER BY period_visits DESC, c.total_visits DESC LIMIT %s"
            else:
                base += " GROUP BY c.id ORDER BY c.total_visits DESC LIMIT %s"
            params.append(limit)

            cur.execute(base, params)
            return [dict(r) for r in cur.fetchall()]


def get_customer(customer_id):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM customers WHERE id=%s", (customer_id,))
            row = cur.fetchone()
            return dict(row) if row else None


def get_visits(customer_id, limit=100):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM visits WHERE customer_id=%s
                ORDER BY date DESC LIMIT %s
            """, (customer_id, limit))
            return [dict(r) for r in cur.fetchall()]


def get_visit_stats(customer_id):
    """来店統計（曜日・月別・店舗別）"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT date, store FROM visits WHERE customer_id=%s ORDER BY date",
                (customer_id,)
            )
            visits = cur.fetchall()

    from collections import Counter
    import datetime
    dow_map = {0: '月', 1: '火', 2: '水', 3: '木', 4: '金', 5: '土', 6: '日'}
    dow_cnt = Counter()
    month_cnt = Counter()
    store_cnt = Counter()

    for v in visits:
        try:
            d = datetime.date.fromisoformat(v['date'])
            dow_cnt[dow_map[d.weekday()]] += 1
            month_cnt[v['date'][:7]] += 1
            store_cnt[v['store']] += 1
        except Exception:
            pass

    return {
        'by_dow': dict(sorted(dow_cnt.items(), key=lambda x: ['月', '火', '水', '木', '金', '土', '日'].index(x[0]))),
        'by_month': dict(sorted(month_cnt.items())[-6:]),
        'by_store': dict(store_cnt),
    }


def get_dashboard_stats(store=None, period=None):
    """ダッシュボード用集計"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            store_cond = "AND store=%s" if store else ""
            period_cond = "AND LEFT(date,7)=%s" if period else ""
            params = [p for p in [store, period] if p]

            cur.execute(f"""
                SELECT
                    SUM(new_count) as new_total,
                    SUM(repeat_unnamed_count) as repeat_b,
                    SUM(repeat_named_count) as repeat_a,
                    SUM(cafe_count) as cafe_total,
                    COUNT(DISTINCT date) as days
                FROM daily_summary
                WHERE 1=1 {store_cond} {period_cond}
            """, params)
            summary = cur.fetchone()

            rank_counts = {}
            store_filter = "AND primary_store=%s" if store else ""
            rp = [store] if store else []
            cur.execute(f"""
                SELECT rank, COUNT(*) as cnt FROM customers
                WHERE merged_into IS NULL {store_filter}
                GROUP BY rank
            """, rp)
            for row in cur.fetchall():
                rank_counts[row['rank']] = row['cnt']

            summary_dict = dict(summary) if summary else {}
            summary_dict = {k: (v if v is not None else 0) for k, v in summary_dict.items()}
            return {
                'summary': summary_dict,
                'rank_counts': rank_counts,
            }


def get_available_periods():
    """利用可能な年月リスト"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT LEFT(date,7) as ym
                FROM daily_summary ORDER BY ym DESC
            """)
            return [r['ym'] for r in cur.fetchall()]


def get_stores():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT store FROM daily_summary ORDER BY store")
            return [r['store'] for r in cur.fetchall()]


def get_all_stores_stats(period=None):
    """全店舗の集計を1クエリで取得（ダッシュボード高速化: N往復→1往復）"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            period_cond = "AND LEFT(date,7)=%s" if period else ""
            params = [period] if period else []
            cur.execute(f"""
                SELECT
                    store,
                    SUM(new_count)              AS new_total,
                    SUM(repeat_unnamed_count)   AS repeat_b,
                    SUM(repeat_named_count)     AS repeat_a,
                    SUM(cafe_count)             AS cafe_total,
                    COUNT(DISTINCT date)        AS days
                FROM daily_summary
                WHERE 1=1 {period_cond}
                GROUP BY store
                ORDER BY store
            """, params)
            rows = cur.fetchall()
    return {r['store']: {k: (v if v is not None else 0) for k, v in dict(r).items()}
            for r in rows}


def get_weekday_stats(store=None, period=None):
    """
    曜日別の平均来客数を返す
    戻り値: [{"weekday": 0..6(月〜日), "label": "月", "avg_new": x, "avg_repeat": x, "avg_total": x}, ...]
    """
    WEEKDAY_LABELS = ["月", "火", "水", "木", "金", "土", "日"]
    with get_conn() as conn:
        with conn.cursor() as cur:
            store_cond  = "AND store=%s"  if store  else ""
            period_cond = "AND LEFT(date,7)=%s" if period else ""
            params = [p for p in [store, period] if p]

            # DOW: 0=日曜, 1=月曜...6=土曜 (PostgreSQL仕様)
            # → 月曜始まりに変換: (DOW + 6) % 7  → 0=月,1=火,...,6=日
            cur.execute(f"""
                SELECT
                    (EXTRACT(DOW FROM date::date)::int + 6) %% 7 AS weekday_idx,
                    AVG(new_count)             AS avg_new,
                    AVG(repeat_unnamed_count)  AS avg_repeat,
                    AVG(new_count + repeat_unnamed_count + repeat_named_count) AS avg_total,
                    COUNT(*)                   AS days_count
                FROM daily_summary
                WHERE 1=1 {store_cond} {period_cond}
                GROUP BY weekday_idx
                ORDER BY weekday_idx
            """, params)
            rows = cur.fetchall()

    result = []
    data_map = {int(r["weekday_idx"]): r for r in rows}
    for i, label in enumerate(WEEKDAY_LABELS):
        r = data_map.get(i, {})
        result.append({
            "weekday": i,
            "label": label,
            "avg_new":    round(float(r.get("avg_new",    0) or 0), 1),
            "avg_repeat": round(float(r.get("avg_repeat", 0) or 0), 1),
            "avg_total":  round(float(r.get("avg_total",  0) or 0), 1),
            "days_count": int(r.get("days_count", 0) or 0),
        })
    return result


def set_rank(customer_id, rank, updated_by):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE customers SET rank=%s, updated_at=NOW() WHERE id=%s",
                (rank, customer_id)
            )


def bulk_set_rank(customer_ids: list, rank: str, updated_by: str):
    """複数顧客を1クエリで一括ランク更新"""
    if not customer_ids:
        return
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE customers SET rank=%s, updated_at=NOW() WHERE id = ANY(%s)",
                (rank, customer_ids)
            )


def merge_customers(from_id, into_id, merged_by):
    """2顧客をマージ（from → into）"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE visits SET customer_id=%s WHERE customer_id=%s",
                        (into_id, from_id))
            cur.execute(
                "UPDATE customers SET merged_into=%s WHERE id=%s",
                (into_id, from_id)
            )
            cur.execute("""
                INSERT INTO merge_log (merged_customer_id, into_customer_id, merged_by)
                VALUES (%s,%s,%s)
            """, (from_id, into_id, merged_by))
            cur.execute("""
                UPDATE customers SET
                    total_visits=(SELECT COUNT(*) FROM visits WHERE customer_id=%s),
                    updated_at=NOW()
                WHERE id=%s
            """, (into_id, into_id))


def unmerge_customers(from_id, merged_by):
    """マージを解除"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT merged_into FROM customers WHERE id=%s", (from_id,))
            row = cur.fetchone()
            if not row:
                return
            into_id = row['merged_into']
            cur.execute(
                "UPDATE customers SET merged_into=NULL WHERE id=%s", (from_id,)
            )
            cur.execute("""
                UPDATE visits SET customer_id=%s
                WHERE customer_id=%s AND date >= (
                    SELECT merged_at FROM merge_log
                    WHERE merged_customer_id=%s ORDER BY id DESC LIMIT 1
                )
            """, (from_id, into_id, from_id))


def add_note(customer_id, note, added_by):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT notes FROM customers WHERE id=%s", (customer_id,))
            existing = cur.fetchone()
            old = existing['notes'] if existing else ''
            from datetime import date
            new_note = f"[{date.today()} {added_by}] {note}"
            updated = (old + '\n' + new_note).strip()
            cur.execute(
                "UPDATE customers SET notes=%s, updated_at=NOW() WHERE id=%s",
                (updated, customer_id)
            )


def get_monthly_top_changes(customer_id, yearmonth=None):
    """今月のトップ替え回数（自動 + 手動調整）を返す"""
    if yearmonth is None:
        from datetime import date as _date
        yearmonth = _date.today().strftime('%Y-%m')
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) as cnt FROM visits
                WHERE customer_id=%s AND service_type='top_change'
                AND LEFT(date,7)=%s
            """, (customer_id, yearmonth))
            auto = cur.fetchone()['cnt']
            cur.execute("SELECT top_change_bonus FROM customers WHERE id=%s", (customer_id,))
            row = cur.fetchone()
            bonus = row['top_change_bonus'] if row and row['top_change_bonus'] else 0
            return auto + bonus, auto, bonus


def adjust_top_change_bonus(customer_id, delta):
    """トップ替え手動調整（+1 or -1）"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE customers SET top_change_bonus=top_change_bonus+%s, updated_at=NOW() WHERE id=%s",
                (delta, customer_id)
            )


def reset_top_change_bonus(customer_id):
    """月次リセット用"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE customers SET top_change_bonus=0, updated_at=NOW() WHERE id=%s",
                (customer_id,)
            )


def get_all_users():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, username, role, store, created_at FROM users ORDER BY role, username"
            )
            return [dict(r) for r in cur.fetchall()]


def add_user(username, password, role, store="", email=""):
    import hashlib
    pw_hash = hashlib.sha256(password.encode()).hexdigest()
    with get_conn() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    "INSERT INTO users (username, password_hash, role, store, email) VALUES (%s,%s,%s,%s,%s)",
                    (username, pw_hash, role, store, email)
                )
                return True
            except Exception:
                return False


def delete_user(user_id):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM users WHERE id=%s", (user_id,))


def update_user_password(username, new_password):
    import hashlib
    pw_hash = hashlib.sha256(new_password.encode()).hexdigest()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET password_hash=%s WHERE username=%s",
                (pw_hash, username)
            )


def verify_user(username, password):
    import hashlib
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE username=%s", (username,))
            row = cur.fetchone()
            if not row:
                return None
            pw_hash = hashlib.sha256(password.encode()).hexdigest()
            if row['password_hash'] == pw_hash:
                return dict(row)
            return None


# ─────────────────────────────────────────
# セッショントークン（ログイン記憶）
# ─────────────────────────────────────────
def create_session_token(user_id: int) -> str:
    """ログイン記憶用トークンを発行・DBに保存"""
    import secrets
    token = secrets.token_urlsafe(32)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM session_tokens WHERE expires_at < NOW()")
            cur.execute("""
                INSERT INTO session_tokens (token, user_id)
                VALUES (%s, %s)
                ON CONFLICT (token) DO UPDATE SET user_id=EXCLUDED.user_id
            """, (token, user_id))
    return token


def verify_session_token(token: str):
    """トークンからユーザー情報を返す（期限切れ・無効なら None）"""
    if not token:
        return None
    with get_conn() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute("""
                    SELECT u.* FROM users u
                    JOIN session_tokens st ON u.id = st.user_id
                    WHERE st.token=%s AND st.expires_at > NOW()
                """, (token,))
                row = cur.fetchone()
                return dict(row) if row else None
            except Exception:
                return None


def delete_session_token(token: str):
    """ログアウト時にトークン削除"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute("DELETE FROM session_tokens WHERE token=%s", (token,))
            except Exception:
                pass


# ─────────────────────────────────────────
# 招待トークン
# ─────────────────────────────────────────
def create_invitation(role: str, store: str = "") -> str:
    """招待トークンを発行してURLを返す"""
    import secrets
    token = secrets.token_urlsafe(24)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM invitations WHERE expires_at < NOW()")
            cur.execute(
                "INSERT INTO invitations (token, role, store) VALUES (%s,%s,%s)",
                (token, role, store)
            )
    return token


def get_invitation(token: str):
    """招待トークンを検証して {role, store} を返す。無効なら None"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM invitations
                WHERE token=%s AND used=0 AND expires_at > NOW()
            """, (token,))
            row = cur.fetchone()
            return dict(row) if row else None


def use_invitation(token: str):
    """招待トークンを使用済みにする"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE invitations SET used=1 WHERE token=%s", (token,))


def get_line_samples(store: str) -> list:
    """店舗の告知文サンプルをDBから取得（キャッシュ用）"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT sample_text FROM line_samples WHERE store=%s ORDER BY id",
                (store,)
            )
            rows = cur.fetchall()
            return [r["sample_text"] for r in rows]


def get_line_sample_stores() -> list:
    """告知文サンプルが存在する店舗一覧を返す"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT store FROM line_samples ORDER BY store")
            rows = cur.fetchall()
            return [r["store"] for r in rows]
