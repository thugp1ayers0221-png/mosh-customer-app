"""
MOSH シフト管理 DB操作

既存 mosh_db.py の get_conn() 接続プールを共用する。
スキーマ:
  staff_master   — スタッフマスター（雇用形態・時給/月給・週休パターン等）
  stores_master  — 店舗マスター（売上目標・目標人件比）
  shifts         — シフト（予定 = 拘束時間）
  time_logs      — 打刻ログ（実績）
  shift_requests — シフト希望（来月の入れる日/休み）
  payroll_lock   — 賃金画面用セカンドパスワード（1行・初期値: datakintaimosh）
"""
import os
import hashlib
from contextlib import contextmanager
from datetime import datetime, date, time, timedelta
from typing import Optional

import mosh_db as base_db


# ─────────────────────────────────────────
# 接続（既存プールを共用）
# ─────────────────────────────────────────

get_conn = base_db.get_conn


def _hash(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


# ─────────────────────────────────────────
# マイグレーション
# ─────────────────────────────────────────

def migrate_shift_db():
    """シフト管理関連のテーブル作成（IF NOT EXISTS で冪等）"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            # ── stores_master ──
            cur.execute("""
                CREATE TABLE IF NOT EXISTS stores_master (
                    code TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    monthly_target_sales INTEGER DEFAULT 0,
                    target_labor_cost_ratio NUMERIC DEFAULT 30.0,
                    open_time TIME DEFAULT '15:00',
                    close_time TIME DEFAULT '24:00',
                    is_franchise BOOLEAN DEFAULT false,
                    active BOOLEAN DEFAULT true,
                    sort_order INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)

            # ── staff_master ──
            cur.execute("""
                CREATE TABLE IF NOT EXISTS staff_master (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    display_name TEXT NOT NULL,
                    short_name TEXT DEFAULT '',
                    nickname TEXT DEFAULT '',
                    primary_store TEXT REFERENCES stores_master(code),
                    available_stores TEXT[] DEFAULT '{}',
                    position TEXT DEFAULT 'スタッフ',
                    employment_type TEXT DEFAULT 'アルバイト',
                    hourly_wage INTEGER DEFAULT 0,
                    base_monthly_salary INTEGER DEFAULT 0,
                    monthly_standard_hours INTEGER DEFAULT 176,
                    position_allowance_per_hour INTEGER DEFAULT 0,
                    weekly_off_days INTEGER DEFAULT 2,
                    shift_off_count INTEGER DEFAULT 0,
                    hours_per_day NUMERIC DEFAULT 8,
                    monthly_target_hours INTEGER DEFAULT 160,
                    flexible BOOLEAN DEFAULT false,
                    active BOOLEAN DEFAULT true,
                    joined_at DATE,
                    notes TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)

            # ── shifts ──
            cur.execute("""
                CREATE TABLE IF NOT EXISTS shifts (
                    id SERIAL PRIMARY KEY,
                    staff_id INTEGER NOT NULL REFERENCES staff_master(id) ON DELETE CASCADE,
                    store TEXT NOT NULL REFERENCES stores_master(code),
                    shift_date DATE NOT NULL,
                    start_time TIME NOT NULL,
                    end_time TIME NOT NULL,
                    crosses_midnight BOOLEAN DEFAULT false,
                    is_legal_holiday BOOLEAN DEFAULT false,
                    status TEXT DEFAULT 'planned',
                    note TEXT DEFAULT '',
                    created_by INTEGER REFERENCES users(id),
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(staff_id, shift_date, store, start_time)
                )
            """)

            # ── time_logs ──
            cur.execute("""
                CREATE TABLE IF NOT EXISTS time_logs (
                    id SERIAL PRIMARY KEY,
                    staff_id INTEGER NOT NULL REFERENCES staff_master(id) ON DELETE CASCADE,
                    shift_id INTEGER REFERENCES shifts(id) ON DELETE SET NULL,
                    store TEXT NOT NULL REFERENCES stores_master(code),
                    work_date DATE NOT NULL,
                    clock_in TIMESTAMPTZ,
                    clock_out TIMESTAMPTZ,
                    break_start TIMESTAMPTZ,
                    break_end TIMESTAMPTZ,
                    note TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)

            # ── shift_requests ──
            cur.execute("""
                CREATE TABLE IF NOT EXISTS shift_requests (
                    id SERIAL PRIMARY KEY,
                    staff_id INTEGER NOT NULL REFERENCES staff_master(id) ON DELETE CASCADE,
                    year_month TEXT NOT NULL,
                    request_date DATE NOT NULL,
                    request_type TEXT NOT NULL,
                    preferred_start TIME,
                    preferred_end TIME,
                    note TEXT DEFAULT '',
                    submitted_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(staff_id, request_date)
                )
            """)

            # ── payroll_lock（賃金画面用セカンドパスワード保持・1行のみ）──
            cur.execute("""
                CREATE TABLE IF NOT EXISTS payroll_lock (
                    id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
                    password_hash TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)

            # ── インデックス ──
            cur.execute("CREATE INDEX IF NOT EXISTS idx_shifts_date_store ON shifts(shift_date, store)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_shifts_staff_date ON shifts(staff_id, shift_date)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_timelogs_date_staff ON time_logs(work_date, staff_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_requests_yearmonth ON shift_requests(year_month)")

            # ── 既存テーブルのALTER（payroll_admin ロール対応）──
            try:
                cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS staff_id INTEGER REFERENCES staff_master(id)")
            except Exception:
                pass

    # 初期データ投入
    _seed_initial_data()


def _seed_initial_data():
    """店舗マスター + 賃金パスワード初期化（既存データがなければ）"""
    stores = [
        ("kashiwa",          "柏店",           2_600_000, 28.0, "15:00", "24:00", False, 1),
        ("masons",           "The Mason's",    1_180_000, 30.0, "15:00", "29:00", False, 2),  # 翌5時(=29:00)
        ("higashimurayama",  "東村山店",       1_000_000, 28.0, "15:00", "24:00", False, 3),
        ("nishifunabashi",   "西船橋店",       1_800_000, 28.0, "15:00", "24:00", False, 4),
        ("otaka",            "おおたかの森店", 0,         30.0, "15:00", "24:00", True,  5),
        ("matsudo",          "松戸店",         0,         30.0, "15:00", "24:00", True,  6),
    ]
    with get_conn() as conn:
        with conn.cursor() as cur:
            for code, name, target, ratio, ot, ct, fc, sort in stores:
                cur.execute("""
                    INSERT INTO stores_master
                        (code, display_name, monthly_target_sales, target_labor_cost_ratio,
                         open_time, close_time, is_franchise, sort_order)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (code) DO NOTHING
                """, (code, name, target, ratio, ot, ct, fc, sort))

            # 賃金パスワード初期値: datakintaimosh
            cur.execute("""
                INSERT INTO payroll_lock (id, password_hash)
                VALUES (1, %s)
                ON CONFLICT (id) DO NOTHING
            """, (_hash("datakintaimosh"),))


# ─────────────────────────────────────────
# 店舗マスター
# ─────────────────────────────────────────

def get_stores_master(active_only: bool = True) -> list:
    with get_conn() as conn:
        with conn.cursor() as cur:
            sql = "SELECT * FROM stores_master"
            if active_only:
                sql += " WHERE active = true"
            sql += " ORDER BY sort_order, code"
            cur.execute(sql)
            return [dict(r) for r in cur.fetchall()]


def update_store_master(code: str, **kwargs):
    if not kwargs:
        return
    sets = ", ".join(f"{k} = %s" for k in kwargs.keys())
    values = list(kwargs.values()) + [code]
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE stores_master SET {sets} WHERE code = %s", values)


# ─────────────────────────────────────────
# スタッフマスター
# ─────────────────────────────────────────

def get_all_staff(active_only: bool = True, store: Optional[str] = None) -> list:
    with get_conn() as conn:
        with conn.cursor() as cur:
            sql = """
                SELECT sm.*, s.display_name AS store_name
                FROM staff_master sm
                LEFT JOIN stores_master s ON sm.primary_store = s.code
                WHERE 1=1
            """
            params = []
            if active_only:
                sql += " AND sm.active = true"
            if store:
                sql += " AND (sm.primary_store = %s OR %s = ANY(sm.available_stores))"
                params.extend([store, store])
            sql += " ORDER BY sm.primary_store, sm.position, sm.display_name"
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]


def get_staff(staff_id: int) -> Optional[dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM staff_master WHERE id = %s", (staff_id,))
            r = cur.fetchone()
            return dict(r) if r else None


def get_staff_by_user_id(user_id: int) -> Optional[dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM staff_master WHERE user_id = %s", (user_id,))
            r = cur.fetchone()
            return dict(r) if r else None


def upsert_staff(**fields) -> int:
    """display_name を一意キーとして UPSERT。返り値は staff_id"""
    if "display_name" not in fields:
        raise ValueError("display_name is required")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM staff_master WHERE display_name = %s", (fields["display_name"],))
            existing = cur.fetchone()
            if existing:
                staff_id = existing["id"]
                sets = ", ".join(f"{k} = %s" for k in fields.keys())
                cur.execute(
                    f"UPDATE staff_master SET {sets}, updated_at = NOW() WHERE id = %s",
                    list(fields.values()) + [staff_id]
                )
                return staff_id
            cols = ", ".join(fields.keys())
            placeholders = ", ".join(["%s"] * len(fields))
            cur.execute(
                f"INSERT INTO staff_master ({cols}) VALUES ({placeholders}) RETURNING id",
                list(fields.values())
            )
            return cur.fetchone()["id"]


def update_staff(staff_id: int, **fields):
    if not fields:
        return
    sets = ", ".join(f"{k} = %s" for k in fields.keys())
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE staff_master SET {sets}, updated_at = NOW() WHERE id = %s",
                list(fields.values()) + [staff_id]
            )


def deactivate_staff(staff_id: int):
    update_staff(staff_id, active=False)


# ─────────────────────────────────────────
# シフト
# ─────────────────────────────────────────

def get_shifts_by_month(year_month: str, store: Optional[str] = None,
                          staff_id: Optional[int] = None) -> list:
    """year_month: 'YYYY-MM'"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            sql = """
                SELECT s.*, sm.display_name, sm.employment_type,
                       sm.hourly_wage, sm.base_monthly_salary,
                       sm.monthly_standard_hours, sm.position_allowance_per_hour,
                       sm.position
                FROM shifts s
                JOIN staff_master sm ON s.staff_id = sm.id
                WHERE TO_CHAR(s.shift_date, 'YYYY-MM') = %s
            """
            params = [year_month]
            if store:
                sql += " AND s.store = %s"
                params.append(store)
            if staff_id:
                sql += " AND s.staff_id = %s"
                params.append(staff_id)
            sql += " ORDER BY s.shift_date, s.start_time"
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]


def upsert_shift(staff_id: int, store: str, shift_date: date,
                  start_time: time, end_time: time,
                  crosses_midnight: bool = False, is_legal_holiday: bool = False,
                  note: str = "", created_by: Optional[int] = None) -> int:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO shifts (staff_id, store, shift_date, start_time, end_time,
                                    crosses_midnight, is_legal_holiday, note, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (staff_id, shift_date, store, start_time)
                DO UPDATE SET end_time = EXCLUDED.end_time,
                              crosses_midnight = EXCLUDED.crosses_midnight,
                              is_legal_holiday = EXCLUDED.is_legal_holiday,
                              note = EXCLUDED.note,
                              updated_at = NOW()
                RETURNING id
            """, (staff_id, store, shift_date, start_time, end_time,
                  crosses_midnight, is_legal_holiday, note, created_by))
            return cur.fetchone()["id"]


def delete_shift(shift_id: int):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM shifts WHERE id = %s", (shift_id,))


# ─────────────────────────────────────────
# 打刻ログ
# ─────────────────────────────────────────

def clock_in(staff_id: int, store: str, shift_id: Optional[int] = None,
              now: Optional[datetime] = None) -> int:
    now = now or datetime.now()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO time_logs (staff_id, store, shift_id, work_date, clock_in)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            """, (staff_id, store, shift_id, now.date(), now))
            return cur.fetchone()["id"]


def clock_out(time_log_id: int, now: Optional[datetime] = None):
    now = now or datetime.now()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE time_logs SET clock_out = %s, updated_at = NOW() WHERE id = %s",
                        (now, time_log_id))


def get_open_time_log(staff_id: int) -> Optional[dict]:
    """退勤打刻していない現在進行中の打刻ログを返す"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM time_logs
                WHERE staff_id = %s AND clock_out IS NULL
                ORDER BY clock_in DESC LIMIT 1
            """, (staff_id,))
            r = cur.fetchone()
            return dict(r) if r else None


def get_time_logs_by_month(year_month: str, store: Optional[str] = None,
                            staff_id: Optional[int] = None) -> list:
    with get_conn() as conn:
        with conn.cursor() as cur:
            sql = """
                SELECT tl.*, sm.display_name, sm.employment_type,
                       sm.hourly_wage, sm.base_monthly_salary,
                       sm.monthly_standard_hours, sm.position_allowance_per_hour
                FROM time_logs tl
                JOIN staff_master sm ON tl.staff_id = sm.id
                WHERE TO_CHAR(tl.work_date, 'YYYY-MM') = %s
            """
            params = [year_month]
            if store:
                sql += " AND tl.store = %s"
                params.append(store)
            if staff_id:
                sql += " AND tl.staff_id = %s"
                params.append(staff_id)
            sql += " ORDER BY tl.work_date, tl.clock_in"
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]


# ─────────────────────────────────────────
# シフト希望
# ─────────────────────────────────────────

def upsert_shift_request(staff_id: int, year_month: str, request_date: date,
                          request_type: str, preferred_start: Optional[time] = None,
                          preferred_end: Optional[time] = None, note: str = ""):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO shift_requests
                    (staff_id, year_month, request_date, request_type, preferred_start, preferred_end, note)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (staff_id, request_date)
                DO UPDATE SET request_type = EXCLUDED.request_type,
                              preferred_start = EXCLUDED.preferred_start,
                              preferred_end = EXCLUDED.preferred_end,
                              note = EXCLUDED.note,
                              submitted_at = NOW()
            """, (staff_id, year_month, request_date, request_type,
                  preferred_start, preferred_end, note))


def get_shift_requests(year_month: str, staff_id: Optional[int] = None) -> list:
    with get_conn() as conn:
        with conn.cursor() as cur:
            sql = """
                SELECT r.*, sm.display_name, sm.primary_store
                FROM shift_requests r
                JOIN staff_master sm ON r.staff_id = sm.id
                WHERE r.year_month = %s
            """
            params = [year_month]
            if staff_id:
                sql += " AND r.staff_id = %s"
                params.append(staff_id)
            sql += " ORDER BY sm.primary_store, sm.display_name, r.request_date"
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]


# ─────────────────────────────────────────
# 賃金画面セカンドパスワード
# ─────────────────────────────────────────

def verify_payroll_password(password: str) -> bool:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT password_hash FROM payroll_lock WHERE id = 1")
            r = cur.fetchone()
            if not r:
                return False
            return r["password_hash"] == _hash(password)


def update_payroll_password(new_password: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE payroll_lock SET password_hash = %s, updated_at = NOW() WHERE id = 1
            """, (_hash(new_password),))


# ─────────────────────────────────────────
# 売上連動（既存 daily_summary は来店人数のみ。売上連動は将来拡張）
# ─────────────────────────────────────────

def get_monthly_sales(year_month: str, store: str) -> Optional[int]:
    """既存 mosh_sync.py が出力する月次売上を取得（将来拡張）"""
    # TODO: Obsidian CSV or daily_summary に売上カラム追加後に実装
    return None
