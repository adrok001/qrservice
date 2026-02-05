"""
Chart data builders for dashboard.
"""
from collections import defaultdict
from datetime import datetime, time, timedelta
from typing import Any

from dateutil.relativedelta import relativedelta
from django.db.models import QuerySet
from django.utils import timezone

from apps.companies.models import Company
from apps.reviews.models import Review


def build_chart_data(reviews: QuerySet) -> dict:
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


def get_daily_reviews(
    company: Company,
    days: int,
    period: str,
    date_from: str | None = None,
    date_to: str | None = None,
    spot_ids: list | None = None,
) -> dict:
    """Get review counts by day/week/month depending on period length."""
    start_date, end_date = _get_chart_date_range(period, date_from, date_to, days)

    if days <= 14:
        return _get_daily_grouped(company, start_date, end_date, days, spot_ids=spot_ids)
    elif days <= 90:
        return _get_weekly_grouped(company, start_date, end_date, spot_ids=spot_ids)
    else:
        return _get_monthly_grouped(company, start_date, end_date, spot_ids=spot_ids)


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


def _get_daily_grouped(company: Company, start_date, end_date, days: int, spot_ids=None) -> dict:
    """Get daily grouped review counts."""
    day_names = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
    labels, values = [], []

    for i in range(days):
        day = start_date + timedelta(days=i)
        if day > end_date:
            break
        start = timezone.make_aware(datetime.combine(day, time.min))
        end = timezone.make_aware(datetime.combine(day + timedelta(days=1), time.min))
        qs = Review.objects.filter(
            company=company, created_at__gte=start, created_at__lt=end
        )
        if spot_ids:
            qs = qs.filter(spot_id__in=spot_ids)
        count = qs.count()
        labels.append(day_names[day.weekday()] if days <= 7 else day.strftime('%d.%m'))
        values.append(count)

    return {'labels': labels, 'values': values}


def _get_weekly_grouped(company: Company, start_date, end_date, spot_ids=None) -> dict:
    """Get weekly grouped review counts."""
    labels, values = [], []
    current = start_date - timedelta(days=start_date.weekday())

    while current <= end_date:
        week_end = current + timedelta(days=7)
        start = timezone.make_aware(datetime.combine(current, time.min))
        end = timezone.make_aware(datetime.combine(week_end, time.min))
        qs = Review.objects.filter(
            company=company, created_at__gte=start, created_at__lt=end
        )
        if spot_ids:
            qs = qs.filter(spot_id__in=spot_ids)
        count = qs.count()
        labels.append(current.strftime('%d.%m'))
        values.append(count)
        current += timedelta(days=7)

    return {'labels': labels, 'values': values}


def _get_monthly_grouped(company: Company, start_date, end_date, spot_ids=None) -> dict:
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
        qs = Review.objects.filter(
            company=company, created_at__gte=start, created_at__lt=end
        )
        if spot_ids:
            qs = qs.filter(spot_id__in=spot_ids)
        count = qs.count()
        labels.append(month_names[month - 1])
        values.append(count)
        current += relativedelta(months=1)

    return {'labels': labels, 'values': values}
