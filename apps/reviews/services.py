"""
Review business logic services.
Keeps views thin by extracting validation and processing logic.
"""
import json
import re
from typing import Tuple, Optional, Dict, Any, List

from apps.companies.models import Company, Spot
from apps.qr.models import QR
from .models import Review, ReviewPhoto
from .impression_categories import (
    CATEGORY_MARKERS,
    IMPRESSION_CATEGORIES,
    POSITIVE_BOOSTERS_WORDS,
    NEGATIVE_MARKERS,
)


class ReviewError(Exception):
    """Custom exception for review validation errors"""
    def __init__(self, message: str, status: int = 400):
        self.message = message
        self.status = status
        super().__init__(message)


def parse_request_data(request) -> Tuple[Dict[str, Any], List]:
    """Parse request data and photos from different content types"""
    content_type = request.content_type or ''

    if 'multipart/form-data' in content_type:
        # Convert QueryDict to regular dict (values are lists, we need first item)
        data = {k: v[0] if isinstance(v, list) and len(v) == 1 else v
                for k, v in dict(request.POST).items()}
        return data, request.FILES.getlist('photos')

    if 'application/json' in content_type:
        try:
            return json.loads(request.body), []
        except json.JSONDecodeError:
            raise ReviewError('Invalid JSON')

    # Fallback
    if request.POST:
        data = {k: v[0] if isinstance(v, list) and len(v) == 1 else v
                for k, v in dict(request.POST).items()}
    else:
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            raise ReviewError('Invalid data')
    photos = request.FILES.getlist('photos')
    return data, photos


def validate_review_data(data: Dict[str, Any]) -> Tuple[Company, int, str]:
    """Validate review data and return company, rating, text"""
    company_id = data.get('company')
    rating = data.get('rating')
    text = (data.get('text') or '').strip()

    if not company_id or not rating:
        raise ReviewError('company и rating обязательны')

    try:
        company = Company.objects.get(id=company_id, is_active=True)
    except Company.DoesNotExist:
        raise ReviewError('Компания не найдена', 404)

    rating = int(rating)
    if not 1 <= rating <= 5:
        raise ReviewError('rating должен быть от 1 до 5')

    if rating <= 3 and not text:
        raise ReviewError('Для оценки 1-3 текст обязателен')

    return company, rating, text


def validate_photos(photos: List, max_count: int = 5, max_size: int = 10 * 1024 * 1024):
    """Validate uploaded photos"""
    allowed_types = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']

    if len(photos) > max_count:
        raise ReviewError(f'Максимум {max_count} фото')

    for photo in photos:
        if photo.content_type not in allowed_types:
            raise ReviewError(f'Неподдерживаемый формат: {photo.name}')
        if photo.size > max_size:
            raise ReviewError(f'Файл слишком большой: {photo.name}')


def get_related_objects(data: Dict[str, Any], company: Company) -> Tuple[Optional[Spot], Optional[QR]]:
    """Get spot and QR code from data"""
    spot = None
    spot_id = data.get('spot')
    if spot_id:
        try:
            spot = Spot.objects.get(id=spot_id, company=company)
        except Spot.DoesNotExist:
            pass

    qr = None
    qr_code = data.get('qr_code')
    if qr_code:
        try:
            qr = QR.objects.get(code=qr_code, company=company)
        except QR.DoesNotExist:
            pass

    return spot, qr


def _get_sentiment(rating: int, has_negative: bool, has_positive: bool) -> str:
    """Determine sentiment based on rating and text markers."""
    base = 'positive' if rating >= 4 else ('negative' if rating <= 2 else 'neutral')
    if has_negative and not has_positive:
        return 'negative'
    if has_positive and not has_negative:
        return 'positive'
    return base


def _find_tags(text_lower: str, sentiment: str) -> List[Dict[str, str]]:
    """Find category tags in text."""
    found = set()
    tags = []
    for category, markers in CATEGORY_MARKERS.items():
        if category in found:
            continue
        for marker in markers:
            if marker in text_lower:
                found.add(category)
                subcategory = IMPRESSION_CATEGORIES.get(category, [''])[0]
                tags.append({'category': category, 'subcategory': subcategory, 'sentiment': sentiment})
                break
    return tags


def analyze_review_impressions(text: str, rating: int) -> List[Dict[str, str]]:
    """Analyze review text and determine impression categories."""
    base_sentiment = 'positive' if rating >= 4 else ('negative' if rating <= 2 else 'neutral')

    if not text:
        return [{'category': 'Общее', 'subcategory': 'Общее впечатление', 'sentiment': base_sentiment}]

    text_lower = text.lower()
    has_negative = any(re.search(p, text_lower) for p in NEGATIVE_MARKERS)
    has_positive = any(re.search(p, text_lower) for p in POSITIVE_BOOSTERS_WORDS)

    sentiment = _get_sentiment(rating, has_negative, has_positive)
    tags = _find_tags(text_lower, sentiment)

    if not tags:
        tags = [{'category': 'Общее', 'subcategory': 'Общее впечатление', 'sentiment': base_sentiment}]

    return tags


def create_review(company: Company, rating: int, text: str, data: Dict[str, Any],
                  spot: Optional[Spot], qr: Optional[QR], photos: List) -> Review:
    """Create review and save photos"""
    # Анализируем впечатления
    tags = analyze_review_impressions(text, rating)

    review = Review.objects.create(
        company=company,
        source=Review.Source.INTERNAL,
        spot=spot,
        qr=qr,
        rating=rating,
        text=text,
        author_name=data.get('author_name', 'Аноним') or 'Аноним',
        author_contact=data.get('author_contact') or '',
        ratings=data.get('ratings') if isinstance(data.get('ratings'), dict) else {},
        tags=tags,  # Сохраняем результат анализа
    )

    for photo in photos:
        ReviewPhoto.objects.create(review=review, image=photo)

    return review


def send_review_notification(review: Review):
    """Send Telegram notification for negative reviews"""
    if not review.is_negative:
        return

    from apps.notifications.telegram import notify_negative_review
    try:
        notify_negative_review(review)
    except Exception:
        pass  # Don't block review submission if notification fails


def get_spot_from_request(spot_id: Optional[str], company: Company) -> Optional[Spot]:
    """Get spot by ID if exists"""
    if not spot_id:
        return None
    try:
        return Spot.objects.get(id=spot_id, company=company)
    except (Spot.DoesNotExist, ValueError):
        return None


def get_redirect_platforms(company: Company) -> List[Dict[str, Any]]:
    """Get enabled platforms for positive review redirect"""
    from apps.companies.models import Connection

    platforms = []
    connections = Connection.objects.filter(
        company=company,
        sync_enabled=True
    ).select_related('platform')

    for conn in connections:
        if conn.external_url:
            platforms.append({
                'id': conn.platform_id,
                'name': conn.platform.name,
                'url': conn.external_url,
                'icon': conn.platform.icon or conn.platform_id[0].upper(),
            })
    return platforms
