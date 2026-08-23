"""Time-bucketed query counts from query_logs for admin dashboards."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_TRUNC_UNITS = frozenset({"day", "week", "month"})


def add_months_utc(anchor_first_of_month: datetime, months: int) -> datetime:
    m = anchor_first_of_month.month - 1 + months
    y = anchor_first_of_month.year + m // 12
    m = m % 12 + 1
    return datetime(y, m, 1, tzinfo=timezone.utc)


def _utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _norm_key(trunc: str, dt: datetime) -> str:
    dt = _utc(dt)
    if trunc == "day":
        return dt.date().isoformat()
    if trunc == "week":
        d = dt.date()
        monday = d - timedelta(days=d.weekday())
        return monday.isoformat()
    if trunc == "month":
        return f"{dt.year}-{dt.month:02d}-01"
    raise ValueError(f"unsupported trunc: {trunc}")


async def _counts_by_trunc(
    db: AsyncSession,
    trunc: str,
    start: datetime,
    end: datetime,
) -> dict[str, int]:
    if trunc not in _TRUNC_UNITS:
        raise ValueError(f"invalid trunc: {trunc!r}")

    # Parameterized SQL (PostgreSQL date_trunc); avoids dialect quirks with func.date_trunc in GROUP BY.
    stmt = text(
        """
        SELECT date_trunc(:trunc, created_at) AS bucket, count(id) AS cnt
        FROM query_logs
        WHERE created_at >= :start AND created_at <= :end
        GROUP BY 1
        ORDER BY 1
        """
    )
    rows = (
        await db.execute(
            stmt,
            {"trunc": trunc, "start": start, "end": end},
        )
    ).all()
    out: dict[str, int] = {}
    for row in rows:
        b = row.bucket
        if b is None:
            continue
        if isinstance(b, datetime):
            bdt = b
        elif isinstance(b, date):
            bdt = datetime.combine(b, time.min, tzinfo=timezone.utc)
        else:
            bdt = datetime.fromisoformat(str(b).replace("Z", "+00:00"))
        key = _norm_key(trunc, bdt)
        out[key] = int(row.cnt or 0)
    return out


def _point(bucket_key: str, trunc: str, count: int) -> dict[str, object]:
    if trunc == "day":
        d = date.fromisoformat(bucket_key)
        dt = datetime.combine(d, time.min, tzinfo=timezone.utc)
    elif trunc == "week":
        d = date.fromisoformat(bucket_key)
        dt = datetime.combine(d, time.min, tzinfo=timezone.utc)
    elif trunc == "month":
        y_str, mo_str, _ = bucket_key.split("-")
        dt = datetime(int(y_str), int(mo_str), 1, tzinfo=timezone.utc)
    else:
        raise ValueError(trunc)
    return {"bucketStart": dt.isoformat(), "count": int(count)}


async def build_query_series(db: AsyncSession, now: datetime | None = None) -> dict[str, list[dict[str, object]]]:
    now = now or datetime.now(timezone.utc)
    today = now.date()

    # --- last 7 calendar days (UTC), oldest → newest ---
    day_keys_7 = [(today - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
    start_7 = datetime.combine(today - timedelta(days=6), time.min, tzinfo=timezone.utc)
    c7 = await _counts_by_trunc(db, "day", start_7, now)
    last7_days = [_point(k, "day", c7.get(k, 0)) for k in day_keys_7]

    # --- last 30 calendar days ---
    day_keys_30 = [(today - timedelta(days=i)).isoformat() for i in range(29, -1, -1)]
    start_30 = datetime.combine(today - timedelta(days=29), time.min, tzinfo=timezone.utc)
    c30 = await _counts_by_trunc(db, "day", start_30, now)
    last30_days = [_point(k, "day", c30.get(k, 0)) for k in day_keys_30]

    # --- last 12 ISO weeks (Monday start), oldest → newest ---
    monday_this = today - timedelta(days=today.weekday())
    week_keys = [(monday_this - timedelta(weeks=i)).isoformat() for i in range(11, -1, -1)]
    start_w = datetime.combine(date.fromisoformat(week_keys[0]), time.min, tzinfo=timezone.utc)
    cw = await _counts_by_trunc(db, "week", start_w, now)
    last12_weeks = [_point(k, "week", cw.get(k, 0)) for k in week_keys]

    # --- last 12 calendar months (first of month), oldest → newest ---
    anchor = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    month_keys = []
    for i in range(11, -1, -1):
        dt_m = add_months_utc(anchor, -i)
        month_keys.append(f"{dt_m.year}-{dt_m.month:02d}-01")
    start_m = datetime.combine(date.fromisoformat(month_keys[0]), time.min, tzinfo=timezone.utc)
    cm = await _counts_by_trunc(db, "month", start_m, now)
    last12_months = [_point(k, "month", cm.get(k, 0)) for k in month_keys]

    return {
        "last7Days": last7_days,
        "last30Days": last30_days,
        "last12Weeks": last12_weeks,
        "last12Months": last12_months,
    }
