"""
スタッフマスター 一括投入スクリプト

Obsidian `MOSH/03_スタッフ/00_まとめ/スタッフ一覧.md`（2026-05-22更新版）から
staff_master + users（認証）を一括登録する。

使い方:
    DATABASE_URL=... python3 staff_seed.py

冪等: 既存スタッフは UPSERT で更新（display_name キー）。
時給/月給/役職給は初期値0。経営陣4名（清本・田中・美希・カナ）のみ管理画面から設定可能。
"""
import sys
import unicodedata
import shift_db
import mosh_db


# ─────────────────────────────────────────
# スタッフ定義（Obsidian 2026-05-22版から手動転記）
# ─────────────────────────────────────────
#
# フィールド:
#   display_name     : 本名（DBの一意キー）
#   nickname         : 通称（シフト表示用）
#   primary_store    : 主所属店舗コード
#   available_stores : 兼務店舗コード一覧
#   position         : 役職（店長/副店長/店長代理/スタッフ/研修生/マネージャー/共同経営/代表）
#   employment_type  : "社員"/"アルバイト"/"業務委託"
#   username         : 認証ユーザー名（None → 後で自動生成）
#   payroll_admin    : 賃金設定権限（経営陣4名のみTrue）
#
# 賃金関連（hourly_wage / base_monthly_salary / position_allowance_per_hour）は
# すべて初期0。清本さんが管理画面から個別設定する。

STAFF_DATA = [
    # ── 経営・本部 ──
    # 清本・田中は店舗業務に入らないため include_in_shift=False
    {"display_name": "清本勇樹",   "last_name": "清本", "first_name": "勇樹",   "nickname": "清本／kii",
     "primary_store": "kashiwa",
     "available_stores": ["kashiwa","masons","higashimurayama","nishifunabashi","otaka","matsudo"],
     "position": "代表", "employment_type": "社員", "username": "kii001", "is_owner": True, "payroll_admin": True,
     "include_in_shift": False},
    {"display_name": "田中たくみ", "last_name": "田中", "first_name": "たくみ", "nickname": "田中",
     "primary_store": "kashiwa",
     "available_stores": ["kashiwa","masons","higashimurayama","nishifunabashi","otaka","matsudo"],
     "position": "共同経営", "employment_type": "社員", "username": "tanaka001", "payroll_admin": True,
     "include_in_shift": False},
    {"display_name": "齊藤美希",   "last_name": "齊藤", "first_name": "美希",   "nickname": "みき",
     "primary_store": "kashiwa",
     "available_stores": ["kashiwa","masons","higashimurayama","nishifunabashi","otaka"],
     "position": "マネージャー", "employment_type": "社員", "username": "miki001", "payroll_admin": True},
    {"display_name": "箕輪加奈",   "last_name": "箕輪", "first_name": "加奈",   "nickname": "カナ",
     "primary_store": "nishifunabashi",
     "available_stores": ["nishifunabashi","otaka"],
     "position": "マネージャー", "employment_type": "社員", "username": "kana001", "payroll_admin": True,
     "monthly_target_hours": 140},

    # ── 店長（4名） ──
    {"display_name": "池田愛美",   "last_name": "池田", "first_name": "愛美",   "nickname": "あみ",
     "primary_store": "kashiwa",
     "position": "店長", "employment_type": "社員", "username": "ami_kashiwa", "is_manager": True},
    {"display_name": "花田竜盛",   "last_name": "花田", "first_name": "竜盛",   "nickname": "りゅうせい",
     "primary_store": "masons",
     "position": "店長", "employment_type": "社員", "username": "hanada_masons", "is_manager": True},
    {"display_name": "川床尚平",   "last_name": "川床", "first_name": "尚平",   "nickname": "しょうへい",
     "primary_store": "higashimurayama",
     "position": "店長", "employment_type": "社員", "username": "shohei_higashi", "is_manager": True},
    {"display_name": "岩崎俊輔",   "last_name": "岩崎", "first_name": "俊輔",   "nickname": "俊介",
     "primary_store": "matsudo",
     "available_stores": ["matsudo","kashiwa","otaka"],
     "position": "店長", "employment_type": "社員", "username": "shunsuke_matsudo", "is_manager": True},

    # ── 副店長・店長代理 ──
    {"display_name": "増岡伸哉",   "last_name": "増岡", "first_name": "伸哉",   "nickname": "しんや",
     "primary_store": "nishifunabashi",
     "position": "副店長", "employment_type": "社員", "username": "shinya_nishi"},
    {"display_name": "齋藤龍星",   "last_name": "齋藤", "first_name": "龍星",   "nickname": "りゅうせい（おおたか）",
     "primary_store": "otaka",
     "position": "店長代理（共同）", "employment_type": "社員", "username": "ryusei_otaka"},
    {"display_name": "松園泰伽",   "last_name": "松園", "first_name": "泰伽",   "nickname": "ぞの",
     "primary_store": "otaka",
     "position": "店長代理（共同）", "employment_type": "アルバイト", "username": "zono_otaka"},

    # ── 柏店 ──
    {"display_name": "鈴木諒",     "last_name": "鈴木", "first_name": "諒",     "nickname": "まこと",
     "primary_store": "kashiwa",
     "available_stores": ["kashiwa","masons"],
     "position": "スタッフ", "employment_type": "社員", "username": "makoto_kashiwa"},
    {"display_name": "加倉井拓仁", "last_name": "加倉井", "first_name": "拓仁", "nickname": "パプリカ",
     "primary_store": "kashiwa",
     "position": "研修生", "employment_type": "アルバイト", "username": "paprika_kashiwa"},
    {"display_name": "渡辺紗里奈", "last_name": "渡辺", "first_name": "紗里奈", "nickname": "サリー",
     "primary_store": "kashiwa",
     "available_stores": ["kashiwa","masons"],
     "position": "スタッフ", "employment_type": "アルバイト", "username": "sally_kashiwa"},
    {"display_name": "中野空",     "last_name": "中野", "first_name": "空",     "nickname": "そら",
     "primary_store": "kashiwa",
     "position": "スタッフ", "employment_type": "アルバイト", "username": "sora_kashiwa"},

    # ── The Mason's ──
    {"display_name": "吉野將吾",   "last_name": "吉野", "first_name": "將吾",   "nickname": "しょうご",
     "primary_store": "masons",
     "position": "スタッフ", "employment_type": "アルバイト", "username": "shogo_masons"},

    # ── 東村山店 ──
    {"display_name": "生駒千晴",   "last_name": "生駒", "first_name": "千晴",   "nickname": "いこまちゃん",
     "primary_store": "higashimurayama",
     "position": "スタッフ", "employment_type": "アルバイト", "username": "ikoma_higashi"},
    {"display_name": "江原はるか", "last_name": "江原", "first_name": "はるか", "nickname": "はる",
     "primary_store": "higashimurayama",
     "position": "スタッフ", "employment_type": "アルバイト", "username": "haru_higashi"},

    # ── おおたかの森店 ──
    {"display_name": "坂本寛稀",   "last_name": "坂本", "first_name": "寛稀",   "nickname": "もっさん",
     "primary_store": "otaka",
     "available_stores": ["otaka","kashiwa","nishifunabashi"],
     "position": "スタッフ", "employment_type": "アルバイト", "username": "mossan_otaka"},
    {"display_name": "市田美優",   "last_name": "市田", "first_name": "美優",   "nickname": "みゆ",
     "primary_store": "otaka",
     "position": "スタッフ", "employment_type": "アルバイト", "username": "miyu_otaka"},
    {"display_name": "原田樹希",   "last_name": "原田", "first_name": "樹希",   "nickname": "いつき",
     "primary_store": "otaka",
     "position": "スタッフ", "employment_type": "アルバイト", "username": "itsuki_otaka"},
    {"display_name": "渡辺瑠璃子", "last_name": "渡辺", "first_name": "瑠璃子", "nickname": "なつめ",
     "primary_store": "otaka",
     "position": "スタッフ", "employment_type": "アルバイト", "username": "natsume_otaka"},
    {"display_name": "福井環太",   "last_name": "福井", "first_name": "環太",   "nickname": "勘太郎",
     "primary_store": "otaka",
     "position": "研修生", "employment_type": "アルバイト", "username": "kanta_otaka"},
    {"display_name": "淡路祐弘",   "last_name": "淡路", "first_name": "祐弘",   "nickname": "マスク",
     "primary_store": "otaka",
     "position": "研修生", "employment_type": "アルバイト", "username": "mask_otaka"},
    {"display_name": "足立大河",   "last_name": "足立", "first_name": "大河",   "nickname": "大河",
     "primary_store": "otaka",
     "position": "FCオーナー", "employment_type": "業務委託", "username": "adachi_otaka",
     "include_in_shift": False},

    # ── 西船橋店 ──
    {"display_name": "大地七海",   "last_name": "大地", "first_name": "七海",   "nickname": "ななみん",
     "primary_store": "nishifunabashi",
     "position": "スタッフ", "employment_type": "アルバイト", "username": "nanami_nishi"},
    {"display_name": "宮本咲",     "last_name": "宮本", "first_name": "咲",     "nickname": "さき",
     "primary_store": "nishifunabashi",
     "position": "スタッフ", "employment_type": "アルバイト", "username": "saki_nishi"},
    {"display_name": "山河萌音",   "last_name": "山河", "first_name": "萌音",   "nickname": "もね",
     "primary_store": "nishifunabashi",
     "position": "スタッフ", "employment_type": "アルバイト", "username": "mone_nishi"},
    {"display_name": "高瀬",       "last_name": "高瀬", "first_name": "",       "nickname": "高瀬",
     "primary_store": "nishifunabashi",
     "position": "事務", "employment_type": "業務委託", "username": "takase_nishi"},

    # ── 本部・不在席 ──
    # ※「新畑加奈」は離婚により「箕輪加奈」と同一人物に統合済み（2026-05-29）
]

DEFAULT_PASSWORD = "MOSH4148"


def seed(log=None):
    """全スタッフを staff_master + users に投入

    Args:
        log: ログ出力関数（None なら print）。Streamlit UI から呼ぶ場合は st.write を渡す。
    Returns:
        dict {"staff_count": int, "user_created": int, "credentials": list[dict]}
    """
    _log = log or print
    _log("=" * 60)
    _log("MOSH スタッフマスター一括投入")
    _log("=" * 60)

    # まずスキーマ確認
    mosh_db.migrate_db()
    shift_db.migrate_shift_db()

    created = 0
    user_created = 0
    credentials = []

    for d_orig in STAFF_DATA:
        d = dict(d_orig)  # 破壊しないようコピー
        is_owner = d.pop("is_owner", False)
        is_manager = d.pop("is_manager", False)
        payroll_admin = d.pop("payroll_admin", False)
        username = d.pop("username")

        # 1. users テーブルに認証アカウント作成（既存なら何もしない）
        existing_users = mosh_db.get_all_users()
        user_exists = any(u["username"] == username for u in existing_users)

        if not user_exists:
            role = "owner" if is_owner else ("manager" if is_manager else "staff")
            mosh_db.add_user(
                username=username,
                password=DEFAULT_PASSWORD,
                role=role,
                store=_role_store(d, role),
            )
            user_created += 1
            _log(f"  👤 認証作成: {username} ({role})")

        # 2. staff_master に登録（display_name で UPSERT）
        fields = {
            "display_name": d["display_name"],
            "last_name": d.get("last_name", ""),
            "first_name": d.get("first_name", ""),
            "nickname": d.get("nickname", ""),
            "short_name": d.get("nickname", d["display_name"])[:6],
            "primary_store": d["primary_store"],
            "available_stores": d.get("available_stores", [d["primary_store"]]),
            "position": d.get("position", "スタッフ"),
            "employment_type": d.get("employment_type", "アルバイト"),
            "monthly_target_hours": d.get("monthly_target_hours", 160),
            "include_in_shift": d.get("include_in_shift", True),
            "active": True,
        }
        staff_id = shift_db.upsert_staff(**fields)
        _link_user_staff(username, staff_id)

        if payroll_admin and not is_owner:
            _set_role(username, "payroll_admin")

        credentials.append({
            "display_name": d["display_name"],
            "username": username,
            "password": DEFAULT_PASSWORD,
            "role": "owner" if is_owner else ("payroll_admin" if payroll_admin else ("manager" if is_manager else "staff")),
            "store": d["primary_store"],
        })
        created += 1

    _log(f"\n✅ 投入完了: スタッフ {created}名 / 新規ユーザー {user_created}名")
    _log(f"\n📝 初期パスワード: {DEFAULT_PASSWORD}（各自変更推奨）")
    _log(f"📝 賃金画面パスワード: datakintaimosh（経営陣4名で共有）")

    return {"staff_count": created, "user_created": user_created, "credentials": credentials}


def _role_store(d: dict, role: str) -> str:
    """managerユーザーの担当店舗をDBに保存（既存setup_users.py互換）"""
    if role == "manager":
        return d["primary_store"]
    return ""


def _link_user_staff(username: str, staff_id: int):
    """users.staff_id カラムに staff_id を紐付け"""
    with shift_db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET staff_id = %s WHERE username = %s",
                        (staff_id, username))


def _set_role(username: str, role: str):
    with shift_db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET role = %s WHERE username = %s", (role, username))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--dry-run":
        print(f"投入対象: {len(STAFF_DATA)} 名")
        for d in STAFF_DATA:
            print(f"  {d['primary_store']:<18} {d.get('position','スタッフ'):<14} {d['display_name']} ({d.get('employment_type','-')})")
        sys.exit(0)
    seed()
