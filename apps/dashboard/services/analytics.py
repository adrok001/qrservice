"""
Analytics and KPI business logic.
"""
import json
from datetime import timedelta
from typing import Any

from django.db.models import Avg, QuerySet
from django.http import HttpRequest
from django.utils import timezone

from apps.companies.models import Company
from apps.reviews.models import Review

from .periods import get_period_labels, get_period_dates, get_days_count
from .charts import build_chart_data, get_daily_reviews
from .insights import (
    get_attention_items,
    get_top_complaints,
    get_top_praises,
    get_spots_comparison,
    get_simple_metrics,
    get_priority_alerts,
    has_critical_alerts,
)


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

    chart_data = build_chart_data(reviews)
    days_count = get_days_count(period, date_from, date_to)
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
    period = request.GET.get('period', 'all')
    if period not in ('all', 'week', 'month', 'custom'):
        period = 'all'

    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    # Получаем даты периода
    start_date, prev_start, prev_end, end_date = get_period_dates(
        period, date_from, date_to
    )

    # Фильтруем отзывы по периоду
    reviews = _filter_reviews_by_period(company, start_date, end_date)
    prev_reviews = _get_previous_reviews(company, prev_start, prev_end, start_date)

    # === НОВЫЕ БЛОКИ ===

    # 1. Приоритетные проблемы (всегда актуальное, не зависит от периода)
    priority_alerts = get_priority_alerts(company, limit=3)

    # 2. Простые метрики с трендами
    metrics = get_simple_metrics(reviews, prev_reviews)

    # 3. Топ жалоб и похвал (за период)
    complaints = get_top_complaints(reviews, limit=5)
    praises = get_top_praises(reviews, limit=5)

    # 4. Сравнение по точкам (за период)
    spots = get_spots_comparison(company, start_date, end_date)

    # === СТАРЫЕ ДАННЫЕ (для графика) ===
    days_count = get_days_count(period, date_from, date_to)
    daily_data = get_daily_reviews(company, days_count, period, date_from, date_to)

    return {
        'company': company,
        'companies': companies,
        'period': period,
        'date_from': date_from,
        'date_to': date_to,
        'period_labels': get_period_labels(),
        # Новые блоки
        'priority_alerts': priority_alerts,
        'has_critical': has_critical_alerts(priority_alerts),
        'metrics': metrics,
        'complaints': complaints,
        'praises': praises,
        'spots': spots,
        # Данные для графика
        'daily_data': daily_data,
        'daily_data_json': json.dumps(daily_data, ensure_ascii=False),
    }
