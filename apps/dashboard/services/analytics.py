"""
Analytics and KPI business logic.
"""
import json
from collections import defaultdict
from datetime import datetime, time, timedelta
from typing import Any

from dateutil.relativedelta import relativedelta
from django.db.models import Avg, QuerySet
from django.http import HttpRequest
from django.utils import timezone

from apps.companies.models import Company
from apps.reviews.models import Review


# === Period helpers ===

def get_period_labels() -> dict[str, str]:
    """Get human-readable date ranges for each period (for tooltips)."""
    today = timezone.now().date()

    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    quarter_month = ((today.month - 1) // 3) * 3 + 1
    quarter_start = today.replace(month=quarter_month, day=1)
    half_year_start = today - relativedelta(months=6)

    def fmt(start, end):
        if start.year == end.year:
            return f"{start.strftime('%d.%m')} — {end.strftime('%d.%m.%Y')}"
        return f"{start.strftime('%d.%m.%Y')} — {end.strftime('%d.%m.%Y')}"

    return {
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
    """Get quarter period dates."""
    quarter_month = ((today.month - 1) // 3) * 3 + 1
    quarter_start = today.replace(month=quarter_month, day=1)
    start = timezone.make_aware(datetime.combine(quarter_start, time.min))
    prev_quarter_start = quarter_start - relativedelta(months=3)
    prev_start = timezone.make_aware(datetime.combine(prev_quarter_start, time.min))
    return start, prev_start, start, None


def _get_half_year_dates(today):
    """Get half year period dates."""
    half_year_start = today - relativedelta(months=6)
    start = timezone.make_aware(datetime.combine(half_year_start, time.min))
    prev_start = timezone.make_aware(
        datetime.combine(half_year_start - relativedelta(months=6), time.min)
    )
    return start, prev_start, start, None


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


# === KPI Calculations ===

def calculate_kpi_metrics(reviews_qs: QuerySet) -> dict:
    """Calculate KPI metrics from a queryset of reviews."""
    total_count = reviews_qs.count()
    if total_count == 0:
        return _empty_kpi_metrics()

    avg_rating = reviews_qs.aggregate(avg=Avg('rating'))['avg'] or 0
    promoters = reviews_qs.filter(rating=5).count()
    detractors = reviews_qs.filter(rating__lte=3).count()
    nps = ((promoters - detractors) / total_count * 100)

    negative_count = detractors
    negative_share = (negative_count / total_count * 100)

    negative_unanswered = reviews_qs.filter(rating__lte=3, response='').count()
    negative_unanswered_share = (
        (negative_unanswered / negative_count * 100) if negative_count > 0 else 0
    )

    avg_response_hours = _calc_avg_response_time(reviews_qs)

    return {
        'avg_rating': round(avg_rating, 2),
        'nps': round(nps, 1),
        'negative_share': round(negative_share, 1),
        'negative_unanswered_count': negative_unanswered,
        'negative_unanswered_share': round(negative_unanswered_share, 1),
        'avg_response_time_hours': round(avg_response_hours, 1),
        'total_count': total_count,
        'promoters': promoters,
        'detractors': detractors,
        'negative_count': negative_count,
    }


def _empty_kpi_metrics() -> dict:
    """Return empty KPI metrics."""
    return {
        'avg_rating': 0, 'nps': 0, 'negative_share': 0,
        'negative_unanswered_count': 0, 'negative_unanswered_share': 0,
        'avg_response_time_hours': 0, 'total_count': 0,
        'promoters': 0, 'detractors': 0, 'negative_count': 0,
    }


def _calc_avg_response_time(reviews_qs: QuerySet) -> float:
    """Calculate average response time in hours."""
    reviews_with_response = reviews_qs.filter(response_at__isnull=False)
    if not reviews_with_response.exists():
        return 0

    total_hours = 0
    count = 0
    for r in reviews_with_response.values('created_at', 'response_at'):
        if r['response_at'] and r['created_at']:
            delta = r['response_at'] - r['created_at']
            total_hours += delta.total_seconds() / 3600
            count += 1

    return total_hours / count if count > 0 else 0


def calculate_reputation_risk(
    company: Company,
    current_metrics: dict,
    period_start: Any
) -> int:
    """Calculate reputation risk score (0-100)."""
    share_negative = (
        current_metrics['negative_share'] / 100
        if current_metrics['total_count'] > 0 else 0
    )
    share_unanswered = (
        current_metrics['negative_unanswered_share'] / 100
        if current_metrics['negative_count'] > 0 else 0
    )

    recent_start = timezone.now() - timedelta(days=7)
    recent_reviews = Review.objects.filter(company=company, created_at__gte=recent_start)
    recent_total = recent_reviews.count()
    recent_negative = recent_reviews.filter(rating__lte=3).count()
    recent_rate = (recent_negative / recent_total) if recent_total > 0 else 0

    risk = 50 * share_negative + 30 * share_unanswered + 20 * recent_rate
    return round(min(risk, 100), 0)


# === Analytics Data ===

def get_analytics_data(
    company: Company,
    period: str = 'month',
    date_from: str | None = None,
    date_to: str | None = None
) -> dict:
    """Get analytics data for charts and KPI."""
    start_date, prev_start, prev_end, end_date = get_period_dates(
        period, date_from, date_to
    )

    reviews = _filter_reviews_by_period(company, start_date, end_date)
    prev_reviews = _get_previous_reviews(company, prev_start, prev_end, start_date)

    current_kpi = calculate_kpi_metrics(reviews)
    prev_kpi = calculate_kpi_metrics(prev_reviews)

    deltas = _calc_deltas(current_kpi, prev_kpi)
    reputation_risk = calculate_reputation_risk(company, current_kpi, start_date)

    chart_data = _build_chart_data(reviews)
    days_count = _get_days_count(period, date_from, date_to)
    daily_data = get_daily_reviews(company, days_count, period, date_from, date_to)

    return {
        'total_count': current_kpi['total_count'],
        **current_kpi,
        'avg_rating_delta': deltas['rating'],
        'nps_delta': deltas['nps'],
        'reputation_risk': reputation_risk,
        **chart_data,
        'daily_data': daily_data,
    }


def _filter_reviews_by_period(
    company: Company,
    start_date: Any,
    end_date: Any
) -> QuerySet:
    """Filter reviews by date range."""
    reviews = Review.objects.filter(company=company)
    if start_date:
        reviews = reviews.filter(created_at__gte=start_date)
    if end_date:
        reviews = reviews.filter(created_at__lt=end_date)
    return reviews


def _get_previous_reviews(
    company: Company,
    prev_start: Any,
    prev_end: Any,
    start_date: Any
) -> QuerySet:
    """Get reviews from previous period."""
    if prev_start and prev_end:
        return Review.objects.filter(
            company=company,
            created_at__gte=prev_start,
            created_at__lt=prev_end
        )
    if start_date:
        return Review.objects.none()
    return Review.objects.filter(company=company)


def _calc_deltas(current: dict, prev: dict) -> dict:
    """Calculate metric deltas."""
    has_prev = prev['total_count'] > 0
    return {
        'rating': round(current['avg_rating'] - prev['avg_rating'], 2) if has_prev else None,
        'nps': round(current['nps'] - prev['nps'], 1) if has_prev else None,
    }


def _build_chart_data(reviews: QuerySet) -> dict:
    """Build data for all charts."""
    rating_counts = defaultdict(int)
    source_counts = defaultdict(int)
    sentiment_counts = {'positive': 0, 'neutral': 0, 'negative': 0}

    for r in reviews.values('rating', 'source'):
        rating_counts[r['rating']] += 1
        source_counts[r['source']] += 1
        if r['rating'] == 5:
            sentiment_counts['positive'] += 1
        elif r['rating'] == 4:
            sentiment_counts['neutral'] += 1
        else:
            sentiment_counts['negative'] += 1

    return {
        'rating_data': _build_rating_data(rating_counts),
        'source_data': _build_source_data(source_counts),
        'sentiment_data': _build_sentiment_data(sentiment_counts),
        'sentiment_counts': sentiment_counts,
    }


def _build_rating_data(counts: dict) -> dict:
    """Build rating chart data."""
    return {
        'labels': ['5 звёзд', '4 звезды', '3 звезды', '2 звезды', '1 звезда'],
        'values': [counts.get(i, 0) for i in [5, 4, 3, 2, 1]],
        'colors': ['#22c55e', '#84cc16', '#fbbf24', '#f97316', '#ef4444'],
    }


def _build_source_data(counts: dict) -> dict:
    """Build source chart data."""
    names = {
        'internal': 'Наш сервис', 'yandex': 'Яндекс Карты',
        '2gis': '2ГИС', 'google': 'Google Maps', 'tripadvisor': 'TripAdvisor',
    }
    colors = {
        'internal': '#f97316', 'yandex': '#facc15', '2gis': '#1fab54',
        'google': '#4285f4', 'tripadvisor': '#00af87',
    }
    data = {'labels': [], 'values': [], 'colors': []}
    for src, cnt in sorted(counts.items(), key=lambda x: -x[1]):
        if cnt > 0:
            data['labels'].append(names.get(src, src))
            data['values'].append(cnt)
            data['colors'].append(colors.get(src, '#999999'))
    return data


def _build_sentiment_data(counts: dict) -> dict:
    """Build sentiment chart data."""
    return {
        'labels': ['Позитив', 'Нейтральный', 'Негатив'],
        'values': [counts['positive'], counts['neutral'], counts['negative']],
        'colors': ['#22c55e', '#fbbf24', '#ef4444'],
    }


def _get_days_count(
    period: str,
    date_from: str | None,
    date_to: str | None
) -> int:
    """Get number of days for chart granularity."""
    mapping = {'week': 7, 'month': 30, 'quarter': 90, 'half_year': 180}
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


# === Daily Reviews ===

def get_daily_reviews(
    company: Company,
    days: int,
    period: str,
    date_from: str | None = None,
    date_to: str | None = None
) -> dict:
    """Get review counts by day/week/month depending on period length."""
    start_date, end_date = _get_chart_date_range(period, date_from, date_to, days)

    if days <= 14:
        return _get_daily_grouped(company, start_date, end_date, days)
    elif days <= 90:
        return _get_weekly_grouped(company, start_date, end_date)
    else:
        return _get_monthly_grouped(company, start_date, end_date)


def _get_chart_date_range(
    period: str,
    date_from: str | None,
    date_to: str | None,
    days: int
) -> tuple:
    """Get date range for chart."""
    today = timezone.now().date()

    if period == 'custom' and date_from and date_to:
        try:
            return (
                datetime.strptime(date_from, '%Y-%m-%d').date(),
                datetime.strptime(date_to, '%Y-%m-%d').date()
            )
        except (ValueError, TypeError):
            pass

    ranges = {
        'week': (today - timedelta(days=today.weekday()), today),
        'month': (today.replace(day=1), today),
        'quarter': (
            today.replace(month=((today.month - 1) // 3) * 3 + 1, day=1),
            today
        ),
        'half_year': (today - relativedelta(months=6), today),
    }
    return ranges.get(period, (today - timedelta(days=30), today))


def _get_daily_grouped(
    company: Company,
    start_date,
    end_date,
    days: int
) -> dict:
    """Get daily grouped review counts."""
    day_names = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
    labels, values = [], []

    for i in range(days):
        day = start_date + timedelta(days=i)
        if day > end_date:
            break
        start = timezone.make_aware(datetime.combine(day, time.min))
        end = timezone.make_aware(datetime.combine(day + timedelta(days=1), time.min))
        count = Review.objects.filter(
            company=company, created_at__gte=start, created_at__lt=end
        ).count()
        labels.append(day_names[day.weekday()] if days <= 7 else day.strftime('%d.%m'))
        values.append(count)

    return {'labels': labels, 'values': values}


def _get_weekly_grouped(company: Company, start_date, end_date) -> dict:
    """Get weekly grouped review counts."""
    labels, values = [], []
    current = start_date - timedelta(days=start_date.weekday())

    while current <= end_date:
        week_end = current + timedelta(days=7)
        start = timezone.make_aware(datetime.combine(current, time.min))
        end = timezone.make_aware(datetime.combine(week_end, time.min))
        count = Review.objects.filter(
            company=company, created_at__gte=start, created_at__lt=end
        ).count()
        labels.append(current.strftime('%d.%m'))
        values.append(count)
        current += timedelta(days=7)

    return {'labels': labels, 'values': values}


def _get_monthly_grouped(company: Company, start_date, end_date) -> dict:
    """Get monthly grouped review counts."""
    month_names = ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн',
                   'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек']
    labels, values = [], []
    current = start_date.replace(day=1)

    while current <= end_date:
        month, year = current.month, current.year
        start = timezone.make_aware(datetime(year, month, 1, 0, 0, 0))
        if month == 12:
            end = timezone.make_aware(datetime(year + 1, 1, 1, 0, 0, 0))
        else:
            end = timezone.make_aware(datetime(year, month + 1, 1, 0, 0, 0))
        count = Review.objects.filter(
            company=company, created_at__gte=start, created_at__lt=end
        ).count()
        labels.append(month_names[month - 1])
        values.append(count)
        current += relativedelta(months=1)

    return {'labels': labels, 'values': values}


# === Impression Map ===

def get_impression_map_data(
    company: Company,
    start_date: Any = None,
    end_date: Any = None
) -> list[dict]:
    """Get impression map data from review tags."""
    reviews = Review.objects.filter(company=company)
    if start_date:
        reviews = reviews.filter(created_at__gte=start_date)
    if end_date:
        reviews = reviews.filter(created_at__lt=end_date)

    category_order = [
        "Безопасность", "Сервис", "Скорость", "Продукт",
        "Цена", "Комфорт", "Процесс", "Общее"
    ]
    stats = {cat: {"positive": 0, "negative": 0, "neutral": 0} for cat in category_order}

    for review in reviews.values('tags'):
        tags = review.get('tags')
        if not tags or not isinstance(tags, list):
            continue
        for tag in tags:
            category = tag.get('category')
            sentiment = tag.get('sentiment', 'neutral')
            if category in stats:
                stats[category][sentiment] += 1

    return [
        {
            "category": cat,
            "positive": stats[cat]["positive"],
            "negative": stats[cat]["negative"],
            "neutral": stats[cat]["neutral"],
            "total": total,
            "positive_pct": round(stats[cat]["positive"] / total * 100),
            "negative_pct": round(stats[cat]["negative"] / total * 100),
            "neutral_pct": round(stats[cat]["neutral"] / total * 100),
            "is_critical": cat == "Безопасность",
        }
        for cat in category_order
        if (total := sum(stats[cat].values())) > 0
    ]


# === Dashboard Context Builder ===

def build_dashboard_context(
    company: Company,
    companies: list[Company],
    request: HttpRequest
) -> dict:
    """Build complete context for dashboard view."""
    period = request.GET.get('period', 'month')
    if period not in ('week', 'month', 'quarter', 'half_year', 'custom'):
        period = 'month'

    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    analytics = get_analytics_data(company, period, date_from, date_to)
    impression_map = get_impression_map_data(company)

    # Import here to avoid circular imports
    from .reviews import get_dashboard_stats

    return {
        'company': company,
        'companies': companies,
        'stats': get_dashboard_stats(company),
        'period': period,
        'date_from': date_from,
        'date_to': date_to,
        'period_labels': get_period_labels(),
        'analytics': analytics,
        'analytics_json': json.dumps(analytics, ensure_ascii=False),
        'impression_map': impression_map,
    }
