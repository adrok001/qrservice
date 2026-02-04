"""
Reviews-related business logic.
"""
from datetime import timedelta

from django.db.models import Avg, Count, Q, QuerySet
from django.utils import timezone

from apps.companies.models import Company, Platform, Connection
from apps.reviews.models import Review
from apps.qr.models import QR
from .insights import PROBLEM_PATTERNS


def get_dashboard_stats(company: Company) -> dict:
    """Get statistics for dashboard main page."""
    since = timezone.now() - timedelta(days=30)

    reviews = Review.objects.filter(company=company)
    reviews_month = reviews.filter(created_at__gte=since)

    stats = {
        'avg_rating': reviews.aggregate(avg=Avg('rating'))['avg'] or 0,
        'new_reviews': reviews_month.count(),
        'negative_count': reviews_month.filter(rating__lte=3).count(),
        'total_scans': QR.objects.filter(company=company).aggregate(
            total=Count('scans')
        )['total'] or 0,
    }

    stats['avg_rating'] = round(stats['avg_rating'], 1)
    return stats


def get_attention_reviews(company: Company, limit: int = 5) -> QuerySet:
    """Get negative reviews without response."""
    return Review.objects.filter(
        company=company,
        rating__lte=3,
        response='',
        status='new'
    ).prefetch_related('photos').order_by('-created_at')[:limit]


def get_recent_reviews(company: Company, limit: int = 5) -> QuerySet:
    """Get recent reviews."""
    return Review.objects.filter(
        company=company
    ).prefetch_related('photos').order_by('-created_at')[:limit]


def get_review_counts(company: Company) -> dict:
    """Get review counts for filter tabs."""
    base = Review.objects.filter(company=company)
    return {
        'all': base.count(),
        'new': base.filter(status='new').count(),
        'negative': base.filter(rating__lte=3).count(),
        'no_response': base.filter(response='').count(),
    }


def filter_reviews_by_category(reviews_queryset, category: str) -> list:
    """
    Filter reviews by category in Python.

    Note: This is a performance optimization. Instead of loading ALL reviews
    and then filtering, we only load the reviews after DB-level filtering.
    For PostgreSQL, this could be moved to JSON query.

    Args:
        reviews_queryset: Django QuerySet (not yet evaluated)
        category: Category to filter by

    Returns:
        List of filtered reviews
    """
    # Load only necessary fields to reduce memory usage
    reviews = reviews_queryset.only('id', 'tags', 'text', 'rating', 'created_at', 'author_name')

    filtered = []
    for review in reviews:
        if review.tags and isinstance(review.tags, list):
            for tag in review.tags:
                if isinstance(tag, dict) and tag.get('category') == category:
                    # Re-fetch full object only for matched reviews
                    filtered.append(review)
                    break

    # Fetch full objects for matched IDs (single query)
    if filtered:
        review_ids = [r.id for r in filtered]
        return list(reviews_queryset.filter(id__in=review_ids))
    return []


def filter_reviews(company: Company, params: dict) -> list:
    """
    Filter reviews based on request parameters.

    Optimized to minimize database queries by:
    1. Using prefetch_related for related objects
    2. Applying all DB-level filters before evaluation
    3. Only converting to list at the very end
    """
    # Start with base queryset - NOT evaluated yet
    reviews = Review.objects.filter(company=company).prefetch_related('photos', 'history')

    # Apply all DB-level filters (still not evaluated)
    source = params.get('source')
    if source:
        reviews = reviews.filter(source=source)

    rating = params.get('rating')
    if rating:
        reviews = reviews.filter(rating=int(rating))

    filter_type = params.get('filter')
    if filter_type == 'negative':
        reviews = reviews.filter(rating__lte=3)
    elif filter_type == 'no_response':
        reviews = reviews.filter(response='')
    elif filter_type == 'new':
        reviews = reviews.filter(status='new')
    elif filter_type == 'wants_contact':
        reviews = reviews.filter(wants_contact=True, response='')
    elif filter_type == 'safety':
        # Фильтр по категории "Безопасность" - обрабатывается ниже в category filter
        pass

    sentiment = params.get('sentiment')
    if sentiment:
        reviews = reviews.filter(sentiment=sentiment)

    search = params.get('search')
    if search:
        reviews = reviews.filter(
            Q(text__icontains=search) |
            Q(author_name__icontains=search)
        )

    reviews = reviews.order_by('-created_at')

    # Category filter requires Python iteration (SQLite limitation)
    # But we optimize by only loading matched reviews
    category = params.get('category')

    # Если фильтр safety — это категория "Безопасность" для негативных отзывов
    if filter_type == 'safety':
        reviews = reviews.filter(rating__lte=3)
        category = 'Безопасность'

    if category:
        return filter_reviews_by_category(reviews, category)

    # Фильтр по типу проблемы (из priority_alerts)
    problem_key = params.get('problem')
    if problem_key:
        return filter_reviews_by_problem(reviews, problem_key)

    # Only now evaluate the queryset to list
    return list(reviews)


def filter_reviews_by_problem(reviews_queryset: QuerySet, problem_key: str) -> list:
    """
    Фильтрует отзывы по типу проблемы (паттернам из PROBLEM_PATTERNS).
    """
    # Находим паттерны для данного ключа
    patterns = None
    for problem in PROBLEM_PATTERNS:
        if problem['key'] == problem_key:
            patterns = problem['patterns']
            break

    if not patterns:
        return list(reviews_queryset)

    # Фильтруем только негативные
    reviews_queryset = reviews_queryset.filter(rating__lte=3)

    # Фильтруем по паттернам в тексте
    matched = []
    for review in reviews_queryset:
        text_lower = (review.text or '').lower()
        if any(p in text_lower for p in patterns):
            matched.append(review)

    return matched


def update_feedback_settings(
    company: Company,
    post_data: dict,
    platforms: QuerySet[Platform]
) -> None:
    """Update feedback form settings from POST data."""
    settings = company.settings or {}
    feedback = settings.get('feedback', {})

    feedback['title'] = post_data.get('title', '').strip() or 'Как вам у нас?'
    feedback['subtitle'] = post_data.get('subtitle', '').strip()
    feedback['bg_color'] = post_data.get('bg_color', '#f8f9fa')
    feedback['positive_title'] = post_data.get('positive_title', '').strip()
    feedback['positive_subtitle'] = post_data.get('positive_subtitle', '').strip()
    feedback['negative_title'] = post_data.get('negative_title', '').strip()
    feedback['negative_subtitle'] = post_data.get('negative_subtitle', '').strip()
    feedback['thank_you_title'] = post_data.get('thank_you_title', '').strip()
    feedback['thank_you_subtitle'] = post_data.get('thank_you_subtitle', '').strip()
    feedback['show_internal_form'] = post_data.get('show_internal_form') == 'on'

    settings['feedback'] = feedback
    company.settings = settings
    company.save(update_fields=['settings'])

    _update_platform_feedback_connections(company, post_data, platforms)


def _update_platform_feedback_connections(
    company: Company,
    post_data: dict,
    platforms: QuerySet[Platform]
) -> None:
    """Update platform connections for feedback form."""
    for platform in platforms:
        enabled = post_data.get(f'platform_{platform.id}_enabled') == 'on'
        url = post_data.get(f'platform_{platform.id}_url', '').strip()

        if url:
            Connection.objects.update_or_create(
                company=company,
                platform=platform,
                defaults={
                    'external_url': url,
                    'external_id': url,
                    'sync_enabled': enabled,
                }
            )
        else:
            Connection.objects.filter(company=company, platform=platform).delete()


def build_form_settings_platform_data(company) -> list[dict]:
    """Build platform data for form settings view."""
    from apps.companies.models import Platform, Connection

    platforms = Platform.objects.filter(is_active=True)
    connections = {
        c.platform_id: c
        for c in Connection.objects.filter(company=company)
    }

    return [
        {
            'id': p.id,
            'name': p.name,
            'enabled': connections.get(p.id).sync_enabled if connections.get(p.id) else False,
            'url': connections.get(p.id).external_url if connections.get(p.id) else '',
        }
        for p in platforms
    ], platforms
