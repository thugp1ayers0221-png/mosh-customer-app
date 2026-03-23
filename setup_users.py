"""初期ユーザー設定"""
import sqlite3, hashlib
from pathlib import Path

DB_PATH = Path(__file__).parent / "mosh_customers.db"

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

USERS = [
    # username,       password,   role,      store
    ("kii001",       "MOSH4148", "owner",   ""),
    ("ami_kashiwa",  "MOSH4148", "manager", "柏"),
    ("zona_otaka",   "MOSH4148", "manager", "おおたかの森"),
    ("shohei_higashi","MOSH4148","manager", "東村山"),
    ("kana_nishi",   "MOSH4148", "manager", "西船橋"),
    ("ryusei_masons","MOSH4148", "manager", "メイソンズ"),
    ("staff",        "MOSH4148", "staff",   ""),
]

def setup():
    conn = sqlite3.connect(DB_PATH)
    for username, pw, role, store in USERS:
        try:
            conn.execute("""
                INSERT OR REPLACE INTO users (username, password_hash, role, store)
                VALUES (?, ?, ?, ?)
            """, (username, hash_pw(pw), role, store))
            print(f"✅ {username} ({role})")
        except Exception as e:
            print(f"⚠️ {username}: {e}")
    conn.commit()
    conn.close()
    print("\n初期パスワード: MOSH4148（各自変更推奨）")

if __name__ == "__main__":
    setup()
