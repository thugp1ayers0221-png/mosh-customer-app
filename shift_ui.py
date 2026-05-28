"""
MOSH シフト管理 UI

タブ構成:
  📅 シフト管理       — owner / manager / payroll_admin（カレンダー型編集）
  🗓 マイシフト       — 全員（自分のシフト閲覧）
  ⏱ 打刻              — 全員（出退勤）
  📝 シフト希望        — 全員（希望提出）／owner系（希望一覧確認）
  💰 給与計算          — owner / payroll_admin（要セカンドパスワード）
  ⚙️ スタッフマスター — owner / payroll_admin
"""
import io
import re
import calendar
import time as time_module
from datetime import datetime, date, time, timedelta
from typing import Optional

import streamlit as st
import pandas as pd

import shift_db
import payroll_logic as pl


# ─────────────────────────────────────────
# 共通ユーティリティ
# ─────────────────────────────────────────

STORE_OPTIONS = [
    ("kashiwa",         "柏店"),
    ("masons",          "The Mason's"),
    ("higashimurayama", "東村山店"),
    ("nishifunabashi",  "西船橋店"),
    ("otaka",           "おおたかの森店"),
    ("matsudo",         "松戸店"),
]
STORE_CODE_TO_NAME = dict(STORE_OPTIONS)
STORE_NAME_TO_CODE = {n: c for c, n in STORE_OPTIONS}


def _csv_download(df: pd.DataFrame, filename: str, label: str = "📥 CSV出力"):
    """UTF-8 BOM付きCSVをダウンロードボタンで提供"""
    buf = io.BytesIO()
    buf.write("﻿".encode("utf-8"))
    df.to_csv(buf, index=False, encoding="utf-8")
    st.download_button(
        label=label,
        data=buf.getvalue(),
        file_name=filename,
        mime="text/csv",
    )


def _is_payroll_admin(user: dict) -> bool:
    return user and user.get("role") in ("owner", "payroll_admin")


def _is_manager_or_above(user: dict) -> bool:
    return user and user.get("role") in ("owner", "manager", "payroll_admin")


def _parse_time_cell(cell: str) -> Optional[tuple[time, time, bool]]:
    """
    「15-24」「15:30-24」「15-29」のような時間文字列をパース。
    返り値: (start_time, end_time, crosses_midnight) or None（休み/空欄）

    24以上の数字は翌日扱い（例: 29 → 翌5:00, crosses_midnight=True）
    """
    if not cell or not isinstance(cell, str):
        return None
    cell = cell.strip()
    if cell in ("", "休", "×", "ー", "-", "—", "－"):
        return None
    # ↓ 数字-数字 or 数字:分-数字:分
    m = re.match(r"^(\d{1,2})(?::(\d{1,2}))?\s*[-〜~]\s*(\d{1,2})(?::(\d{1,2}))?$", cell)
    if not m:
        return None
    sh, sm, eh, em = m.group(1), m.group(2), m.group(3), m.group(4)
    sh, sm = int(sh), int(sm or 0)
    eh, em = int(eh), int(em or 0)
    crosses = False
    if eh >= 24:
        eh -= 24
        crosses = True
    try:
        st_t = time(sh, sm)
        en_t = time(eh, em)
    except ValueError:
        return None
    return (st_t, en_t, crosses)


def _format_time_cell(start: time, end: time, crosses_midnight: bool) -> str:
    sh = f"{start.hour}:{start.minute:02d}" if start.minute else f"{start.hour}"
    eh = end.hour + (24 if crosses_midnight else 0)
    eh_str = f"{eh}:{end.minute:02d}" if end.minute else f"{eh}"
    return f"{sh}-{eh_str}"


def _shift_to_datetimes(shift_date: date, start_t: time, end_t: time, crosses: bool):
    """シフトレコードから出退勤の datetime ペアを生成"""
    start_dt = datetime.combine(shift_date, start_t)
    end_dt = datetime.combine(shift_date, end_t)
    if crosses or (end_t < start_t):
        end_dt += timedelta(days=1)
    return start_dt, end_dt


# ─────────────────────────────────────────
# 1. シフト管理タブ（owner / manager / payroll_admin）
# ─────────────────────────────────────────

def render_shift_create_tab(user: dict):
    st.markdown("### 📅 シフト管理")

    if not _is_manager_or_above(user):
        st.warning("この画面は管理者専用です。")
        return

    # 店舗選択（managerは自店舗のみ）
    available_codes = [c for c, _ in STORE_OPTIONS]
    if user.get("role") == "manager" and user.get("store"):
        # 既存usersテーブルでは表示名で保存されているのでマップで変換
        mapped = STORE_NAME_TO_CODE.get(user["store"]) or user["store"]
        available_codes = [mapped] if mapped in dict(STORE_OPTIONS) else available_codes

    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        store_code = st.selectbox(
            "店舗",
            available_codes,
            format_func=lambda c: STORE_CODE_TO_NAME.get(c, c),
            key="shift_store",
        )
    with col2:
        today = date.today()
        ym_options = []
        for i in range(-1, 4):
            d = (today.replace(day=1) + timedelta(days=32 * i)).replace(day=1)
            ym_options.append(d.strftime("%Y-%m"))
        ym = st.selectbox("月", ym_options, index=1, key="shift_ym")
    with col3:
        st.markdown("&nbsp;")
        refresh = st.button("🔄 再読込", use_container_width=True)

    year, month = map(int, ym.split("-"))
    _, days_in_month = calendar.monthrange(year, month)
    days = list(range(1, days_in_month + 1))

    # スタッフ取得（その店舗で勤務可能な人）
    staffs = shift_db.get_all_staff(active_only=True, store=store_code)
    if not staffs:
        st.info("この店舗で勤務可能なスタッフがまだ登録されていません。")
        return

    # シフト取得
    shifts = shift_db.get_shifts_by_month(ym, store=store_code)
    shift_map = {}
    for s in shifts:
        shift_map[(s["staff_id"], s["shift_date"].day)] = s

    # DataFrame作成
    rows = []
    for staff in staffs:
        row = {"スタッフ": staff["display_name"], "_staff_id": staff["id"]}
        for d in days:
            sh = shift_map.get((staff["id"], d))
            row[str(d)] = _format_time_cell(sh["start_time"], sh["end_time"], sh["crosses_midnight"]) if sh else ""
        rows.append(row)
    df = pd.DataFrame(rows)

    st.caption(f"💡 セルに「15-24」のように時間帯を入力。休みは空欄または「休」「×」「ー」。翌日にまたぐ場合は「15-29」（→翌5時）形式")

    # 編集
    edited = st.data_editor(
        df.drop(columns=["_staff_id"]),
        use_container_width=True,
        hide_index=True,
        key=f"shift_editor_{store_code}_{ym}",
        disabled=["スタッフ"],
        column_config={"スタッフ": st.column_config.TextColumn(width="small")},
    )

    # 保存ボタン
    col_save, col_csv = st.columns([1, 1])
    with col_save:
        if st.button("💾 シフトを保存", type="primary", use_container_width=True):
            _save_shift_changes(edited, df, staffs, year, month, store_code, user)
    with col_csv:
        _csv_download(edited, f"mosh_shifts_{store_code}_{ym}.csv")

    # サマリー（労働時間・人件費試算）
    st.markdown("---")
    _render_shift_summary(staffs, shifts, store_code, ym, user)


def _save_shift_changes(edited_df: pd.DataFrame, original_df: pd.DataFrame,
                          staffs: list, year: int, month: int, store_code: str, user: dict):
    """data_editor の差分を検出して upsert/delete"""
    changes = 0
    errors = []
    user_id = user.get("id")

    for idx, row in edited_df.iterrows():
        staff = staffs[idx]
        staff_id = staff["id"]
        for col in edited_df.columns:
            if not col.isdigit():
                continue
            new_val = (row[col] or "").strip() if isinstance(row[col], str) else ""
            old_val = (original_df.iloc[idx][col] or "").strip() if isinstance(original_df.iloc[idx][col], str) else ""
            if new_val == old_val:
                continue
            day = int(col)
            try:
                shift_date = date(year, month, day)
            except ValueError:
                continue
            parsed = _parse_time_cell(new_val)
            # 新しい値が休/空 → 削除
            if parsed is None:
                # 既存シフトを削除（ある場合のみ）
                shifts_to_delete = [s for s in shift_db.get_shifts_by_month(f"{year:04d}-{month:02d}", store=store_code)
                                    if s["staff_id"] == staff_id and s["shift_date"] == shift_date]
                for s in shifts_to_delete:
                    shift_db.delete_shift(s["id"])
                changes += 1
            else:
                start_t, end_t, crosses = parsed
                try:
                    shift_db.upsert_shift(
                        staff_id=staff_id, store=store_code, shift_date=shift_date,
                        start_time=start_t, end_time=end_t,
                        crosses_midnight=crosses, created_by=user_id,
                    )
                    changes += 1
                except Exception as e:
                    errors.append(f"{staff['display_name']} {month}/{day}: {e}")

    if errors:
        for e in errors:
            st.error(e)
    if changes:
        st.success(f"✅ {changes}件のシフトを保存しました")
        st.rerun()
    else:
        st.info("変更はありませんでした")


def _render_shift_summary(staffs: list, shifts: list, store_code: str, ym: str, user: dict):
    """シフト合計時間 + 人件費試算（payroll_admin のみ人件費表示）"""
    st.markdown("#### 📊 月次サマリー")

    summaries = []
    for staff in staffs:
        staff_shifts = [s for s in shifts if s["staff_id"] == staff["id"]]
        total_raw = 0.0
        total_actual = 0.0
        for s in staff_shifts:
            start_dt, end_dt = _shift_to_datetimes(s["shift_date"], s["start_time"], s["end_time"], s["crosses_midnight"])
            split = pl.split_work_hours(start_dt, end_dt, staff["employment_type"])
            total_raw += split["raw_hours"]
            total_actual += split["actual_hours"]
        summaries.append({
            "スタッフ": staff["display_name"],
            "出勤日数": len(staff_shifts),
            "拘束時間": f"{total_raw:.1f}h",
            "実労働時間": f"{total_actual:.1f}h",
            "雇用形態": staff["employment_type"],
            "_actual_hours": total_actual,
            "_staff": staff,
        })

    df = pd.DataFrame(summaries).drop(columns=["_actual_hours", "_staff"])

    # 人件費は payroll_admin のみ表示（セカンドPWアンロックが必要）
    if _is_payroll_admin(user) and _payroll_unlocked():
        df_cost = []
        for s in summaries:
            staff = s["_staff"]
            staff_shifts = [sh for sh in shifts if sh["staff_id"] == staff["id"]]
            splits = []
            for sh in staff_shifts:
                start_dt, end_dt = _shift_to_datetimes(sh["shift_date"], sh["start_time"],
                                                        sh["end_time"], sh["crosses_midnight"])
                splits.append({"split": pl.split_work_hours(start_dt, end_dt, staff["employment_type"],
                                                              is_legal_holiday=sh["is_legal_holiday"]),
                                "date": sh["shift_date"]})
            rate = pl.calc_hourly_rate(
                employment_type=staff["employment_type"],
                hourly_wage=staff["hourly_wage"],
                base_monthly_salary=staff["base_monthly_salary"],
                monthly_standard_hours=staff["monthly_standard_hours"],
                position_allowance_per_hour=staff["position_allowance_per_hour"],
            )
            monthly = pl.calc_monthly_payroll(splits, rate, staff["employment_type"],
                                               base_monthly_salary=staff["base_monthly_salary"] or 0)
            df_cost.append({"スタッフ": staff["display_name"], "人件費": f"¥{monthly['total_pay']:,}"})

        df_cost_df = pd.DataFrame(df_cost)
        df = df.merge(df_cost_df, on="スタッフ", how="left")

        total_cost = sum(int(row["人件費"].replace("¥","").replace(",","")) for row in df_cost)
        store = next((s for s in shift_db.get_stores_master() if s["code"] == store_code), None)
        target = store["monthly_target_sales"] if store else 0
        ratio = (total_cost / target * 100) if target else 0
        target_ratio = float(store["target_labor_cost_ratio"]) if store else 30.0

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("総人件費", f"¥{total_cost:,}")
        with col2:
            st.metric("月間売上目標", f"¥{target:,}" if target else "—")
        with col3:
            color = "🟢" if ratio < target_ratio else ("🟡" if ratio < target_ratio + 5 else "🔴")
            st.metric("人件費比率", f"{color} {ratio:.1f}%", delta=f"目標 {target_ratio:.0f}%以下", delta_color="off")

    st.dataframe(df, use_container_width=True, hide_index=True)


# ─────────────────────────────────────────
# 2. マイシフトタブ（全員）
# ─────────────────────────────────────────

def render_my_shift_tab(user: dict):
    st.markdown("### 🗓 マイシフト")

    staff_id = user.get("staff_id")
    if not staff_id:
        st.warning("あなたのアカウントはまだスタッフマスターに紐付いていません。管理者に連絡してください。")
        return

    staff = shift_db.get_staff(staff_id)
    if not staff:
        st.error("スタッフ情報が見つかりません。")
        return

    st.caption(f"👤 {staff['display_name']}（{staff.get('nickname','')}）/ 主所属: {STORE_CODE_TO_NAME.get(staff['primary_store'], staff['primary_store'])}")

    # 月選択
    today = date.today()
    ym_options = []
    for i in range(-1, 3):
        d = (today.replace(day=1) + timedelta(days=32 * i)).replace(day=1)
        ym_options.append(d.strftime("%Y-%m"))
    ym = st.selectbox("月", ym_options, index=1, key="my_shift_ym")

    shifts = shift_db.get_shifts_by_month(ym, staff_id=staff_id)
    if not shifts:
        st.info("この月のシフトはまだ登録されていません。")
        return

    rows = []
    total_actual = 0.0
    total_expected_pay = 0
    rate = pl.calc_hourly_rate(
        employment_type=staff["employment_type"],
        hourly_wage=staff["hourly_wage"],
        base_monthly_salary=staff["base_monthly_salary"],
        monthly_standard_hours=staff["monthly_standard_hours"],
        position_allowance_per_hour=staff["position_allowance_per_hour"],
    )
    for s in shifts:
        start_dt, end_dt = _shift_to_datetimes(s["shift_date"], s["start_time"], s["end_time"], s["crosses_midnight"])
        split = pl.split_work_hours(start_dt, end_dt, staff["employment_type"],
                                     is_legal_holiday=s["is_legal_holiday"])
        pay = pl.calc_single_shift_pay(split, rate)
        total_actual += split["actual_hours"]
        total_expected_pay += sum(pay.values())
        rows.append({
            "日付": s["shift_date"].strftime("%-m/%-d (%a)") if hasattr(s["shift_date"], "strftime") else str(s["shift_date"]),
            "店舗": STORE_CODE_TO_NAME.get(s["store"], s["store"]),
            "時間帯": _format_time_cell(s["start_time"], s["end_time"], s["crosses_midnight"]),
            "拘束": f"{split['raw_hours']:.1f}h",
            "実労働": f"{split['actual_hours']:.1f}h",
        })

    df = pd.DataFrame(rows)
    col1, col2 = st.columns(2)
    with col1:
        st.metric("月間総実労働", f"{total_actual:.1f}h")
    with col2:
        if staff["employment_type"] == "社員":
            st.metric("月給", f"¥{staff['base_monthly_salary']:,}" if staff["base_monthly_salary"] else "未設定")
        else:
            st.metric("予定収入（見込）", f"¥{total_expected_pay:,}" if total_expected_pay else "—")

    st.dataframe(df, use_container_width=True, hide_index=True)
    _csv_download(df, f"my_shifts_{staff_id}_{ym}.csv")


# ─────────────────────────────────────────
# 3. 打刻タブ（全員）
# ─────────────────────────────────────────

def render_timecard_tab(user: dict):
    st.markdown("### ⏱ 打刻（出退勤）")

    staff_id = user.get("staff_id")
    if not staff_id:
        st.warning("あなたのアカウントはまだスタッフマスターに紐付いていません。管理者に連絡してください。")
        return

    staff = shift_db.get_staff(staff_id)
    open_log = shift_db.get_open_time_log(staff_id)

    st.markdown(f"#### 👤 {staff['display_name']}")

    if open_log:
        # 退勤前の状態
        st.success(f"🟢 出勤中（{open_log['clock_in'].strftime('%H:%M')} ～）")
        elapsed = (datetime.now(open_log["clock_in"].tzinfo) - open_log["clock_in"])
        st.caption(f"経過時間: {elapsed.total_seconds() / 3600:.2f} 時間")
        if st.button("🔴 退勤", type="primary", use_container_width=True):
            shift_db.clock_out(open_log["id"])
            st.success("退勤しました。お疲れさまでした！")
            time_module.sleep(1)
            st.rerun()
    else:
        # 出勤前の状態
        st.info("⚪ 未出勤")
        store_code = st.selectbox("勤務店舗",
                                     [c for c, _ in STORE_OPTIONS],
                                     format_func=lambda c: STORE_CODE_TO_NAME.get(c, c),
                                     index=[c for c, _ in STORE_OPTIONS].index(staff["primary_store"])
                                     if staff["primary_store"] in [c for c, _ in STORE_OPTIONS] else 0,
                                     key="clock_in_store")
        if st.button("🟢 出勤", type="primary", use_container_width=True):
            shift_db.clock_in(staff_id, store_code)
            st.success("出勤を記録しました！")
            time_module.sleep(1)
            st.rerun()

    # 当月の打刻履歴
    st.markdown("---")
    st.markdown("#### 📋 今月の打刻履歴")
    ym = date.today().strftime("%Y-%m")
    logs = shift_db.get_time_logs_by_month(ym, staff_id=staff_id)
    if not logs:
        st.caption("打刻履歴はまだありません")
        return
    rows = []
    for log in logs:
        clock_in = log["clock_in"]
        clock_out = log["clock_out"]
        if clock_in and clock_out:
            split = pl.split_work_hours(clock_in.replace(tzinfo=None), clock_out.replace(tzinfo=None),
                                         staff["employment_type"])
            actual = f"{split['actual_hours']:.1f}h"
        else:
            actual = "—"
        rows.append({
            "日付": log["work_date"].strftime("%-m/%-d"),
            "店舗": STORE_CODE_TO_NAME.get(log["store"], log["store"]),
            "出勤": clock_in.strftime("%H:%M") if clock_in else "—",
            "退勤": clock_out.strftime("%H:%M") if clock_out else "🟢出勤中",
            "実労働": actual,
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    _csv_download(pd.DataFrame(rows), f"my_timelogs_{staff_id}_{ym}.csv")


# ─────────────────────────────────────────
# 4. シフト希望タブ（全員 + owner系の一覧確認）
# ─────────────────────────────────────────

def render_shift_request_tab(user: dict):
    st.markdown("### 📝 シフト希望")

    # 来月のYYYY-MM
    today = date.today()
    next_month_first = (today.replace(day=1) + timedelta(days=32)).replace(day=1)
    ym = next_month_first.strftime("%Y-%m")

    tabs = st.tabs(["📥 希望を提出", "📋 全員の希望一覧"] if _is_manager_or_above(user) else ["📥 希望を提出"])

    with tabs[0]:
        _render_submit_request(user, ym)

    if _is_manager_or_above(user) and len(tabs) > 1:
        with tabs[1]:
            _render_request_overview(ym)


def _render_submit_request(user: dict, ym: str):
    staff_id = user.get("staff_id")
    if not staff_id:
        st.warning("あなたのアカウントはまだスタッフマスターに紐付いていません。")
        return
    staff = shift_db.get_staff(staff_id)
    st.caption(f"👤 {staff['display_name']} / 来月 {ym} の希望を提出してください")

    year, month = map(int, ym.split("-"))
    _, days_in_month = calendar.monthrange(year, month)

    existing = {r["request_date"]: r for r in shift_db.get_shift_requests(ym, staff_id=staff_id)}

    rows = []
    for d in range(1, days_in_month + 1):
        rd = date(year, month, d)
        r = existing.get(rd)
        rows.append({
            "日付": rd.strftime("%-m/%-d (%a)"),
            "希望": r["request_type"] if r else "—",
            "希望時間帯": _format_request_time(r) if r else "",
            "備考": r["note"] if r else "",
            "_date": rd,
        })
    df = pd.DataFrame(rows)
    edited = st.data_editor(
        df.drop(columns=["_date"]),
        use_container_width=True,
        hide_index=True,
        column_config={
            "希望": st.column_config.SelectboxColumn(
                options=["—", "出れる", "休み希望", "時間指定"],
                required=False,
            ),
            "希望時間帯": st.column_config.TextColumn(help="例: 15-24"),
        },
        disabled=["日付"],
        key=f"req_editor_{ym}",
    )

    if st.button("💾 希望を保存", type="primary"):
        cnt = 0
        for i, row in edited.iterrows():
            rd = df.iloc[i]["_date"]
            rtype_map = {"出れる": "available", "休み希望": "unavailable", "時間指定": "preferred"}
            rtype = rtype_map.get(row["希望"])
            if not rtype:
                continue
            pstart, pend = None, None
            parsed = _parse_time_cell(row["希望時間帯"])
            if parsed:
                pstart, pend = parsed[0], parsed[1]
            shift_db.upsert_shift_request(staff_id, ym, rd, rtype, pstart, pend, row.get("備考","") or "")
            cnt += 1
        st.success(f"✅ {cnt}件の希望を保存しました")
        st.rerun()


def _format_request_time(r):
    if r.get("preferred_start") and r.get("preferred_end"):
        return _format_time_cell(r["preferred_start"], r["preferred_end"], False)
    return ""


def _render_request_overview(ym: str):
    reqs = shift_db.get_shift_requests(ym)
    if not reqs:
        st.info("まだ希望提出がありません")
        return
    rows = [{
        "スタッフ": r["display_name"],
        "店舗": STORE_CODE_TO_NAME.get(r["primary_store"], r["primary_store"]),
        "日付": r["request_date"].strftime("%-m/%-d"),
        "希望": {"available": "出れる", "unavailable": "休み希望", "preferred": "時間指定"}.get(r["request_type"], r["request_type"]),
        "希望時間帯": _format_request_time(r),
        "備考": r["note"] or "",
    } for r in reqs]
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)
    _csv_download(df, f"mosh_requests_{ym}.csv")


# ─────────────────────────────────────────
# 5. 給与計算タブ（owner / payroll_admin・セカンドPW保護）
# ─────────────────────────────────────────

# ─────────────────────────────────────────
# 初期セットアップタブ（owner専用・staff_seed投入）
# ─────────────────────────────────────────

def render_setup_tab(user: dict):
    st.markdown("### 📦 初期セットアップ")
    if user.get("role") != "owner":
        st.error("この画面は owner 専用です")
        return

    st.markdown("""
シフト管理ツールの**初回セットアップ**を行います。

- ✅ シフト管理用5テーブルを Supabase に作成（既存なら何もしない）
- ✅ 店舗マスター（5店舗）を初期投入
- ✅ スタッフマスターに全30名を投入
- ✅ 認証アカウントを30名分発行（初期PW: `MOSH4148`）
- ✅ 賃金画面パスワード設定（`datakintaimosh`）

**冪等です**：何度実行しても既存データは保護されます。
""")

    # 現状の登録状況
    try:
        current_staff = shift_db.get_all_staff(active_only=False)
        st.info(f"📊 現在の登録: スタッフ {len(current_staff)}名 / 店舗 {len(shift_db.get_stores_master(active_only=False))}店")
    except Exception as e:
        st.warning(f"DB接続を確認中... ({e})")

    if "setup_confirmed" not in st.session_state:
        st.session_state.setup_confirmed = False

    if not st.session_state.setup_confirmed:
        if st.button("🚀 セットアップを開始", type="primary"):
            st.session_state.setup_confirmed = True
            st.rerun()
    else:
        st.warning("⚠️ 本当に実行しますか？（既存データは保護されますが、新規スタッフが追加されます）")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ はい、実行", type="primary"):
                _run_setup()
                st.session_state.setup_confirmed = False
        with col2:
            if st.button("❌ キャンセル"):
                st.session_state.setup_confirmed = False
                st.rerun()


def _run_setup():
    import staff_seed
    log_area = st.empty()
    logs = []

    def log_fn(msg):
        logs.append(str(msg))
        log_area.code("\n".join(logs[-30:]))

    try:
        result = staff_seed.seed(log=log_fn)
        st.success(f"✅ セットアップ完了！スタッフ {result['staff_count']}名 / 新規ユーザー {result['user_created']}名")

        # 認証情報CSV出力
        creds_df = pd.DataFrame(result["credentials"])
        st.markdown("### 📥 全スタッフのログイン情報")
        st.dataframe(creds_df, use_container_width=True, hide_index=True)
        _csv_download(creds_df, f"mosh_staff_credentials_{date.today().strftime('%Y-%m-%d')}.csv",
                       label="📥 ログイン情報CSV（スタッフ配布用）")
    except Exception as e:
        st.error(f"❌ エラー: {e}")
        st.exception(e)


PAYROLL_UNLOCK_KEY = "payroll_unlocked_at"
PAYROLL_TIMEOUT_SEC = 30 * 60  # 30分


def _payroll_unlocked() -> bool:
    ts = st.session_state.get(PAYROLL_UNLOCK_KEY)
    if not ts:
        return False
    if (datetime.now() - ts).total_seconds() > PAYROLL_TIMEOUT_SEC:
        st.session_state.pop(PAYROLL_UNLOCK_KEY, None)
        return False
    return True


def require_payroll_unlock() -> bool:
    """賃金関連UIの前に呼ぶ。アンロック済みなら True、未アンロックなら入力UIを描画して False"""
    if _payroll_unlocked():
        return True
    st.warning("🔒 この画面は経営陣パスワードで保護されています")
    pw = st.text_input("経営陣パスワード", type="password", key="payroll_pw_input")
    if st.button("🔓 ロック解除"):
        if shift_db.verify_payroll_password(pw):
            st.session_state[PAYROLL_UNLOCK_KEY] = datetime.now()
            st.success("✅ ロック解除しました（30分間有効）")
            st.rerun()
        else:
            st.error("❌ パスワードが違います")
    return False


def render_payroll_tab(user: dict):
    st.markdown("### 💰 給与計算（経営陣限定）")

    if not _is_payroll_admin(user):
        st.error("この画面は経営陣（owner / payroll_admin）専用です")
        return

    if not require_payroll_unlock():
        return

    # 月選択
    today = date.today()
    ym_options = []
    for i in range(-3, 2):
        d = (today.replace(day=1) + timedelta(days=32 * i)).replace(day=1)
        ym_options.append(d.strftime("%Y-%m"))
    ym = st.selectbox("対象月", ym_options, index=3, key="payroll_ym")

    # ロック残り時間表示
    remain = PAYROLL_TIMEOUT_SEC - (datetime.now() - st.session_state[PAYROLL_UNLOCK_KEY]).total_seconds()
    st.caption(f"🔓 アンロック残り {int(remain // 60)}分{int(remain % 60)}秒")

    if st.button("🔒 今すぐ再ロック"):
        st.session_state.pop(PAYROLL_UNLOCK_KEY, None)
        st.rerun()

    st.markdown("---")

    # 全スタッフの月次集計
    staffs = shift_db.get_all_staff(active_only=True)
    shifts = shift_db.get_shifts_by_month(ym)
    logs = shift_db.get_time_logs_by_month(ym)

    # ソース選択
    source = st.radio("集計ソース", ["シフト（予定）", "打刻（実績）"], horizontal=True, key="payroll_source")

    rows = []
    for staff in staffs:
        if source == "シフト（予定）":
            staff_shifts = [s for s in shifts if s["staff_id"] == staff["id"]]
            splits = []
            for s in staff_shifts:
                start_dt, end_dt = _shift_to_datetimes(s["shift_date"], s["start_time"],
                                                        s["end_time"], s["crosses_midnight"])
                splits.append({"split": pl.split_work_hours(start_dt, end_dt, staff["employment_type"],
                                                              is_legal_holiday=s["is_legal_holiday"]),
                                "date": s["shift_date"]})
        else:
            staff_logs = [l for l in logs if l["staff_id"] == staff["id"] and l["clock_out"]]
            splits = []
            for l in staff_logs:
                splits.append({"split": pl.split_work_hours(l["clock_in"].replace(tzinfo=None),
                                                              l["clock_out"].replace(tzinfo=None),
                                                              staff["employment_type"]),
                                "date": l["work_date"]})

        if not splits:
            continue

        rate = pl.calc_hourly_rate(
            employment_type=staff["employment_type"],
            hourly_wage=staff["hourly_wage"],
            base_monthly_salary=staff["base_monthly_salary"],
            monthly_standard_hours=staff["monthly_standard_hours"],
            position_allowance_per_hour=staff["position_allowance_per_hour"],
        )
        monthly = pl.calc_monthly_payroll(splits, rate, staff["employment_type"],
                                           base_monthly_salary=staff["base_monthly_salary"] or 0)

        rows.append({
            "スタッフ": staff["display_name"],
            "店舗": STORE_CODE_TO_NAME.get(staff["primary_store"], staff["primary_store"]),
            "雇用": staff["employment_type"],
            "出勤日数": monthly["shift_days"],
            "拘束h": round(monthly["raw_hours"], 1),
            "休憩(分)": monthly["break_minutes"],
            "実労働h": round(monthly["actual_hours"], 1),
            "通常h": round(monthly["regular_hours"], 1),
            "深夜h": round(monthly["night_hours"], 1),
            "残業h": round(monthly["overtime_hours"], 1),
            "残業×深夜h": round(monthly["overtime_night_hours"], 1),
            "月60h超h": round(monthly["overtime_60_plus_hours"], 1),
            "法定休日h": round(monthly["holiday_hours"], 1),
            "基本給": monthly["base_monthly_salary"],
            "通常賃金": monthly["regular_pay"],
            "深夜手当": monthly["night_pay"],
            "残業手当": monthly["overtime_pay"],
            "残業×深夜手当": monthly["overtime_night_pay"],
            "月60h超手当": monthly["overtime_60_plus_pay"],
            "法定休日手当": monthly["holiday_pay"],
            "支給合計": monthly["total_pay"],
        })

    if not rows:
        st.info("対象月のデータがありません")
        return

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    total_pay = df["支給合計"].sum()
    st.metric("📊 月間総人件費", f"¥{total_pay:,}")

    _csv_download(df, f"mosh_payroll_{ym}_{source.replace('（','_').replace('）','')}.csv",
                   label="📥 給与計算CSVをダウンロード")

    # パスワード変更（owner のみ）
    if user.get("role") == "owner":
        st.markdown("---")
        with st.expander("🔧 経営陣パスワード変更"):
            new_pw = st.text_input("新しいパスワード", type="password", key="new_payroll_pw")
            new_pw2 = st.text_input("確認用パスワード", type="password", key="new_payroll_pw2")
            if st.button("変更を保存"):
                if not new_pw or new_pw != new_pw2:
                    st.error("パスワードが一致しません")
                else:
                    shift_db.update_payroll_password(new_pw)
                    st.success("✅ パスワードを変更しました")


# ─────────────────────────────────────────
# 6. スタッフマスター管理タブ（owner / payroll_admin・要セカンドPW）
# ─────────────────────────────────────────

def render_staff_admin_tab(user: dict):
    st.markdown("### ⚙️ スタッフマスター管理")

    if not _is_payroll_admin(user):
        st.error("この画面は経営陣（owner / payroll_admin）専用です")
        return
    if not require_payroll_unlock():
        return

    staffs = shift_db.get_all_staff(active_only=True)
    if not staffs:
        st.info("スタッフがまだ登録されていません。`staff_seed.py` を実行してください。")
        return

    rows = []
    for s in staffs:
        rows.append({
            "ID": s["id"],
            "本名": s["display_name"],
            "通称": s["nickname"] or "",
            "店舗": STORE_CODE_TO_NAME.get(s["primary_store"], s["primary_store"]),
            "役職": s["position"],
            "雇用": s["employment_type"],
            "時給": s["hourly_wage"] or 0,
            "月給": s["base_monthly_salary"] or 0,
            "所定h/月": s["monthly_standard_hours"] or 176,
            "役職給/h": s["position_allowance_per_hour"] or 0,
            "週休日数": s["weekly_off_days"] or 2,
            "月目標h": s["monthly_target_hours"] or 160,
            "フレキ": s["flexible"],
        })
    df = pd.DataFrame(rows)
    edited = st.data_editor(
        df,
        use_container_width=True,
        hide_index=True,
        disabled=["ID", "本名"],
        column_config={
            "雇用": st.column_config.SelectboxColumn(options=["社員", "アルバイト", "業務委託"]),
            "時給": st.column_config.NumberColumn(min_value=0, step=10),
            "月給": st.column_config.NumberColumn(min_value=0, step=1000),
            "所定h/月": st.column_config.NumberColumn(min_value=0, step=1),
            "役職給/h": st.column_config.NumberColumn(min_value=0, step=10),
            "週休日数": st.column_config.NumberColumn(min_value=0, max_value=7, step=1),
            "月目標h": st.column_config.NumberColumn(min_value=0, step=4),
        },
        key="staff_admin_editor",
    )

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("💾 変更を保存", type="primary", use_container_width=True):
            cnt = 0
            for i, row in edited.iterrows():
                orig = df.iloc[i]
                changed = {}
                if row["通称"] != orig["通称"]: changed["nickname"] = row["通称"]
                if row["役職"] != orig["役職"]: changed["position"] = row["役職"]
                if row["雇用"] != orig["雇用"]: changed["employment_type"] = row["雇用"]
                if row["時給"] != orig["時給"]: changed["hourly_wage"] = int(row["時給"])
                if row["月給"] != orig["月給"]: changed["base_monthly_salary"] = int(row["月給"])
                if row["所定h/月"] != orig["所定h/月"]: changed["monthly_standard_hours"] = int(row["所定h/月"])
                if row["役職給/h"] != orig["役職給/h"]: changed["position_allowance_per_hour"] = int(row["役職給/h"])
                if row["週休日数"] != orig["週休日数"]: changed["weekly_off_days"] = int(row["週休日数"])
                if row["月目標h"] != orig["月目標h"]: changed["monthly_target_hours"] = int(row["月目標h"])
                if row["フレキ"] != orig["フレキ"]: changed["flexible"] = bool(row["フレキ"])
                if changed:
                    shift_db.update_staff(row["ID"], **changed)
                    cnt += 1
            st.success(f"✅ {cnt}名のスタッフ情報を更新しました")
            st.rerun()
    with col2:
        _csv_download(edited, f"mosh_staff_master_{date.today().strftime('%Y-%m')}.csv")


# ─────────────────────────────────────────
# 7. 店舗マスター管理（簡易・owner のみ）
# ─────────────────────────────────────────

def render_store_admin_tab(user: dict):
    if user.get("role") != "owner":
        st.error("この画面は owner 専用です")
        return
    if not require_payroll_unlock():
        return

    st.markdown("### 🏪 店舗マスター")
    stores = shift_db.get_stores_master(active_only=False)
    df = pd.DataFrame([{
        "コード": s["code"],
        "店舗名": s["display_name"],
        "月間売上目標": s["monthly_target_sales"],
        "目標人件比%": float(s["target_labor_cost_ratio"]),
        "FC": s["is_franchise"],
        "アクティブ": s["active"],
    } for s in stores])
    edited = st.data_editor(df, use_container_width=True, hide_index=True,
                              disabled=["コード"],
                              key="store_admin_editor")
    if st.button("💾 店舗情報を保存", type="primary"):
        for i, row in edited.iterrows():
            orig = df.iloc[i]
            changed = {}
            if row["店舗名"] != orig["店舗名"]: changed["display_name"] = row["店舗名"]
            if row["月間売上目標"] != orig["月間売上目標"]: changed["monthly_target_sales"] = int(row["月間売上目標"])
            if row["目標人件比%"] != orig["目標人件比%"]: changed["target_labor_cost_ratio"] = float(row["目標人件比%"])
            if row["FC"] != orig["FC"]: changed["is_franchise"] = bool(row["FC"])
            if row["アクティブ"] != orig["アクティブ"]: changed["active"] = bool(row["アクティブ"])
            if changed:
                shift_db.update_store_master(row["コード"], **changed)
        st.success("✅ 店舗情報を更新しました")
        st.rerun()
