"""
日報パーサー: Obsidianの日報MDから顧客名・来店情報を抽出してSupabase(PostgreSQL)に保存
"""
import re
import hashlib
from pathlib import Path
from datetime import datetime

from mosh_db import get_conn, migrate_db

REPORTS_BASE = Path("/Users/kiyomotoyuuki/Library/Mobile Documents/com~apple~CloudDocs/Obsidian/Second Brain/MOSH/07_議事録・記録/日報")

STORES = ["柏", "東村山", "おおたか", "メイソンズ", "西船橋"]

# 来店者名リストから除外するキーワード（スタッフ名・システム文言・非個人名）
EXCLUDE_PATTERNS = [
    r'^【', r'^（', r'^\[', r'終業報告', r'連絡事項', r'レジ締め',
    r'^新規', r'^リピ', r'^計', r'^カフェ', r'^S$', r'^B$', r'^C$',
    r'お願い', r'補充', r'掃除', r'報告', r'確認', r'問い合わせ',
    # 人数・性別表記（個人名ではない）
    r'\d+名', r'\d+人', r'[男女]性', r'男の子', r'女の子', r'^男$', r'^女$',
    r'^一見', r'^初見', r'リピーター', r'^グループ', r'^お連れ',
    # 助詞・接続詞を含む文章（説明文・感想文）
    r'[をへ]', r'ました$', r'ます$', r'です$', r'てる$', r'てた$',
    r'見て', r'来て', r'持って', r'持ち', r'なって', r'して',
    # 説明的なキーワード
    r'おすすめ', r'興味', r'ミックス', r'フレーバー', r'シーシャ',
    r'来店', r'予約', r'注文', r'インスタ', r'Twitter', r'X$', r'TikTok',
    r'SNS', r'口コミ', r'クーポン', r'初回',
    # 金額・レジ・商品名（個人名ではない）
    r'[¥￥]', r'レジ金', r'レジ', r'現金', r'売上', r'合計',
    r'レギュラー', r'スイーツ', r'ドリンク', r'フード', r'台$', r'皿$',
    r'その他', r'会員名', r'会員登録', r'メンバー',
    # 時刻表記（22:20など）
    r'\d{1,2}:\d{2}',
    # 飲み方・使い方系
    r'飲み方', r'ソフト', r'ハード', r'吸い方',
    # テンプレート・矢印・記号
    r'^[↓↑→←▼▲►◄]', r'名前わかる', r'名前を書', r'書く', r'かく$',
    r'^書', r'テンプレ', r'フォーマット',
    # 数字のみ・記号のみ
    r'^\d+$', r'^[\W\s]+$',
]

# 個人名として許容する最大文字数（敬称込みで）
MAX_NAME_LEN = 12

# サービスタイプ判定
TOP_CHANGE_PATTERN = re.compile(r'トップ替え|トップ変え|topチェンジ', re.IGNORECASE)
CAFE_PATTERN = re.compile(r'カフェ|cafe', re.IGNORECASE)
MEMBER_PATTERN = re.compile(r'会員登録|メンバー登録|member', re.IGNORECASE)


def init_db():
    """DBを初期化してコネクションを返す（ローカル実行用）"""
    migrate_db()
    return get_conn()


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

    lines = section.split('\n')

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # セクション境界
        if re.match(r'【(新規|リピ|計|連絡|レジ|明日|無い|今日)', line):
            break
        if re.match(r'[>　\s]*新規|[>　\s]*リピ|[>　\s]*　計|[>　\s]*合計', line):
            continue

        # Discordクォート記号(>) や装飾記号を除去
        clean = re.sub(r'^[>・\-\*\•→　\s🆕]+', '', line)
        clean = re.sub(r'\(.*?\)|（.*?）|\[.*?\]|【.*?】', '', clean)
        clean = clean.strip()

        # 除外パターン（クリーン済みテキストに適用）
        skip = False
        for pat in EXCLUDE_PATTERNS:
            if re.search(pat, clean):
                skip = True
                break
        if skip:
            continue

        is_new = '🆕' in line or clean.startswith('新規')

        # 区切り文字で分割して個人名を抽出
        # 対応: 読点・カンマ・中黒・&・＆・「と」（敬称の後）
        parts = re.split(
            r'[、,，・&＆]'
            r'|(?<=[さんくんちゃん])と(?=\S)'
            r'|(?<=さん)と(?=\S)'
            r'|(?<=くん)と(?=\S)'
            r'|(?<=ちゃん)と(?=\S)',
            clean
        )

        for part in parts:
            part = part.strip()
            if not part or len(part) < 2:
                continue
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

            normalized = normalize_name(part)
            if not normalized or len(normalized) < 2:
                continue

            if re.match(r'^[\d\s\W]+$', normalized):
                continue

            # 複数人が残っている場合はスキップ（さん・くん・ちゃんが2回以上 or &が残存）
            honorific_count = len(re.findall(r'さん|くん|ちゃん', part))
            if honorific_count >= 2 or re.search(r'[&＆]', part):
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
    pattern = rf'🆕.*?{re.escape(name.replace("さん",""))}.*?\n(.*?)(?=🆕|【|\Z)'
    match = re.search(pattern, text, re.DOTALL)
    if match:
        memo = match.group(1).strip()
        lines = [l.strip() for l in memo.split('\n') if l.strip()][:3]
        return ' / '.join(lines)
    return ''


def normalize_name(name: str) -> str:
    """名前を正規化（敬称除去・スペース除去）"""
    name = name.strip()
    name = re.sub(r'[　\s]+', '', name)
    name = re.sub(r'[^\w\u3040-\u30ff\u4e00-\u9fff\u3400-\u4dbf]', '', name)
    return name


def parse_report_file(filepath: Path, store: str, conn):
    """1つの日報ファイルを処理"""
    text = filepath.read_text(encoding='utf-8')

    date_match = re.search(r'(\d{4}-\d{2}-\d{2})', filepath.name)
    if not date_match:
        return
    date = date_match.group(1)

    result = parse_visitor_names(text)
    if not result:
        return

    visitors, summary = result

    with conn.cursor() as cur:
        # daily_summary に upsert
        cur.execute("""
            INSERT INTO daily_summary
            (store, date, new_count, repeat_unnamed_count, repeat_named_count, cafe_count, source_file)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (store, date) DO UPDATE SET
                new_count=EXCLUDED.new_count,
                repeat_unnamed_count=EXCLUDED.repeat_unnamed_count,
                repeat_named_count=EXCLUDED.repeat_named_count,
                cafe_count=EXCLUDED.cafe_count,
                source_file=EXCLUDED.source_file
        """, (store, date, summary['new_count'], summary['repeat_unnamed_count'],
              summary['repeat_named_count'], summary['cafe_count'], str(filepath)))
        conn.commit()

        # 各来店者を処理
        for v in visitors:
            name = v['display_name']
            normalized = v['normalized']
            service = v['service']

            customer = find_or_create_customer(conn, name, normalized, store, date)
            if not customer:
                continue

            customer_id = customer['id']

            # 同日同店舗の重複チェック
            cur.execute(
                "SELECT id FROM visits WHERE customer_id=%s AND store=%s AND date=%s",
                (customer_id, store, date)
            )
            existing = cur.fetchone()

            if not existing:
                cur.execute("""
                    INSERT INTO visits (customer_id, store, date, service_type, source_file)
                    VALUES (%s, %s, %s, %s, %s)
                """, (customer_id, store, date, service, str(filepath)))

            # customers の集計を更新
            cur.execute("""
                UPDATE customers SET
                    total_visits = (SELECT COUNT(*) FROM visits WHERE customer_id=%s),
                    last_visit_date = GREATEST(COALESCE(last_visit_date,''), %s),
                    updated_at = NOW()
                WHERE id=%s
            """, (customer_id, date, customer_id))

            # primary_store: 最も来店回数の多い店舗
            cur.execute("""
                SELECT store, COUNT(*) as cnt FROM visits
                WHERE customer_id=%s GROUP BY store ORDER BY cnt DESC LIMIT 1
            """, (customer_id,))
            top_store = cur.fetchone()
            if top_store:
                cur.execute("UPDATE customers SET primary_store=%s WHERE id=%s",
                            (top_store['store'], customer_id))

        conn.commit()


def find_or_create_customer(conn, display_name: str, normalized: str,
                             store: str, date: str) -> dict:
    """顧客を検索、なければ作成"""
    base_name = normalized.replace('さん', '').replace('くん', '').replace('ちゃん', '')

    with conn.cursor() as cur:
        # 完全一致
        cur.execute(
            "SELECT * FROM customers WHERE name=%s AND merged_into IS NULL",
            (display_name,)
        )
        row = cur.fetchone()
        if row:
            return dict(row)

        # エイリアス検索
        cur.execute(
            "SELECT * FROM customers WHERE aliases LIKE %s AND merged_into IS NULL",
            (f'%{display_name}%',)
        )
        row = cur.fetchone()
        if row:
            return dict(row)

        # 正規化名で検索（敬称除去後の部分一致）
        cur.execute("""
            SELECT * FROM customers
            WHERE replace(replace(replace(name,'さん',''),'くん',''),'ちゃん','') = %s
            AND merged_into IS NULL
            LIMIT 1
        """, (base_name,))
        row = cur.fetchone()
        if row:
            return dict(row)

        # 新規作成
        cur.execute("""
            INSERT INTO customers (name, primary_store, first_visit_date, last_visit_date, total_visits, rank)
            VALUES (%s, %s, %s, %s, 1, 'A')
            RETURNING *
        """, (display_name, store, date, date))
        conn.commit()
        row = cur.fetchone()
        return dict(row) if row else None


def update_cross_store_flags(conn):
    """同名が複数店舗にいる顧客にフラグ"""
    with conn.cursor() as cur:
        cur.execute("""
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
        """)
        rows = cur.fetchall()

        for r in rows:
            cur.execute("UPDATE customers SET cross_store_flag=1 WHERE id IN (%s,%s)",
                        (r['id'], r['id_1'] if 'id_1' in r else list(r.values())[1]))
        conn.commit()
    print(f"クロスストアフラグ: {len(rows)}件")


def auto_rank(conn):
    """来店回数ベースで自動ランク付け（Sは手動）"""
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE customers SET rank='A'
            WHERE total_visits >= 1 AND rank NOT IN ('S') AND merged_into IS NULL
        """)
        conn.commit()


def import_all_reports():
    """全日報を一括インポート（Supabase PostgreSQL）"""
    import os
    # ローカル実行時は環境変数 DATABASE_URL を設定してから実行
    # 例: export DATABASE_URL="postgresql://postgres.xxx:password@pooler.supabase.com:5432/postgres"

    migrate_db()

    total = 0
    for store in STORES:
        store_path = REPORTS_BASE / store
        if not store_path.exists():
            print(f"⚠️  {store}: フォルダなし")
            continue

        files = sorted(store_path.rglob("20[0-9][0-9]-[0-9][0-9]-[0-9][0-9].md"))
        print(f"📁 {store}: {len(files)}件処理中...")

        for i, f in enumerate(files):
            # ファイルごとに独立したコネクションを使う（デッドロック防止）
            for attempt in range(3):
                try:
                    with get_conn() as conn:
                        parse_report_file(f, store, conn)
                    break
                except Exception as e:
                    if attempt < 2 and "deadlock" in str(e).lower():
                        import time; time.sleep(0.5)
                        continue
                    print(f"  ⚠️ {f.name}: {e}")
                    break

            if (i + 1) % 100 == 0:
                print(f"  {i+1}/{len(files)}...")

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) as cnt FROM visits WHERE store=%s", (store,))
                count = cur.fetchone()['cnt']
        print(f"  ✅ {store}: 来店ログ {count}件")
        total += len(files)

    with get_conn() as conn:
        update_cross_store_flags(conn)
        auto_rank(conn)

        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) as cnt FROM customers WHERE merged_into IS NULL")
            cust_count = cur.fetchone()['cnt']
            cur.execute("SELECT COUNT(*) as cnt FROM visits")
            visit_count = cur.fetchone()['cnt']

    print(f"\n✅ 完了: 顧客 {cust_count}名 / 来店ログ {visit_count}件 / 処理ファイル {total}件")


if __name__ == "__main__":
    import_all_reports()
