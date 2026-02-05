"""
Period date range helpers.
"""
from datetime import datetime, time, timedelta
from typing import Any

from dateutil.relativedelta import relativedelta
from django.utils import timezone


def get_period_labels() -> dict[str, str]:
    """Get human-readable date ranges for each period (for tooltips)."""
    today = timezone.now().date()

    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)

    def fmt(start, end):
        if start.year == end.year:
            return f"{start.strftime('%d.%m')} — {end.strftime('%d.%m.%Y')}"
        return f"{start.strftime('%d.%m.%Y')} — {end.strftime('%d.%m.%Y')}"

    quarter_start = today - relativedelta(months=3)
    half_year_start = today - relativedelta(months=6)

    return {
        'all': 'За всё время',
        'week': fmt(week_start, today),
        'month': fmt(month_start, today),
        'quarter': fmt(quarter_start, today),
        'half_year': fmt(half_year_start, today),
    }


def get_period_dates(
    period: str,
    date_from: str | None = None,
    date_to: str | None = None
) -> tuple[Any, Any, Any, Any]:
    """Get start/end dates for period, plus previous period for delta."""
    today = timezone.now().date()

    handlers = {
        'all': _get_all_dates,
        'week': _get_week_dates,
        'month': _get_month_dates,
        'quarter': _get_quarter_dates,
        'half_year': _get_half_year_dates,
    }

    if period == 'custom' and date_from and date_to:
        return _get_custom_dates(date_from, date_to)

    handler = handlers.get(period)
    if handler:
        return handler(today)

    return None, None, None, None


def _get_all_dates(today):
    """Get all time period dates (no filtering)."""
    # Return None for start - means no date filter
    # For delta comparison, use last month
    month_start = today.replace(day=1)
    prev_month_start = (month_start - timedelta(days=1)).replace(day=1)
    prev_start = timezone.make_aware(datetime.combine(prev_month_start, time.min))
    prev_end = timezone.make_aware(datetime.combine(month_start, time.min))
    return None, prev_start, prev_end, None


def _get_week_dates(today):
    """Get week period dates."""
    week_start = today - timedelta(days=today.weekday())
    start = timezone.make_aware(datetime.combine(week_start, time.min))
    prev_start = timezone.make_aware(
        datetime.combine(week_start - timedelta(days=7), time.min)
    )
    return start, prev_start, start, None


def _get_month_dates(today):
    """Get month period dates."""
    month_start = today.replace(day=1)
    start = timezone.make_aware(datetime.combine(month_start, time.min))
    prev_month_start = (month_start - timedelta(days=1)).replace(day=1)
    prev_start = timezone.make_aware(datetime.combine(prev_month_start, time.min))
    return start, prev_start, start, None


def _get_quarter_dates(today):
    """Get quarter (last 3 months) period dates."""
    start = today - relativedelta(months=3)
    start_dt = timezone.make_aware(datetime.combine(start, time.min))
    prev_start = today - relativedelta(months=6)
    prev_start_dt = timezone.make_aware(datetime.combine(prev_start, time.min))
    return start_dt, prev_start_dt, start_dt, None


def _get_half_year_dates(today):
    """Get half-year (last 6 months) period dates."""
    start = today - relativedelta(months=6)
    start_dt = timezone.make_aware(datetime.combine(start, time.min))
    prev_start = today - relativedelta(months=12)
    prev_start_dt = timezone.make_aware(datetime.combine(prev_start, time.min))
    return start_dt, prev_start_dt, start_dt, None


def _get_custom_dates(date_from: str, date_to: str):
    """Get custom period dates."""
    try:
        from_date = datetime.strptime(date_from, '%Y-%m-%d').date()
        to_date = datetime.strptime(date_to, '%Y-%m-%d').date()
        start = timezone.make_aware(datetime.combine(from_date, time.min))
        end = timezone.make_aware(datetime.combine(to_date + timedelta(days=1), time.min))
        period_days = (to_date - from_date).days + 1
        prev_start = timezone.make_aware(
            datetime.combine(from_date - timedelta(days=period_days), time.min)
        )
        return start, prev_start, start, end
    except (ValueError, TypeError):
        return None, None, None, None


def get_days_count(
    period: str,
    date_from: str | None,
    date_to: str | None
) -> int:
    """Get number of days for chart granularity."""
    mapping = {'week': 7, 'month': 30, 'quarter': 90, 'half_year': 180, 'all': 365}
    if period in mapping:
        return mapping[period]
    if period == 'custom' and date_from and date_to:
        try:
            f = datetime.strptime(date_from, '%Y-%m-%d').date()
            t = datetime.strptime(date_to, '%Y-%m-%d').date()
            return (t - f).days + 1
        except (ValueError, TypeError):
            pass
    return 30
