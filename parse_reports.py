"""
日報パーサー: Obsidianの日報MDから顧客名・来店情報を抽出してSQLiteに保存
"""
import re
import sqlite3
import hashlib
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent / "mosh_customers.db"
REPORTS_BASE = Path("/Users/kiyomotoyuuki/Library/Mobile Documents/com~apple~CloudDocs/Obsidian/Second Brain/MOSH/07_議事録・記録/日報")

STORES = ["柏", "東村山", "おおたかの森", "メイソンズ", "西船橋"]

# 来店者名リストから除外するキーワード（スタッフ名・システム文言・非個人名）
EXCLUDE_PATTERNS = [
    r'^【', r'^（', r'^\[', r'終業報告', r'連絡事項', r'レジ締め',
    r'^新規', r'^リピ', r'^計', r'^カフェ', r'^S$', r'^B$', r'^C$',
    r'お願い', r'補充', r'掃除', r'報告', r'確認', r'問い合わせ',
    # 人数・性別表記（個人名ではない）
    r'\d+名', r'\d+人', r'[男女]性', r'男の子', r'女の子', r'^男$', r'^女$',
    r'^一見', r'^初見', r'リピーター$', r'^グループ', r'^お連れ',
    # 助詞・接続詞を含む文章（説明文・感想文）
    r'[をへ]', r'ました$', r'ます$', r'です$', r'てる$', r'てた$',
    r'見て', r'来て', r'持って', r'持ち', r'なって', r'して',
    # 説明的なキーワード
    r'おすすめ', r'興味', r'ミックス', r'フレーバー', r'シーシャ',
    r'来店', r'予約', r'注文', r'インスタ', r'Twitter', r'X$', r'TikTok',
    r'SNS', r'口コミ', r'クーポン', r'初回',
]

# 個人名として許容する最大文字数（敬称込みで）
MAX_NAME_LEN = 12

# サービスタイプ判定
TOP_CHANGE_PATTERN = re.compile(r'トップ替え|トップ変え|topチェンジ', re.IGNORECASE)
CAFE_PATTERN = re.compile(r'カフェ|cafe', re.IGNORECASE)
MEMBER_PATTERN = re.compile(r'会員登録|メンバー登録|member', re.IGNORECASE)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    with open(Path(__file__).parent / "schema.sql") as f:
        conn.executescript(f.read())
    conn.commit()
    return conn

def parse_visitor_names(text: str) -> list[dict]:
    """来店者名リストを抽出する"""
    visitors = []

    # 来店人数セクションを探す
    section_match = re.search(
        r'【来店人数】.*?(?=【|$)',
        text, re.DOTALL
    )
    if not section_match:
        return visitors

    section = section_match.group(0)

    # 人数サマリー行（新規〇名、リピ〇名）を抽出
    new_count = 0
    repeat_count = 0
    cafe_count = 0
    named_count = 0

    new_match = re.search(r'新規[　\s]*(\d+)', section)
    if new_match:
        new_count = int(new_match.group(1))
    repeat_match = re.search(r'リピ[ーター]*[　\s]*(\d+)', section)
    if repeat_match:
        repeat_count = int(repeat_match.group(1))
    cafe_match = re.search(r'カフェ[利用]*[　\s]*(\d+)', section)
    if cafe_match:
        cafe_count = int(cafe_match.group(1))

    # 名前リスト: 「さん」付き・読点区切り・箇条書きなど多様なフォーマットに対応
    # メイソンズ形式: 行ごとに「名前さん」
    # 柏・西船橋形式: 「名前さん、名前さん、...」や行ごと
    # 新規マーク: 🆕

    lines = section.split('\n')
    in_name_section = False

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # セクション境界
        if re.match(r'【(新規|リピ|計|連絡|レジ|明日|無い|今日)', line):
            break
        if re.match(r'新規|リピ|　計|合計', line):
            continue

        # 除外パターン
        skip = False
        for pat in EXCLUDE_PATTERNS:
            if re.search(pat, line):
                skip = True
                break
        if skip:
            continue

        # 🆕 マークの新規顧客（詳細メモあり）
        is_new = '🆕' in line or line.startswith('新規')

        # 名前候補を抽出（読点・中黒・スペース区切り）
        # 先頭の記号を除去
        clean = re.sub(r'^[・\-\*\•→　\s🆕]+', '', line)
        clean = re.sub(r'\(.*?\)|（.*?）|\[.*?\]|【.*?】', '', clean)  # 括弧内除去

        # カンマ・読点・中黒で分割
        parts = re.split(r'[、,，・]', clean)

        for part in parts:
            part = part.strip()
            if not part or len(part) < 2:
                continue
            # 長すぎる場合は個人名ではなく説明文・センテンス
            if len(part) > MAX_NAME_LEN:
                continue

            # サービスタイプ判定
            service = 'normal'
            if TOP_CHANGE_PATTERN.search(part):
                service = 'top_change'
                part = TOP_CHANGE_PATTERN.sub('', part).strip()
            elif CAFE_PATTERN.search(part):
                service = 'cafe'
                part = CAFE_PATTERN.sub('', part).strip()

            # 「さん」「くん」「ちゃん」等の敬称を除去して正規化
            # ただし表示名には残す
            normalized = normalize_name(part)
            if not normalized or len(normalized) < 2:
                continue

            # 数字だけ、記号だけ等を除外
            if re.match(r'^[\d\s\W]+$', normalized):
                continue

            visitors.append({
                'display_name': part,
                'normalized': normalized,
                'service': service,
                'is_new': is_new,
                'memo': '',
            })
            named_count += 1

    # 名無しリピーター数 = リピ総数 - 名前付き
    unnamed_repeat = max(0, repeat_count - named_count)

    return visitors, {
        'new_count': new_count,
        'repeat_unnamed_count': unnamed_repeat,
        'repeat_named_count': named_count,
        'cafe_count': cafe_count,
    }

def extract_new_customer_memo(text: str, name: str) -> str:
    """新規顧客の詳細メモを抽出"""
    # 🆕マーク以降のブロックを探す
    pattern = rf'🆕.*?{re.escape(name.replace("さん",""))}.*?\n(.*?)(?=🆕|【|\Z)'
    match = re.search(pattern, text, re.DOTALL)
    if match:
        memo = match.group(1).strip()
        # 最初の3行まで
        lines = [l.strip() for l in memo.split('\n') if l.strip()][:3]
        return ' / '.join(lines)
    return ''

def normalize_name(name: str) -> str:
    """名前を正規化（敬称除去・スペース除去）"""
    name = name.strip()
    # 末尾の敬称除去（表示はそのまま）
    name = re.sub(r'[　\s]+', '', name)
    # 特殊文字除去
    name = re.sub(r'[^\w\u3040-\u30ff\u4e00-\u9fff\u3400-\u4dbf]', '', name)
    return name

def parse_report_file(filepath: Path, store: str, conn: sqlite3.Connection):
    """1つの日報ファイルを処理"""
    text = filepath.read_text(encoding='utf-8')

    # 日付をファイル名から取得
    date_match = re.search(r'(\d{4}-\d{2}-\d{2})', filepath.name)
    if not date_match:
        return
    date = date_match.group(1)

    # 来店者名を抽出
    result = parse_visitor_names(text)
    if not result:
        return

    visitors, summary = result

    # daily_summary に upsert
    conn.execute("""
        INSERT OR REPLACE INTO daily_summary
        (store, date, new_count, repeat_unnamed_count, repeat_named_count, cafe_count, source_file)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (store, date, summary['new_count'], summary['repeat_unnamed_count'],
          summary['repeat_named_count'], summary['cafe_count'], str(filepath)))
    conn.commit()

    # 各来店者を処理
    for v in visitors:
        name = v['display_name']
        normalized = v['normalized']
        service = v['service']

        # customers テーブルで名前を検索（あいまい一致）
        customer = find_or_create_customer(conn, name, normalized, store, date)
        if not customer:
            continue

        customer_id = customer['id']

        # visits テーブルに追加（同日同店舗の重複は無視）
        existing = conn.execute(
            "SELECT id FROM visits WHERE customer_id=? AND store=? AND date=?",
            (customer_id, store, date)
        ).fetchone()

        if not existing:
            conn.execute("""
                INSERT INTO visits (customer_id, store, date, service_type, source_file)
                VALUES (?, ?, ?, ?, ?)
            """, (customer_id, store, date, service, str(filepath)))

        # customers の集計を更新
        conn.execute("""
            UPDATE customers SET
                total_visits = (SELECT COUNT(*) FROM visits WHERE customer_id=?),
                last_visit_date = MAX(COALESCE(last_visit_date,''), ?),
                updated_at = datetime('now')
            WHERE id=?
        """, (customer_id, date, customer_id))

        # primary_store: 最も来店回数の多い店舗
        top_store = conn.execute("""
            SELECT store, COUNT(*) as cnt FROM visits
            WHERE customer_id=? GROUP BY store ORDER BY cnt DESC LIMIT 1
        """, (customer_id,)).fetchone()
        if top_store:
            conn.execute("UPDATE customers SET primary_store=? WHERE id=?",
                        (top_store[0], customer_id))

    conn.commit()

def row_to_dict(conn, row) -> dict:
    """sqlite3のRowをdictに変換（row_factory不要）"""
    cols = [d[1] for d in conn.execute("PRAGMA table_info(customers)").fetchall()]
    return dict(zip(cols, row))

def find_or_create_customer(conn, display_name: str, normalized: str,
                             store: str, date: str) -> dict:
    """顧客を検索、なければ作成"""
    base_name = normalized.replace('さん','').replace('くん','').replace('ちゃん','')

    # 完全一致
    row = conn.execute(
        "SELECT * FROM customers WHERE name=? AND merged_into IS NULL",
        (display_name,)
    ).fetchone()
    if row:
        return row_to_dict(conn, row)

    # エイリアス検索
    row = conn.execute(
        "SELECT * FROM customers WHERE aliases LIKE ? AND merged_into IS NULL",
        (f'%{display_name}%',)
    ).fetchone()
    if row:
        return row_to_dict(conn, row)

    # 正規化名で検索（敬称除去後の部分一致）
    row = conn.execute("""
        SELECT * FROM customers
        WHERE replace(replace(replace(name,'さん',''),'くん',''),'ちゃん','') = ?
        AND merged_into IS NULL
        LIMIT 1
    """, (base_name,)).fetchone()
    if row:
        return row_to_dict(conn, row)

    # 新規作成
    conn.execute("""
        INSERT INTO customers (name, primary_store, first_visit_date, last_visit_date, total_visits, rank)
        VALUES (?, ?, ?, ?, 1, 'A')
    """, (display_name, store, date, date))
    conn.commit()
    row = conn.execute(
        "SELECT * FROM customers WHERE name=? ORDER BY id DESC LIMIT 1",
        (display_name,)
    ).fetchone()
    if row:
        return row_to_dict(conn, row)
    return None

def update_cross_store_flags(conn):
    """同名が複数店舗にいる顧客にフラグ"""
    # 正規化名が同じで店舗が異なる顧客を検索
    rows = conn.execute("""
        SELECT c1.id, c2.id
        FROM customers c1
        JOIN customers c2 ON (
            replace(replace(c1.name,'さん',''),'くん','') =
            replace(replace(c2.name,'さん',''),'くん','')
            AND c1.id != c2.id
            AND c1.primary_store != c2.primary_store
            AND c1.merged_into IS NULL
            AND c2.merged_into IS NULL
        )
    """).fetchall()

    for r in rows:
        conn.execute("UPDATE customers SET cross_store_flag=1 WHERE id IN (?,?)", r)
    conn.commit()
    print(f"クロスストアフラグ: {len(rows)}件")

def auto_rank(conn):
    """来店回数ベースで自動ランク付け（Sは手動）"""
    # 来店10回以上かつfirst_visitから180日以上: Sランク候補（手動確認用）
    conn.execute("""
        UPDATE customers SET rank='A'
        WHERE total_visits >= 1 AND rank NOT IN ('S') AND merged_into IS NULL
    """)
    conn.commit()

def import_all_reports():
    """全日報を一括インポート"""
    conn = init_db()

    total = 0
    for store in STORES:
        store_path = REPORTS_BASE / store
        if not store_path.exists():
            print(f"⚠️  {store}: フォルダなし")
            continue

        files = sorted(store_path.rglob("20[0-9][0-9]-[0-9][0-9]-[0-9][0-9].md"))
        print(f"📁 {store}: {len(files)}件処理中...")

        for i, f in enumerate(files):
            try:
                parse_report_file(f, store, conn)
            except Exception as e:
                print(f"  ⚠️ {f.name}: {e}")

            if (i+1) % 100 == 0:
                print(f"  {i+1}/{len(files)}...")

        count = conn.execute(
            "SELECT COUNT(*) FROM visits WHERE store=?", (store,)
        ).fetchone()[0]
        print(f"  ✅ {store}: 来店ログ {count}件")
        total += len(files)

    update_cross_store_flags(conn)
    auto_rank(conn)

    cust_count = conn.execute("SELECT COUNT(*) FROM customers WHERE merged_into IS NULL").fetchone()[0]
    visit_count = conn.execute("SELECT COUNT(*) FROM visits").fetchone()[0]
    print(f"\n✅ 完了: 顧客 {cust_count}名 / 来店ログ {visit_count}件 / 処理ファイル {total}件")
    conn.close()

if __name__ == "__main__":
    import_all_reports()
