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
    ).order_by('-created_at')[:limit]


def get_recent_reviews(company, limit=5):
    """Get recent reviews"""
    return Review.objects.filter(company=company).order_by('-created_at')[:limit]


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
    reviews = Review.objects.filter(company=company)

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


def update_feedback_settings(company, post_data, connections):
    """Update feedback form settings from POST data"""
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

    enabled_platforms = post_data.getlist('platforms')
    for conn in connections:
        conn.sync_enabled = conn.platform_id in enabled_platforms
        conn.save(update_fields=['sync_enabled'])


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
