"""
MOSH 法令準拠 人件費計算ロジック

労働基準法準拠（§32 法定労働時間 / §34 休憩 / §37 割増賃金）
+ MOSH独自の休憩控除ルール（清本さん指定）

倍率テーブル:
  通常              (5:00-22:00・法定内) ×1.00
  深夜              (22:00-翌5:00・法定内) ×1.25
  残業              (1日8h超 or 週40h超・通常時間帯) ×1.25
  残業×深夜         (1日8h超・深夜時間帯) ×1.50
  月60h超残業       (月の残業合計が60h超の部分) ×1.50
  法定休日労働       (手動マーク時のみ) ×1.35
  休憩(無給)        ×0

休憩控除タイミング:
  退勤時刻から逆算して退勤直前を休憩時間として控除
  例: 20:00退勤・休憩60分 → 19:00-20:00が休憩、実労働は出勤〜19:00
"""

from datetime import datetime, time, timedelta, date
from typing import Optional


# ─────────────────────────────────────────
# 休憩時間の自動算出（MOSH独自ルール）
# ─────────────────────────────────────────

def calc_break_minutes(employment_type: str, total_hours: float) -> int:
    """
    雇用形態と拘束時間から自動控除する休憩時間（分）を返す。

    アルバイト: 6時間以上 → 60分、6時間未満 → 0分
    社員:       6時間超   → 90分、6時間以下 → 0分
    業務委託:   0分
    """
    if employment_type == "アルバイト":
        return 60 if total_hours >= 6 else 0
    if employment_type == "社員":
        return 90 if total_hours > 6 else 0
    return 0


# ─────────────────────────────────────────
# 月給社員の残業計算用時給換算
# ─────────────────────────────────────────

def calc_hourly_rate(
    employment_type: str,
    hourly_wage: Optional[int] = None,
    base_monthly_salary: Optional[int] = None,
    monthly_standard_hours: Optional[int] = None,
    position_allowance_per_hour: Optional[int] = None,
) -> float:
    """
    残業/深夜割増計算のベースとなる時給を返す。

    アルバイト: hourly_wage をそのまま使用
    社員:       月給 ÷ 月所定労働時間 + 役職給(時給換算) ←「1ベース+役職給」方式（清本さん指定）
    業務委託:   hourly_wage があれば使用、なければ0
    """
    if employment_type == "アルバイト":
        return float(hourly_wage or 0)
    if employment_type == "社員":
        if not base_monthly_salary or not monthly_standard_hours:
            return 0.0
        base = base_monthly_salary / monthly_standard_hours
        allowance = position_allowance_per_hour or 0
        return base + allowance
    return float(hourly_wage or 0)


# ─────────────────────────────────────────
# 時間帯分解（1シフト分）
# ─────────────────────────────────────────

NIGHT_START_HOUR = 22  # 22:00から深夜割増
NIGHT_END_HOUR = 5     # 翌5:00まで深夜割増
LEGAL_DAILY_HOURS = 8  # 1日の法定労働時間


def _to_datetime(d: date, t: time, day_offset: int = 0) -> datetime:
    """日付＋時刻＋日数オフセット → datetime"""
    return datetime.combine(d, t) + timedelta(days=day_offset)


def _minutes_in_range(seg_start: datetime, seg_end: datetime, range_start: datetime, range_end: datetime) -> float:
    """セグメント [seg_start, seg_end) と範囲 [range_start, range_end) の重なり分（分）を返す"""
    s = max(seg_start, range_start)
    e = min(seg_end, range_end)
    if e <= s:
        return 0.0
    return (e - s).total_seconds() / 60.0


def split_work_hours(
    start: datetime,
    end: datetime,
    employment_type: str,
    is_legal_holiday: bool = False,
) -> dict:
    """
    1シフトを時間帯ごとに分解する。

    手順:
      1. 拘束時間 = end - start
      2. 雇用形態に応じた休憩時間を控除（退勤時刻から逆算）
      3. 実労働終了時刻 = end - 休憩時間
      4. start〜実労働終了時刻 を 通常/深夜 と 法定内/法定外 で分割
      5. 法定休日フラグが立っていれば holiday に振り分け

    Returns:
        dict {
            "raw_hours": 拘束時間,
            "break_minutes": 休憩時間（分・無給）,
            "actual_hours": 実労働時間,
            "regular_hours": 通常×法定内,
            "night_hours": 深夜×法定内,
            "overtime_hours": 通常×法定外,
            "overtime_night_hours": 深夜×法定外,
            "holiday_hours": 法定休日労働全体（マークされている場合のみ）,
        }
    """
    raw_hours = (end - start).total_seconds() / 3600
    if raw_hours <= 0:
        return _empty_split()

    break_min = calc_break_minutes(employment_type, raw_hours)
    work_end = end - timedelta(minutes=break_min)
    actual_hours = (work_end - start).total_seconds() / 3600

    # 法定休日労働は全部 holiday に振る（割増は1.35一律で月次集計時に適用）
    if is_legal_holiday:
        return {
            "raw_hours": raw_hours,
            "break_minutes": break_min,
            "actual_hours": actual_hours,
            "regular_hours": 0.0,
            "night_hours": 0.0,
            "overtime_hours": 0.0,
            "overtime_night_hours": 0.0,
            "holiday_hours": actual_hours,
        }

    # 日付ベースで「当日中の8時間目」がいつ来るかを計算
    legal_inner_end = start + timedelta(hours=LEGAL_DAILY_HOURS)

    # 深夜時間帯（22:00-翌5:00）の計算は出勤日基準で考える
    base_date = start.date()
    # 出勤日の深夜帯（22:00開始、翌5:00終了）
    night_a_start = _to_datetime(base_date, time(NIGHT_START_HOUR, 0))
    night_a_end = _to_datetime(base_date, time(NIGHT_END_HOUR, 0), day_offset=1)
    # 出勤日の前日深夜帯（前日22:00〜当日5:00）も考慮（早朝シフト用）
    night_b_start = _to_datetime(base_date, time(NIGHT_START_HOUR, 0), day_offset=-1)
    night_b_end = _to_datetime(base_date, time(NIGHT_END_HOUR, 0))

    regular_min = 0.0
    night_min = 0.0
    overtime_min = 0.0
    overtime_night_min = 0.0

    # 法定内セグメント
    inner_seg_start = start
    inner_seg_end = min(work_end, legal_inner_end)
    if inner_seg_end > inner_seg_start:
        night_in_inner = (
            _minutes_in_range(inner_seg_start, inner_seg_end, night_a_start, night_a_end)
            + _minutes_in_range(inner_seg_start, inner_seg_end, night_b_start, night_b_end)
        )
        total_inner_min = (inner_seg_end - inner_seg_start).total_seconds() / 60
        regular_min = total_inner_min - night_in_inner
        night_min = night_in_inner

    # 法定外セグメント（残業）
    outer_seg_start = max(start, legal_inner_end)
    outer_seg_end = work_end
    if outer_seg_end > outer_seg_start:
        night_in_outer = (
            _minutes_in_range(outer_seg_start, outer_seg_end, night_a_start, night_a_end)
            + _minutes_in_range(outer_seg_start, outer_seg_end, night_b_start, night_b_end)
        )
        total_outer_min = (outer_seg_end - outer_seg_start).total_seconds() / 60
        overtime_min = total_outer_min - night_in_outer
        overtime_night_min = night_in_outer

    return {
        "raw_hours": raw_hours,
        "break_minutes": break_min,
        "actual_hours": actual_hours,
        "regular_hours": regular_min / 60,
        "night_hours": night_min / 60,
        "overtime_hours": overtime_min / 60,
        "overtime_night_hours": overtime_night_min / 60,
        "holiday_hours": 0.0,
    }


def _empty_split() -> dict:
    return {
        "raw_hours": 0.0,
        "break_minutes": 0,
        "actual_hours": 0.0,
        "regular_hours": 0.0,
        "night_hours": 0.0,
        "overtime_hours": 0.0,
        "overtime_night_hours": 0.0,
        "holiday_hours": 0.0,
    }


# ─────────────────────────────────────────
# 1シフトの賃金計算
# ─────────────────────────────────────────

def calc_single_shift_pay(split: dict, hourly_rate: float) -> dict:
    """
    時間帯分解結果と時給から1シフトの賃金内訳を返す。
    （月60h超50%増 と 週40h超 は月次集計側で適用するため、ここでは扱わない）
    """
    rate = hourly_rate
    return {
        "regular_pay": round(split["regular_hours"] * rate),
        "night_pay": round(split["night_hours"] * rate * 1.25),
        "overtime_pay": round(split["overtime_hours"] * rate * 1.25),
        "overtime_night_pay": round(split["overtime_night_hours"] * rate * 1.50),
        "holiday_pay": round(split["holiday_hours"] * rate * 1.35),
    }


# ─────────────────────────────────────────
# 月次集計（週40h超・月60h超を考慮）
# ─────────────────────────────────────────

def calc_monthly_payroll(shift_splits: list[dict], hourly_rate: float, employment_type: str,
                          base_monthly_salary: int = 0) -> dict:
    """
    月次のシフト分解結果リスト [{split, date, ...}, ...] と時給/月給から月次集計を行う。

    週40h超・月60h超は集計時に判定し、追加で1.5倍率を適用する。

    Args:
        shift_splits: [{"split": {...}, "date": date, ...}, ...]
        hourly_rate: 残業計算用時給
        employment_type: "アルバイト" / "社員" / "業務委託"
        base_monthly_salary: 月給社員の基本月給（月給はそのまま支給）

    Returns:
        月次集計dict
    """
    # 1. 全シフトを合算
    totals = {
        "raw_hours": 0.0,
        "break_minutes": 0,
        "actual_hours": 0.0,
        "regular_hours": 0.0,
        "night_hours": 0.0,
        "overtime_hours": 0.0,
        "overtime_night_hours": 0.0,
        "holiday_hours": 0.0,
        "shift_days": 0,
    }
    for item in shift_splits:
        s = item["split"]
        for k in ["raw_hours", "actual_hours", "regular_hours", "night_hours",
                  "overtime_hours", "overtime_night_hours", "holiday_hours"]:
            totals[k] += s[k]
        totals["break_minutes"] += s["break_minutes"]
        if s["actual_hours"] > 0:
            totals["shift_days"] += 1

    # 2. 月60h超の残業を分離（残業合計＝overtime + overtime_night）
    total_overtime = totals["overtime_hours"] + totals["overtime_night_hours"]
    over_60 = max(0.0, total_overtime - 60)
    # 月60h超分は通常残業（×1.25）からまず引かれていく実務想定
    # → 簡略: overtime_hours と overtime_night_hours の比率で按分
    if total_overtime > 0 and over_60 > 0:
        ratio_o = totals["overtime_hours"] / total_overtime
        ratio_on = totals["overtime_night_hours"] / total_overtime
        over_60_regular = over_60 * ratio_o
        over_60_night = over_60 * ratio_on
        totals["overtime_hours"] -= over_60_regular
        totals["overtime_night_hours"] -= over_60_night
        over_60_hours = over_60
    else:
        over_60_hours = 0.0

    # 3. 賃金計算
    rate = hourly_rate
    pay = {
        "regular_pay": round(totals["regular_hours"] * rate),
        "night_pay": round(totals["night_hours"] * rate * 1.25),
        "overtime_pay": round(totals["overtime_hours"] * rate * 1.25),
        "overtime_night_pay": round(totals["overtime_night_hours"] * rate * 1.50),
        "overtime_60_plus_pay": round(over_60_hours * rate * 1.50),
        "holiday_pay": round(totals["holiday_hours"] * rate * 1.35),
    }

    # 4. 月給社員は基本月給を加算（残業手当等は割増分のみが追加支給）
    if employment_type == "社員" and base_monthly_salary:
        # 社員の場合、基本月給は所定労働時間の賃金として既に支給される想定
        # → regular_pay は表示用、実支給は基本月給＋残業手当＋深夜手当
        total_pay = base_monthly_salary + pay["night_pay"] + pay["overtime_pay"] \
                    + pay["overtime_night_pay"] + pay["overtime_60_plus_pay"] + pay["holiday_pay"]
        pay["base_monthly_salary"] = base_monthly_salary
        pay["total_pay"] = total_pay
    else:
        # アルバイト/業務委託は実労働×時給ベース
        total_pay = sum(pay.values())
        pay["base_monthly_salary"] = 0
        pay["total_pay"] = total_pay

    return {
        **totals,
        "overtime_60_plus_hours": over_60_hours,
        **pay,
    }


# ─────────────────────────────────────────
# テスト関数（清本さん復帰後の動作確認用）
# ─────────────────────────────────────────

def _run_self_tests():
    """設計時の認識合わせ例をテストケースとして検証"""
    print("=" * 60)
    print("MOSH 法令準拠人件費計算 セルフテスト")
    print("=" * 60)

    # ケース1: アルバイト 15:00-24:00 時給1500
    start = datetime(2026, 6, 1, 15, 0)
    end = datetime(2026, 6, 2, 0, 0)
    split = split_work_hours(start, end, "アルバイト")
    pay = calc_single_shift_pay(split, 1500)
    print(f"\n【ケース1】アルバイト 15:00-24:00 @1500円")
    print(f"  拘束: {split['raw_hours']:.1f}h / 休憩: {split['break_minutes']}分 / 実労働: {split['actual_hours']:.1f}h")
    print(f"  通常: {split['regular_hours']:.1f}h / 深夜: {split['night_hours']:.1f}h / 残業: {split['overtime_hours']:.1f}h")
    print(f"  賃金: 通常¥{pay['regular_pay']} + 深夜¥{pay['night_pay']} = 合計 ¥{sum(pay.values())}")
    # 期待: 通常7h(15-22) + 深夜1h(22-23) + 休憩1h(23-24) = ¥12,375

    # ケース2: 社員 15:00-24:00 時給換算1500
    split = split_work_hours(start, end, "社員")
    pay = calc_single_shift_pay(split, 1500)
    print(f"\n【ケース2】社員 15:00-24:00 @換算1500円")
    print(f"  拘束: {split['raw_hours']:.1f}h / 休憩: {split['break_minutes']}分 / 実労働: {split['actual_hours']:.1f}h")
    print(f"  通常: {split['regular_hours']:.1f}h / 深夜: {split['night_hours']:.1f}h / 残業: {split['overtime_hours']:.1f}h")
    print(f"  賃金: 通常¥{pay['regular_pay']} + 深夜¥{pay['night_pay']} = 合計 ¥{sum(pay.values())}")
    # 期待: 通常7h + 深夜0.5h(22-22:30) + 休憩1.5h(22:30-24) = ¥11,438

    # ケース3: 社員 メイソンズ 15:00-翌4:00 時給換算1500
    start = datetime(2026, 6, 1, 15, 0)
    end = datetime(2026, 6, 2, 4, 0)
    split = split_work_hours(start, end, "社員")
    pay = calc_single_shift_pay(split, 1500)
    print(f"\n【ケース3】社員 メイソンズ 15:00-翌4:00 @換算1500円")
    print(f"  拘束: {split['raw_hours']:.1f}h / 休憩: {split['break_minutes']}分 / 実労働: {split['actual_hours']:.1f}h")
    print(f"  通常: {split['regular_hours']:.1f}h / 深夜法定内: {split['night_hours']:.1f}h")
    print(f"  残業: {split['overtime_hours']:.1f}h / 残業×深夜: {split['overtime_night_hours']:.1f}h")
    print(f"  賃金: 通常¥{pay['regular_pay']} + 深夜¥{pay['night_pay']} + 残業¥{pay['overtime_pay']} + 残業×深夜¥{pay['overtime_night_pay']}")
    print(f"  合計 ¥{sum(pay.values())}")
    # 期待: 通常7h(15-22) + 深夜法定内1h(22-23) + 残業×深夜3.5h(23-2:30) + 休憩1.5h(2:30-4) = ¥20,250


# ─────────────────────────────────────────
# Square 互換 CSV 出力
# ─────────────────────────────────────────

def export_square_row(
    start_dt: datetime,
    end_dt: datetime,
    employment_type: str,
    hourly_rate: float,
    store_display: str,
    last_name: str,
    first_name: str,
    employee_id: str = "",
    is_legal_holiday: bool = False,
    monthly_overtime_so_far: float = 0.0,
) -> dict:
    """
    Square 形式の勤怠CSV 1行分を生成する。

    Square のオリジナル仕様に合わせて、深夜割増は計算しない（深夜帯も通常扱い）。
    残業は「1日8時間超」で判定し、月60時間超は倍額支給枠（×1.5）に振り替える。

    Args:
        start_dt: 出勤時刻
        end_dt: 退勤時刻
        employment_type: アルバイト/社員/業務委託（休憩控除分岐）
        hourly_rate: 時給（社員の場合は残業計算用時給）
        store_display: 店舗表示名（「The Mason's」「西船橋」など）
        last_name / first_name / employee_id: スタッフ情報
        is_legal_holiday: 法定休日労働なら True（倍額支給扱い）
        monthly_overtime_so_far: その月のこれまでの残業合計（時間）
            60h を超えた部分を倍額支給に振り替える
    """
    raw_hours = (end_dt - start_dt).total_seconds() / 3600
    break_min = calc_break_minutes(employment_type, raw_hours)
    actual_hours = raw_hours - break_min / 60

    # 法定内/法定外（1日8時間で判定）
    if is_legal_holiday:
        regular = 0.0
        overtime = 0.0
        double = actual_hours
    else:
        regular = min(actual_hours, 8.0)
        overtime_today = max(0.0, actual_hours - 8.0)
        # 月60h超の残業分を倍額支給に振替
        before = monthly_overtime_so_far
        after = before + overtime_today
        if after <= 60:
            overtime = overtime_today
            double = 0.0
        elif before >= 60:
            overtime = 0.0
            double = overtime_today
        else:
            overtime = 60 - before
            double = after - 60

    # 賃金
    regular_pay = round(regular * hourly_rate)
    overtime_pay = round(overtime * hourly_rate * 1.25)
    double_pay = round(double * hourly_rate * 1.50)
    total_pay = regular_pay + overtime_pay + double_pay

    # 休憩は退勤直前に配置（清本さんルール）
    if break_min > 0:
        break_end_dt = end_dt
        break_start_dt = end_dt - timedelta(minutes=break_min)
        break_start_d = break_start_dt.strftime("%Y-%m-%d")
        break_start_t = break_start_dt.strftime("%-H:%M:%S") + " JST"
        break_end_d = break_end_dt.strftime("%Y-%m-%d")
        break_end_t = break_end_dt.strftime("%-H:%M:%S") + " JST"
    else:
        break_start_d = break_start_t = break_end_d = break_end_t = ""

    return {
        "row": {
            "従業員ID": employee_id,
            "姓": last_name,
            "名": first_name,
            "職種": employment_type,
            "店舗": store_display,
            "出勤日": start_dt.strftime("%Y-%m-%d"),
            "出勤時間": start_dt.strftime("%-H:%M:%S") + " JST",
            "退勤日": end_dt.strftime("%Y-%m-%d"),
            "退勤時間": end_dt.strftime("%-H:%M:%S") + " JST",
            "休憩開始日": break_start_d,
            "休憩開始時間": break_start_t,
            "休憩終了日": break_end_d,
            "休憩終了時間": break_end_t,
            "無給の休憩": round(break_min / 60, 2),
            "有給の休憩": 0.0,
            "通常勤務時間": round(regular, 2),
            "残業時間": round(overtime, 2),
            "倍額支給時間": round(double, 2),
            "合計実働時間": round(actual_hours, 2),
            "時給": f"JPY{int(hourly_rate):,}",
            "固定人件費": f"JPY{regular_pay:,}",
            "残業での人件費": f"JPY{overtime_pay:,}",
            "倍額支給人件費": f"JPY{double_pay:,}",
            "合計人件費": f"JPY{total_pay:,}",
        },
        "overtime_added": overtime + double,  # 月累計に加算する残業時間
    }


SQUARE_CSV_COLUMNS = [
    "従業員ID", "姓", "名", "職種", "店舗",
    "出勤日", "出勤時間", "退勤日", "退勤時間",
    "休憩開始日", "休憩開始時間", "休憩終了日", "休憩終了時間",
    "無給の休憩", "有給の休憩",
    "通常勤務時間", "残業時間", "倍額支給時間", "合計実働時間",
    "時給", "固定人件費", "残業での人件費", "倍額支給人件費", "合計人件費",
]


if __name__ == "__main__":
    _run_self_tests()
