"""
Dashboard business logic services.
Keeps views thin by extracting data fetching and processing logic.
"""
from django.db.models import Avg, Count, Q
from django.utils import timezone
from datetime import timedelta
from io import BytesIO

from apps.accounts.models import Member
from apps.reviews.models import Review
from apps.qr.models import QR


def get_user_companies(user):
    """Get all companies for user"""
    memberships = Member.objects.filter(
        user=user, is_active=True
    ).select_related('company')
    return [m.company for m in memberships]


def get_current_company(request):
    """Get current company from session or first available"""
    user = request.user
    companies = get_user_companies(user)

    if not companies:
        return None, []

    selected_id = request.session.get('selected_company_id')
    if selected_id:
        for company in companies:
            if str(company.id) == selected_id:
                return company, companies

    return companies[0], companies


def get_dashboard_stats(company):
    """Get statistics for dashboard main page"""
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


def get_attention_reviews(company, limit=5):
    """Get negative reviews without response"""
    return Review.objects.filter(
        company=company,
        rating__lte=3,
        response='',
        status='new'
    ).prefetch_related('photos').order_by('-created_at')[:limit]


def get_recent_reviews(company, limit=5):
    """Get recent reviews"""
    return Review.objects.filter(company=company).prefetch_related('photos').order_by('-created_at')[:limit]


def get_review_counts(company):
    """Get review counts for filter tabs"""
    base = Review.objects.filter(company=company)
    return {
        'all': base.count(),
        'new': base.filter(status='new').count(),
        'negative': base.filter(rating__lte=3).count(),
        'no_response': base.filter(response='').count(),
    }


def filter_reviews(company, params):
    """Filter reviews based on request parameters"""
    reviews = Review.objects.filter(company=company).prefetch_related('photos')

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

    search = params.get('search')
    if search:
        reviews = reviews.filter(
            Q(text__icontains=search) |
            Q(author_name__icontains=search)
        )

    return reviews.order_by('-created_at')


def update_feedback_settings(company, post_data, platforms):
    """Update feedback form settings from POST data"""
    from apps.companies.models import Connection

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

    # Update platform connections
    for platform in platforms:
        enabled = post_data.get(f'platform_{platform.id}_enabled') == 'on'
        url = post_data.get(f'platform_{platform.id}_url', '').strip()

        if url:
            # Create or update connection
            Connection.objects.update_or_create(
                company=company,
                platform=platform,
                defaults={
                    'external_url': url,
                    'external_id': url,  # Use URL as external_id
                    'sync_enabled': enabled,
                }
            )
        else:
            # Remove connection if URL is empty
            Connection.objects.filter(company=company, platform=platform).delete()


def generate_qr_image(qr):
    """Generate QR code image"""
    import qrcode
    from django.core.files.base import ContentFile
    from django.conf import settings

    base_url = getattr(settings, 'SITE_URL', 'http://localhost:8000')
    url = f"{base_url}/{qr.code}"

    qr_image = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr_image.add_data(url)
    qr_image.make(fit=True)

    fill_color = qr.color or '#000000'
    back_color = qr.background or '#FFFFFF'

    img = qr_image.make_image(fill_color=fill_color, back_color=back_color)

    buffer = BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)

    filename = f'qr_{qr.code}.png'
    qr.image.save(filename, ContentFile(buffer.read()), save=True)


def get_platforms_with_connections(company):
    """Get platforms sorted with their connections"""
    from apps.companies.models import Platform, Connection

    platform_order = {'yandex': 1, '2gis': 2, 'google': 3}
    platforms = sorted(
        Platform.objects.filter(is_active=True),
        key=lambda p: platform_order.get(p.id, 99)
    )
    connections = {c.platform_id: c for c in Connection.objects.filter(company=company)}

    return platforms, connections


def update_company_info(company, post_data, files):
    """Update company name, address and logo"""
    name = post_data.get('name', '').strip()
    if name:
        company.name = name

    company.address = post_data.get('address', '').strip()

    if 'logo' in files:
        logo = files['logo']
        allowed_types = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
        if logo.content_type in allowed_types:
            if company.logo:
                company.logo.delete(save=False)
            company.logo = logo

    if post_data.get('delete_logo') == '1' and company.logo:
        company.logo.delete(save=False)
        company.logo = None

    company.save()


def update_platform_connections(company, platforms, post_data, connections):
    """Update geo service platform connections"""
    from apps.companies.models import Connection

    for platform in platforms:
        url = post_data.get(f'platform_{platform.id}', '').strip()
        enabled = post_data.get(f'platform_{platform.id}_enabled') == 'on'
        existing = connections.get(platform.id)

        if url:
            if existing:
                existing.external_url = url
                existing.sync_enabled = enabled
                existing.save(update_fields=['external_url', 'sync_enabled'])
            else:
                Connection.objects.create(
                    company=company,
                    platform=platform,
                    external_id=url,
                    external_url=url,
                    sync_enabled=enabled,
                )
        elif existing and not existing.access_token:
            existing.external_url = ''
            existing.sync_enabled = False
            existing.save(update_fields=['external_url', 'sync_enabled'])


def auto_fill_address(company, post_data):
    """Auto-fill address from geo service URLs if empty"""
    if company.address:
        return

    from apps.companies.services import extract_address_from_urls
    urls = [
        post_data.get('platform_yandex', ''),
        post_data.get('platform_2gis', ''),
        post_data.get('platform_google', ''),
    ]
    extracted = extract_address_from_urls(urls)
    if extracted:
        company.address = extracted
        company.save(update_fields=['address'])


def build_platform_data(platforms, connections):
    """Build platform data for template"""
    return [
        {
            'id': p.id,
            'name': p.name,
            'url': connections.get(p.id).external_url if connections.get(p.id) else '',
            'enabled': connections.get(p.id).sync_enabled if connections.get(p.id) else False,
            'has_oauth': bool(connections.get(p.id) and connections.get(p.id).access_token),
        }
        for p in platforms
    ]


def get_period_dates(period: str):
    """Get start date for given period"""
    from datetime import datetime, time
    today = timezone.now().date()

    if period == 'today':
        start = timezone.make_aware(datetime.combine(today, time.min))
    elif period == 'yesterday':
        start = timezone.make_aware(datetime.combine(today - timedelta(days=1), time.min))
    elif period == 'week':
        start = timezone.make_aware(datetime.combine(today - timedelta(days=7), time.min))
    elif period == 'month':
        start = timezone.make_aware(datetime.combine(today - timedelta(days=30), time.min))
    elif period == 'year':
        start = timezone.make_aware(datetime.combine(today - timedelta(days=365), time.min))
    else:  # 'all'
        start = None

    return start


def get_analytics_data(company, period: str = 'month'):
    """Get analytics data for charts"""
    from collections import defaultdict

    start_date = get_period_dates(period)

    reviews = Review.objects.filter(company=company)
    if start_date:
        reviews = reviews.filter(created_at__gte=start_date)

    total_count = reviews.count()

    # Rating distribution
    rating_counts = defaultdict(int)
    source_counts = defaultdict(int)
    sentiment_counts = {'positive': 0, 'neutral': 0, 'negative': 0}

    for review in reviews.values('rating', 'source', 'sentiment'):
        rating_counts[review['rating']] += 1
        source_counts[review['source']] += 1
        if review['sentiment']:
            sentiment_counts[review['sentiment']] += 1

    # Format for charts
    rating_data = {
        'labels': ['5 звёзд', '4 звезды', '3 звезды', '2 звезды', '1 звезда'],
        'values': [rating_counts.get(5, 0), rating_counts.get(4, 0),
                   rating_counts.get(3, 0), rating_counts.get(2, 0), rating_counts.get(1, 0)],
        'colors': ['#22c55e', '#84cc16', '#fbbf24', '#f97316', '#ef4444'],
    }

    # Source names mapping
    source_names = {
        'internal': 'Наш сервис',
        'yandex': 'Яндекс Карты',
        '2gis': '2ГИС',
        'google': 'Google Maps',
        'tripadvisor': 'TripAdvisor',
    }
    source_colors = {
        'internal': '#000000',
        'yandex': '#fc3f1d',
        '2gis': '#1fab54',
        'google': '#4285f4',
        'tripadvisor': '#00af87',
    }

    source_data = {
        'labels': [],
        'values': [],
        'colors': [],
    }
    for source, count in sorted(source_counts.items(), key=lambda x: -x[1]):
        if count > 0:
            source_data['labels'].append(source_names.get(source, source))
            source_data['values'].append(count)
            source_data['colors'].append(source_colors.get(source, '#999999'))

    # Daily reviews for bar chart (last 7 days or period)
    days_count = 7
    if period == 'today':
        days_count = 1
    elif period == 'yesterday':
        days_count = 1
    elif period == 'week':
        days_count = 7
    elif period == 'month':
        days_count = 30
    elif period == 'year':
        days_count = 12  # Monthly for year

    daily_data = get_daily_reviews(company, days_count, period)

    # Calculate averages and totals
    avg_rating = reviews.aggregate(avg=Avg('rating'))['avg'] or 0

    return {
        'total_count': total_count,
        'avg_rating': round(avg_rating, 1),
        'rating_data': rating_data,
        'source_data': source_data,
        'sentiment_counts': sentiment_counts,
        'daily_data': daily_data,
    }


def get_daily_reviews(company, days: int, period: str):
    """Get review counts by day/month"""
    from collections import defaultdict
    from datetime import datetime, time

    today = timezone.now().date()

    if period == 'year':
        # Monthly data for year view
        labels = []
        values = []
        month_names = ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн',
                       'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек']

        for i in range(11, -1, -1):
            month_date = today - timedelta(days=i*30)
            month = month_date.month
            year = month_date.year

            start = timezone.make_aware(datetime(year, month, 1, 0, 0, 0))
            if month == 12:
                end = timezone.make_aware(datetime(year + 1, 1, 1, 0, 0, 0))
            else:
                end = timezone.make_aware(datetime(year, month + 1, 1, 0, 0, 0))

            count = Review.objects.filter(
                company=company,
                created_at__gte=start,
                created_at__lt=end
            ).count()

            labels.append(month_names[month - 1])
            values.append(count)

        return {'labels': labels, 'values': values}

    # Daily data
    labels = []
    values = []
    day_names = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']

    for i in range(days - 1, -1, -1):
        day = today - timedelta(days=i)
        start = timezone.make_aware(datetime.combine(day, time.min))
        end = timezone.make_aware(datetime.combine(day + timedelta(days=1), time.min))

        count = Review.objects.filter(
            company=company,
            created_at__gte=start,
            created_at__lt=end
        ).count()

        if days <= 7:
            labels.append(day_names[day.weekday()])
        else:
            labels.append(day.strftime('%d.%m'))
        values.append(count)

    return {'labels': labels, 'values': values}
