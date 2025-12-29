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


def get_period_labels():
    """Get human-readable date ranges for each period (for tooltips)"""
    from dateutil.relativedelta import relativedelta

    today = timezone.now().date()

    # Текущая неделя (с понедельника)
    week_start = today - timedelta(days=today.weekday())
    week_end = today

    # Текущий месяц
    month_start = today.replace(day=1)
    month_end = today

    # Текущий квартал
    quarter_month = ((today.month - 1) // 3) * 3 + 1
    quarter_start = today.replace(month=quarter_month, day=1)
    quarter_end = today

    # Последние 6 месяцев
    half_year_start = today - relativedelta(months=6)
    half_year_end = today

    def format_range(start, end):
        if start.year == end.year:
            return f"{start.strftime('%d.%m')} — {end.strftime('%d.%m.%Y')}"
        return f"{start.strftime('%d.%m.%Y')} — {end.strftime('%d.%m.%Y')}"

    return {
        'week': format_range(week_start, week_end),
        'month': format_range(month_start, month_end),
        'quarter': format_range(quarter_start, quarter_end),
        'half_year': format_range(half_year_start, half_year_end),
    }


def get_period_dates(period: str, date_from: str = None, date_to: str = None):
    """Get start and end dates for given period, plus previous period for delta calculation"""
    from datetime import datetime, time
    from dateutil.relativedelta import relativedelta

    today = timezone.now().date()

    if period == 'week':
        # Текущая неделя (с понедельника)
        week_start = today - timedelta(days=today.weekday())
        start = timezone.make_aware(datetime.combine(week_start, time.min))
        # Предыдущая неделя
        prev_start = timezone.make_aware(datetime.combine(week_start - timedelta(days=7), time.min))
        prev_end = start

    elif period == 'month':
        # Текущий месяц (с 1-го числа)
        month_start = today.replace(day=1)
        start = timezone.make_aware(datetime.combine(month_start, time.min))
        # Предыдущий месяц
        prev_month_start = (month_start - timedelta(days=1)).replace(day=1)
        prev_start = timezone.make_aware(datetime.combine(prev_month_start, time.min))
        prev_end = start

    elif period == 'quarter':
        # Текущий квартал
        quarter_month = ((today.month - 1) // 3) * 3 + 1
        quarter_start = today.replace(month=quarter_month, day=1)
        start = timezone.make_aware(datetime.combine(quarter_start, time.min))
        # Предыдущий квартал (3 месяца назад)
        prev_quarter_start = quarter_start - relativedelta(months=3)
        prev_start = timezone.make_aware(datetime.combine(prev_quarter_start, time.min))
        prev_end = start

    elif period == 'half_year':
        # Последние 6 месяцев
        half_year_start = today - relativedelta(months=6)
        start = timezone.make_aware(datetime.combine(half_year_start, time.min))
        # Предыдущие 6 месяцев
        prev_start = timezone.make_aware(datetime.combine(half_year_start - relativedelta(months=6), time.min))
        prev_end = start

    elif period == 'custom' and date_from and date_to:
        # Произвольный период
        try:
            from_date = datetime.strptime(date_from, '%Y-%m-%d').date()
            to_date = datetime.strptime(date_to, '%Y-%m-%d').date()
            start = timezone.make_aware(datetime.combine(from_date, time.min))
            end = timezone.make_aware(datetime.combine(to_date + timedelta(days=1), time.min))
            # Предыдущий период той же длительности
            period_days = (to_date - from_date).days + 1
            prev_start = timezone.make_aware(datetime.combine(from_date - timedelta(days=period_days), time.min))
            prev_end = start
            return start, prev_start, prev_end, end
        except (ValueError, TypeError):
            start = None
            prev_start = None
            prev_end = None

    else:
        start = None
        prev_start = None
        prev_end = None

    return start, prev_start, prev_end, None


def calculate_kpi_metrics(reviews_qs, all_reviews_qs=None):
    """Calculate KPI metrics from a queryset of reviews"""
    from collections import defaultdict
    from django.db.models import F, ExpressionWrapper, DurationField

    total_count = reviews_qs.count()
    if total_count == 0:
        return {
            'avg_rating': 0,
            'nps': 0,
            'negative_share': 0,
            'negative_unanswered_count': 0,
            'negative_unanswered_share': 0,
            'avg_response_time_hours': 0,
            'total_count': 0,
            'promoters': 0,
            'detractors': 0,
            'negative_count': 0,
        }

    # 1. Средний рейтинг: avg(rating) по отзывам с рейтингом
    avg_rating = reviews_qs.aggregate(avg=Avg('rating'))['avg'] or 0

    # 2. NPS: (promoters - detractors) / total_rated * 100
    # promoters = rating 5, detractors = rating 1-3
    promoters = reviews_qs.filter(rating=5).count()
    detractors = reviews_qs.filter(rating__lte=3).count()
    nps = ((promoters - detractors) / total_count * 100) if total_count > 0 else 0

    # 3. Доля негатива: negative / (positive+neutral+negative) * 100
    # negative = rating 1-3
    negative_count = detractors
    negative_share = (negative_count / total_count * 100) if total_count > 0 else 0

    # 4. Негатив без ответа: count(negative where response='')
    negative_unanswered_count = reviews_qs.filter(rating__lte=3, response='').count()
    negative_unanswered_share = (negative_unanswered_count / negative_count * 100) if negative_count > 0 else 0

    # 5. Среднее время ответа (часы): avg(response_at - created_at) по отзывам с ответом
    reviews_with_response = reviews_qs.filter(response_at__isnull=False)
    avg_response_time_hours = 0
    if reviews_with_response.exists():
        total_hours = 0
        count_with_response = 0
        for review in reviews_with_response.values('created_at', 'response_at'):
            if review['response_at'] and review['created_at']:
                delta = review['response_at'] - review['created_at']
                total_hours += delta.total_seconds() / 3600
                count_with_response += 1
        if count_with_response > 0:
            avg_response_time_hours = total_hours / count_with_response

    return {
        'avg_rating': round(avg_rating, 2),
        'nps': round(nps, 1),
        'negative_share': round(negative_share, 1),
        'negative_unanswered_count': negative_unanswered_count,
        'negative_unanswered_share': round(negative_unanswered_share, 1),
        'avg_response_time_hours': round(avg_response_time_hours, 1),
        'total_count': total_count,
        'promoters': promoters,
        'detractors': detractors,
        'negative_count': negative_count,
    }


def calculate_reputation_risk(company, current_metrics, period_start):
    """
    Calculate reputation risk score (0-100)
    Formula: 50*share_negative + 30*share_unanswered_negative + 20*recent_negative_rate
    where recent_negative_rate = negative last 7 days / reviews last 7 days
    """
    # share_negative (0-1): доля негатива от всех отзывов
    share_negative = current_metrics['negative_share'] / 100 if current_metrics['total_count'] > 0 else 0

    # share_unanswered_negative (0-1): доля неотвеченного негатива
    share_unanswered_negative = current_metrics['negative_unanswered_share'] / 100 if current_metrics['negative_count'] > 0 else 0

    # recent_negative_rate (0-1): негатив за 7 дней / отзывы за 7 дней
    recent_start = timezone.now() - timedelta(days=7)
    recent_reviews = Review.objects.filter(company=company, created_at__gte=recent_start)
    recent_total = recent_reviews.count()
    recent_negative = recent_reviews.filter(rating__lte=3).count()
    recent_negative_rate = (recent_negative / recent_total) if recent_total > 0 else 0

    # Formula: 50*share_negative + 30*share_unanswered_negative + 20*recent_negative_rate
    risk_score = 50 * share_negative + 30 * share_unanswered_negative + 20 * recent_negative_rate

    return round(min(risk_score, 100), 0)


def get_analytics_data(company, period: str = 'month', date_from: str = None, date_to: str = None):
    """Get analytics data for charts and KPI"""
    from collections import defaultdict

    start_date, prev_start, prev_end, end_date = get_period_dates(period, date_from, date_to)

    # Current period reviews
    reviews = Review.objects.filter(company=company)
    if start_date:
        reviews = reviews.filter(created_at__gte=start_date)
    if end_date:
        reviews = reviews.filter(created_at__lt=end_date)

    # Previous period reviews (for delta calculation)
    prev_reviews = Review.objects.filter(company=company)
    if prev_start and prev_end:
        prev_reviews = prev_reviews.filter(created_at__gte=prev_start, created_at__lt=prev_end)
    elif start_date:
        prev_reviews = Review.objects.none()

    # Calculate KPI metrics
    current_kpi = calculate_kpi_metrics(reviews)
    prev_kpi = calculate_kpi_metrics(prev_reviews)

    # Calculate deltas
    avg_rating_delta = round(current_kpi['avg_rating'] - prev_kpi['avg_rating'], 2) if prev_kpi['total_count'] > 0 else None
    nps_delta = round(current_kpi['nps'] - prev_kpi['nps'], 1) if prev_kpi['total_count'] > 0 else None

    # Calculate reputation risk
    reputation_risk = calculate_reputation_risk(company, current_kpi, start_date)

    total_count = current_kpi['total_count']

    # Rating distribution
    rating_counts = defaultdict(int)
    source_counts = defaultdict(int)
    sentiment_counts = {'positive': 0, 'neutral': 0, 'negative': 0}

    for review in reviews.values('rating', 'source'):
        rating_counts[review['rating']] += 1
        source_counts[review['source']] += 1
        rating = review['rating']
        if rating == 5:
            sentiment_counts['positive'] += 1
        elif rating == 4:
            sentiment_counts['neutral'] += 1
        else:  # 1-3
            sentiment_counts['negative'] += 1

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
        'internal': '#f97316',
        'yandex': '#facc15',
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

    # Sentiment data for chart
    sentiment_data = {
        'labels': ['Позитив', 'Нейтральный', 'Негатив'],
        'values': [
            sentiment_counts['positive'],
            sentiment_counts['neutral'],
            sentiment_counts['negative']
        ],
        'colors': ['#22c55e', '#fbbf24', '#ef4444'],
    }

    # Daily reviews for bar chart
    # Determine chart granularity based on period
    if period == 'week':
        days_count = 7
    elif period == 'month':
        days_count = 30
    elif period == 'quarter':
        days_count = 90
    elif period == 'half_year':
        days_count = 180
    elif period == 'custom' and date_from and date_to:
        try:
            from datetime import datetime as dt
            from_date = dt.strptime(date_from, '%Y-%m-%d').date()
            to_date = dt.strptime(date_to, '%Y-%m-%d').date()
            days_count = (to_date - from_date).days + 1
        except (ValueError, TypeError):
            days_count = 30
    else:
        days_count = 30

    daily_data = get_daily_reviews(company, days_count, period, date_from, date_to)

    return {
        'total_count': total_count,
        # KPI metrics
        'avg_rating': current_kpi['avg_rating'],
        'avg_rating_delta': avg_rating_delta,
        'nps': current_kpi['nps'],
        'nps_delta': nps_delta,
        'negative_share': current_kpi['negative_share'],
        'negative_unanswered_count': current_kpi['negative_unanswered_count'],
        'negative_unanswered_share': current_kpi['negative_unanswered_share'],
        'avg_response_time_hours': current_kpi['avg_response_time_hours'],
        'reputation_risk': reputation_risk,
        # Chart data
        'rating_data': rating_data,
        'source_data': source_data,
        'sentiment_data': sentiment_data,
        'sentiment_counts': sentiment_counts,
        'daily_data': daily_data,
    }


def get_impression_map_data(company, start_date=None, end_date=None):
    """Get impression map data from review tags"""
    import json

    reviews = Review.objects.filter(company=company)
    if start_date:
        reviews = reviews.filter(created_at__gte=start_date)
    if end_date:
        reviews = reviews.filter(created_at__lt=end_date)

    # Категории в правильном порядке (Безопасность первой)
    category_order = [
        "Безопасность", "Сервис", "Скорость", "Продукт",
        "Цена", "Комфорт", "Процесс", "Общее"
    ]

    # Инициализация статистики
    stats = {cat: {"positive": 0, "negative": 0, "neutral": 0} for cat in category_order}

    # Парсим теги из всех отзывов
    for review in reviews.values('tags'):
        tags_json = review.get('tags')
        if not tags_json:
            continue
        try:
            tags = json.loads(tags_json)
            for tag in tags:
                category = tag.get('category')
                sentiment = tag.get('sentiment', 'neutral')
                if category in stats:
                    stats[category][sentiment] += 1
        except (json.JSONDecodeError, TypeError):
            continue

    # Формируем данные для отображения
    impression_data = []
    for category in category_order:
        data = stats[category]
        total = data["positive"] + data["negative"] + data["neutral"]
        if total > 0:
            impression_data.append({
                "category": category,
                "positive": data["positive"],
                "negative": data["negative"],
                "neutral": data["neutral"],
                "total": total,
                "positive_pct": round(data["positive"] / total * 100),
                "negative_pct": round(data["negative"] / total * 100),
                "neutral_pct": round(data["neutral"] / total * 100),
                "is_critical": category == "Безопасность",
            })

    return impression_data


def get_daily_reviews(company, days: int, period: str, date_from: str = None, date_to: str = None):
    """Get review counts by day/week/month depending on period length"""
    from datetime import datetime, time
    from dateutil.relativedelta import relativedelta

    today = timezone.now().date()
    labels = []
    values = []
    month_names = ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн',
                   'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек']
    day_names = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']

    # Determine start date based on period
    if period == 'custom' and date_from and date_to:
        try:
            start_date = datetime.strptime(date_from, '%Y-%m-%d').date()
            end_date = datetime.strptime(date_to, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            start_date = today - timedelta(days=30)
            end_date = today
    elif period == 'week':
        start_date = today - timedelta(days=today.weekday())
        end_date = today
    elif period == 'month':
        start_date = today.replace(day=1)
        end_date = today
    elif period == 'quarter':
        quarter_month = ((today.month - 1) // 3) * 3 + 1
        start_date = today.replace(month=quarter_month, day=1)
        end_date = today
    elif period == 'half_year':
        start_date = today - relativedelta(months=6)
        end_date = today
    else:
        start_date = today - timedelta(days=30)
        end_date = today

    # Determine grouping based on date range
    if days <= 14:
        # Daily grouping
        for i in range(days):
            day = start_date + timedelta(days=i)
            if day > end_date:
                break
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

    elif days <= 90:
        # Weekly grouping
        current = start_date - timedelta(days=start_date.weekday())
        while current <= end_date:
            week_start = current
            week_end = current + timedelta(days=7)

            start = timezone.make_aware(datetime.combine(week_start, time.min))
            end = timezone.make_aware(datetime.combine(week_end, time.min))

            count = Review.objects.filter(
                company=company,
                created_at__gte=start,
                created_at__lt=end
            ).count()

            labels.append(week_start.strftime('%d.%m'))
            values.append(count)
            current += timedelta(days=7)

    else:
        # Monthly grouping
        current = start_date.replace(day=1)
        while current <= end_date:
            month = current.month
            year = current.year

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
            current += relativedelta(months=1)

    return {'labels': labels, 'values': values}
