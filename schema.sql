-- MOSH 顧客管理DB スキーマ

CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,                          -- 正規化済み表示名
    aliases TEXT DEFAULT '',                     -- カンマ区切り別名
    primary_store TEXT DEFAULT '',               -- 主利用店舗
    rank TEXT DEFAULT 'A',                       -- S/A/B/C
    first_visit_date TEXT,
    last_visit_date TEXT,
    total_visits INTEGER DEFAULT 0,
    is_member INTEGER DEFAULT 0,                 -- メイソンズ会員のみ使用
    notes TEXT DEFAULT '',                       -- 日報メモ集約
    cross_store_flag INTEGER DEFAULT 0,          -- 他店舗に同名あり
    merged_into INTEGER DEFAULT NULL,            -- 同一人物マージ先ID
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS visits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER,                         -- NULLの場合は名無しリピーター
    store TEXT NOT NULL,
    date TEXT NOT NULL,
    service_type TEXT DEFAULT 'normal',          -- normal/top_change/cafe
    memo TEXT DEFAULT '',
    source_file TEXT DEFAULT '',
    FOREIGN KEY (customer_id) REFERENCES customers(id)
);

-- 名無し来店集計（B/Cランク用）
CREATE TABLE IF NOT EXISTS daily_summary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    store TEXT NOT NULL,
    date TEXT NOT NULL,
    new_count INTEGER DEFAULT 0,                 -- C: 新規
    repeat_unnamed_count INTEGER DEFAULT 0,      -- B: 名前不明リピーター
    repeat_named_count INTEGER DEFAULT 0,        -- A+S: 名前付き
    cafe_count INTEGER DEFAULT 0,
    source_file TEXT DEFAULT '',
    UNIQUE(store, date)
);

-- 権限管理
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL,                          -- owner/manager/staff
    store TEXT DEFAULT '',                       -- 担当店舗（manager用）
    created_at TEXT DEFAULT (datetime('now'))
);

-- 同一人物マージ履歴
CREATE TABLE IF NOT EXISTS merge_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    merged_customer_id INTEGER,
    into_customer_id INTEGER,
    merged_by TEXT,
    merged_at TEXT DEFAULT (datetime('now'))
);

-- インデックス
CREATE INDEX IF NOT EXISTS idx_visits_customer ON visits(customer_id);
CREATE INDEX IF NOT EXISTS idx_visits_store_date ON visits(store, date);
CREATE INDEX IF NOT EXISTS idx_customers_name ON customers(name);
CREATE INDEX IF NOT EXISTS idx_customers_store ON customers(primary_store);
