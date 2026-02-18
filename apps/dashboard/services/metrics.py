"""
Dashboard metrics: сравнение по точкам и простые метрики.
"""
from collections import Counter
from datetime import timedelta
from typing import Any

from django.db.models import Avg, Count, Q, QuerySet
from django.utils import timezone

from apps.companies.models import Company, Spot
from apps.reviews.models import Review

from .insights import COMPLAINT_PATTERNS, _extract_issues, get_top_complaints_ai


def get_spots_comparison(
    company: Company,
    start_date: Any = None,
    end_date: Any = None,
    mode: str = 'basic',
) -> list[dict]:
    """
    Сравнение статистики по точкам/филиалам.

    Returns:
        [{'name': 'Тверская', 'rating': 4.5, 'negative_pct': 8, 'trend': 'up', 'count': 234}, ...]
    """
    spots = Spot.objects.filter(company=company, is_active=True)
    if not spots.exists():
        return []

    results = []
    week_ago = timezone.now() - timedelta(days=7)

    for spot in spots:
        # Основная статистика за период
        reviews = Review.objects.filter(company=company, spot=spot)
        if start_date:
            reviews = reviews.filter(created_at__gte=start_date)
        if end_date:
            reviews = reviews.filter(created_at__lt=end_date)

        total = reviews.count()
        if total == 0:
            continue

        stats = reviews.aggregate(
            avg_rating=Avg('rating'),
            negative=Count('id', filter=Q(rating__lte=3))
        )

        avg_rating = stats['avg_rating'] or 0
        negative_count = stats['negative'] or 0
        negative_pct = round(negative_count / total * 100) if total > 0 else 0

        # Тренд: сравниваем с предыдущей неделей
        recent = reviews.filter(created_at__gte=week_ago)
        recent_stats = recent.aggregate(avg_rating=Avg('rating'))
        recent_rating = recent_stats['avg_rating']

        rating_delta = 0
        trend = 'stable'
        if recent_rating and avg_rating:
            rating_delta = round(recent_rating - avg_rating, 1)
            if rating_delta > 0.1:
                trend = 'up'
            elif rating_delta < -0.1:
                trend = 'down'
            else:
                rating_delta = 0  # Не показываем мелкие изменения

        # Для негативного тренда — собираем топ жалоб с количеством
        top_issues = []
        if trend == 'down':
            if mode == 'ai':
                top_issues = get_top_complaints_ai(recent, limit=3)
            else:
                issue_counter = Counter()
                for review in recent.filter(rating__lte=3).values('text'):
                    issues = _extract_issues(review['text'], COMPLAINT_PATTERNS)
                    issue_counter.update(issues)
                top_issues = [
                    {'label': label, 'count': count}
                    for label, count in issue_counter.most_common(3)
                ]

        results.append({
            'id': str(spot.id),
            'name': spot.name,
            'rating': round(avg_rating, 1),
            'negative_pct': negative_pct,
            'trend': trend,
            'rating_delta': rating_delta,
            'top_issues': top_issues,
            'count': total,
        })

    # Сортируем по рейтингу (худшие внизу)
    results.sort(key=lambda x: x['rating'], reverse=True)

    return results


def get_simple_metrics(
    reviews_qs: QuerySet,
    prev_reviews_qs: QuerySet = None
) -> dict:
    """
    Простые метрики с трендами.

    Returns:
        {
            'rating': 4.3,
            'rating_trend': 'up',  # up/down/stable
            'rating_delta': +0.2,
            'negative_pct': 15,
            'negative_trend': 'down',
            'total': 1897
        }
    """
    total = reviews_qs.count()
    if total == 0:
        return {
            'rating': 0, 'rating_trend': 'stable', 'rating_delta': 0,
            'negative_pct': 0, 'negative_trend': 'stable', 'negative_delta': 0, 'total': 0,
            'positive_count': 0, 'negative_count': 0
        }

    stats = reviews_qs.aggregate(
        avg_rating=Avg('rating'),
        negative=Count('id', filter=Q(rating__lte=3)),
        positive=Count('id', filter=Q(rating__gte=4))
    )

    rating = round(stats['avg_rating'] or 0, 1)
    negative_count = stats['negative'] or 0
    positive_count = stats['positive'] or 0
    negative_pct = round(negative_count / total * 100)

    # Тренды
    rating_trend = 'stable'
    rating_delta = 0
    negative_trend = 'stable'
    negative_delta = 0

    if prev_reviews_qs is not None and prev_reviews_qs.exists():
        prev_total = prev_reviews_qs.count()
        prev_stats = prev_reviews_qs.aggregate(
            avg_rating=Avg('rating'),
            negative=Count('id', filter=Q(rating__lte=3))
        )

        prev_rating = prev_stats['avg_rating'] or 0
        prev_negative_pct = round((prev_stats['negative'] or 0) / prev_total * 100) if prev_total > 0 else 0

        rating_delta = round(rating - prev_rating, 1)
        if rating_delta > 0.1:
            rating_trend = 'up'
        elif rating_delta < -0.1:
            rating_trend = 'down'

        negative_delta = negative_pct - prev_negative_pct
        if negative_pct < prev_negative_pct - 2:
            negative_trend = 'down'  # негатив уменьшается = хорошо
        elif negative_pct > prev_negative_pct + 2:
            negative_trend = 'up'  # негатив растёт = плохо

    return {
        'rating': rating,
        'rating_trend': rating_trend,
        'rating_delta': rating_delta,
        'negative_pct': negative_pct,
        'negative_trend': negative_trend,
        'negative_delta': negative_delta,
        'total': total,
        'positive_count': positive_count,
        'negative_count': negative_count,
    }
