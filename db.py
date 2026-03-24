"""DB操作ヘルパー"""
import sqlite3
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path(__file__).parent / "mosh_customers.db"

@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def migrate_db():
    """DBスキーマの自動マイグレーション（カラム追加など）"""
    with get_conn() as conn:
        # customers テーブルの既存カラムを確認
        cols = [row[1] for row in conn.execute("PRAGMA table_info(customers)")]
        # top_change_bonus カラムが無ければ追加
        if "top_change_bonus" not in cols:
            conn.execute("ALTER TABLE customers ADD COLUMN top_change_bonus INTEGER DEFAULT 0")
        # users テーブルが無ければ作成
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'staff',
                store TEXT DEFAULT '',
                email TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        # users テーブルに email カラムが無ければ追加
        user_cols = [row[1] for row in conn.execute("PRAGMA table_info(users)")]
        if "email" not in user_cols:
            conn.execute("ALTER TABLE users ADD COLUMN email TEXT DEFAULT ''")

def get_customers(store=None, period=None, rank=None, search=None,
                  order_by="total_visits", limit=200):
    """顧客一覧を取得（フィルタ・ソート・前月比トレンド対応）"""
    with get_conn() as conn:
        base = """
            SELECT c.*,
                COUNT(DISTINCT v.date) as period_visits,
                (SELECT COUNT(*) FROM visits
                 WHERE customer_id=c.id
                 AND substr(date,1,7)=strftime('%Y-%m','now')) as visits_this_month,
                (SELECT COUNT(*) FROM visits
                 WHERE customer_id=c.id
                 AND substr(date,1,7)=strftime('%Y-%m','now','-1 month')) as visits_last_month
            FROM customers c
            LEFT JOIN visits v ON c.id = v.customer_id
                AND (? IS NULL OR v.store = ?)
                AND (? IS NULL OR substr(v.date,1,7) = ?)
            WHERE c.merged_into IS NULL
        """
        params = [store, store, period, period]

        if store:
            base += " AND (c.primary_store = ? OR ? IS NULL)"
            params += [store, store]
        if rank:
            base += " AND c.rank = ?"
            params.append(rank)
        if search:
            base += " AND (c.name LIKE ? OR c.aliases LIKE ?)"
            params += [f"%{search}%", f"%{search}%"]

        base += f" GROUP BY c.id ORDER BY period_visits DESC, c.total_visits DESC LIMIT ?"
        params.append(limit)

        return [dict(r) for r in conn.execute(base, params).fetchall()]

def get_customer(customer_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM customers WHERE id=?", (customer_id,)
        ).fetchone()
        return dict(row) if row else None

def get_visits(customer_id, limit=100):
    with get_conn() as conn:
        return [dict(r) for r in conn.execute("""
            SELECT * FROM visits WHERE customer_id=?
            ORDER BY date DESC LIMIT ?
        """, (customer_id, limit)).fetchall()]

def get_visit_stats(customer_id):
    """来店統計（曜日・月別・店舗別）"""
    with get_conn() as conn:
        visits = conn.execute(
            "SELECT date, store FROM visits WHERE customer_id=? ORDER BY date",
            (customer_id,)
        ).fetchall()

        from collections import Counter
        import datetime
        dow_map = {0:'月',1:'火',2:'水',3:'木',4:'金',5:'土',6:'日'}
        dow_cnt = Counter()
        month_cnt = Counter()
        store_cnt = Counter()

        for v in visits:
            try:
                d = datetime.date.fromisoformat(v['date'])
                dow_cnt[dow_map[d.weekday()]] += 1
                month_cnt[v['date'][:7]] += 1
                store_cnt[v['store']] += 1
            except:
                pass

        return {
            'by_dow': dict(sorted(dow_cnt.items(), key=lambda x: ['月','火','水','木','金','土','日'].index(x[0]))),
            'by_month': dict(sorted(month_cnt.items())[-6:]),
            'by_store': dict(store_cnt),
        }

def get_dashboard_stats(store=None, period=None):
    """ダッシュボード用集計"""
    with get_conn() as conn:
        store_cond = "AND store=?" if store else ""
        period_cond = "AND substr(date,1,7)=?" if period else ""
        params = [p for p in [store, period] if p]

        # 今期の新規・リピーター
        summary = conn.execute(f"""
            SELECT
                SUM(new_count) as new_total,
                SUM(repeat_unnamed_count) as repeat_b,
                SUM(repeat_named_count) as repeat_a,
                SUM(cafe_count) as cafe_total,
                COUNT(DISTINCT date) as days
            FROM daily_summary
            WHERE 1=1 {store_cond} {period_cond}
        """, params).fetchone()

        # ランク別顧客数
        rank_counts = {}
        store_filter = "AND primary_store=?" if store else ""
        rp = [store] if store else []
        for row in conn.execute(f"""
            SELECT rank, COUNT(*) as cnt FROM customers
            WHERE merged_into IS NULL {store_filter}
            GROUP BY rank
        """, rp).fetchall():
            rank_counts[row['rank']] = row['cnt']

        # None値を0に変換（SUM()が空の場合NULLになる）
        summary_dict = dict(summary) if summary else {}
        summary_dict = {k: (v if v is not None else 0) for k, v in summary_dict.items()}
        return {
            'summary': summary_dict,
            'rank_counts': rank_counts,
        }

def get_available_periods():
    """利用可能な年月リスト"""
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT DISTINCT substr(date,1,7) as ym
            FROM daily_summary ORDER BY ym DESC
        """).fetchall()
        return [r['ym'] for r in rows]

def get_stores():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT store FROM daily_summary ORDER BY store"
        ).fetchall()
        return [r['store'] for r in rows]

def set_rank(customer_id, rank, updated_by):
    with get_conn() as conn:
        conn.execute(
            "UPDATE customers SET rank=?, updated_at=datetime('now') WHERE id=?",
            (rank, customer_id)
        )

def merge_customers(from_id, into_id, merged_by):
    """2顧客をマージ（from → into）"""
    with get_conn() as conn:
        conn.execute("UPDATE visits SET customer_id=? WHERE customer_id=?",
                    (into_id, from_id))
        conn.execute(
            "UPDATE customers SET merged_into=? WHERE id=?",
            (into_id, from_id)
        )
        conn.execute("""
            INSERT INTO merge_log (merged_customer_id, into_customer_id, merged_by)
            VALUES (?,?,?)
        """, (from_id, into_id, merged_by))
        # into の集計を更新
        conn.execute("""
            UPDATE customers SET
                total_visits=(SELECT COUNT(*) FROM visits WHERE customer_id=?),
                updated_at=datetime('now')
            WHERE id=?
        """, (into_id, into_id))

def unmerge_customers(from_id, merged_by):
    """マージを解除"""
    with get_conn() as conn:
        into_id = conn.execute(
            "SELECT merged_into FROM customers WHERE id=?", (from_id,)
        ).fetchone()
        if not into_id:
            return
        conn.execute(
            "UPDATE customers SET merged_into=NULL WHERE id=?", (from_id,)
        )
        # visitを元に戻す（merge_logの記録から）
        conn.execute("""
            UPDATE visits SET customer_id=?
            WHERE customer_id=? AND date >= (
                SELECT merged_at FROM merge_log
                WHERE merged_customer_id=? ORDER BY id DESC LIMIT 1
            )
        """, (from_id, into_id[0], from_id))

def add_note(customer_id, note, added_by):
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT notes FROM customers WHERE id=?", (customer_id,)
        ).fetchone()
        old = existing['notes'] if existing else ''
        from datetime import date
        new_note = f"[{date.today()} {added_by}] {note}"
        updated = (old + '\n' + new_note).strip()
        conn.execute(
            "UPDATE customers SET notes=?, updated_at=datetime('now') WHERE id=?",
            (updated, customer_id)
        )

def get_monthly_top_changes(customer_id, yearmonth=None):
    """今月のトップ替え回数（自動 + 手動調整）を返す"""
    if yearmonth is None:
        from datetime import date as _date
        yearmonth = _date.today().strftime('%Y-%m')
    with get_conn() as conn:
        auto = conn.execute("""
            SELECT COUNT(*) FROM visits
            WHERE customer_id=? AND service_type='top_change'
            AND substr(date,1,7)=?
        """, (customer_id, yearmonth)).fetchone()[0]
        row = conn.execute(
            "SELECT top_change_bonus FROM customers WHERE id=?", (customer_id,)
        ).fetchone()
        bonus = row[0] if row and row[0] else 0
        return auto + bonus, auto, bonus

def adjust_top_change_bonus(customer_id, delta):
    """トップ替え手動調整（+1 or -1）"""
    with get_conn() as conn:
        conn.execute(
            "UPDATE customers SET top_change_bonus=top_change_bonus+?, updated_at=datetime('now') WHERE id=?",
            (delta, customer_id)
        )

def reset_top_change_bonus(customer_id):
    """月次リセット用"""
    with get_conn() as conn:
        conn.execute(
            "UPDATE customers SET top_change_bonus=0, updated_at=datetime('now') WHERE id=?",
            (customer_id,)
        )

def get_all_users():
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT id, username, role, store, created_at FROM users ORDER BY role, username"
        ).fetchall()]

def add_user(username, password, role, store="", email=""):
    import hashlib
    pw_hash = hashlib.sha256(password.encode()).hexdigest()
    with get_conn() as conn:
        try:
            conn.execute(
                "INSERT INTO users (username, password_hash, role, store, email) VALUES (?,?,?,?,?)",
                (username, pw_hash, role, store, email)
            )
            return True
        except Exception:
            return False

def delete_user(user_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM users WHERE id=?", (user_id,))

def update_user_password(username, new_password):
    import hashlib
    pw_hash = hashlib.sha256(new_password.encode()).hexdigest()
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET password_hash=? WHERE username=?",
            (pw_hash, username)
        )

def verify_user(username, password):
    import hashlib
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username=?", (username,)
        ).fetchone()
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
        # session_tokens テーブルが無ければ作成
        conn.execute("""
            CREATE TABLE IF NOT EXISTS session_tokens (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                expires_at TEXT DEFAULT (datetime('now','+30 days'))
            )
        """)
        # 古いトークン削除（30日以上）
        conn.execute("DELETE FROM session_tokens WHERE expires_at < datetime('now')")
        conn.execute(
            "INSERT OR REPLACE INTO session_tokens (token, user_id) VALUES (?,?)",
            (token, user_id)
        )
    return token

def verify_session_token(token: str):
    """トークンからユーザー情報を返す（期限切れ・無効なら None）"""
    if not token:
        return None
    with get_conn() as conn:
        try:
            row = conn.execute("""
                SELECT u.* FROM users u
                JOIN session_tokens st ON u.id = st.user_id
                WHERE st.token=? AND st.expires_at > datetime('now')
            """, (token,)).fetchone()
            return dict(row) if row else None
        except Exception:
            return None

def delete_session_token(token: str):
    """ログアウト時にトークン削除"""
    with get_conn() as conn:
        try:
            conn.execute("DELETE FROM session_tokens WHERE token=?", (token,))
        except Exception:
            pass
