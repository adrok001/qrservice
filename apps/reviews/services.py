"""
Review business logic services.
Keeps views thin by extracting validation and processing logic.
"""
import json
from typing import Tuple, Optional, Dict, Any, List

from apps.companies.models import Company, Spot
from apps.qr.models import QR
from .models import Review, ReviewPhoto
from .impression_categories import (
    CATEGORY_MARKERS,
    IMPRESSION_CATEGORIES,
    POSITIVE_SEGMENT_MARKERS,
    NEGATIVE_SEGMENT_MARKERS,
)
import re
from .ml_analyzer import analyze_sentiment_ml, sentiment_to_score


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


def _build_segment_pattern():
    """Build combined regex pattern for segment detection."""
    all_patterns = []
    for p in POSITIVE_SEGMENT_MARKERS:
        all_patterns.append(f"(?P<pos_{len(all_patterns)}>{p})")
    for p in NEGATIVE_SEGMENT_MARKERS:
        all_patterns.append(f"(?P<neg_{len(all_patterns)}>{p})")
    return re.compile('|'.join(all_patterns), re.IGNORECASE)


_SEGMENT_PATTERN = None


def _get_segment_pattern():
    """Lazy init segment pattern."""
    global _SEGMENT_PATTERN
    if _SEGMENT_PATTERN is None:
        _SEGMENT_PATTERN = _build_segment_pattern()
    return _SEGMENT_PATTERN


def _segment_text(text: str) -> List[Tuple[str, str]]:
    """
    Разбивает текст на сегменты с тональностью.

    Returns:
        List of (segment_text, sentiment_hint) where sentiment_hint is
        'positive', 'negative', or 'default'
    """
    text_lower = text.lower()
    pattern = _get_segment_pattern()

    # Find all segment markers
    markers = []
    for match in pattern.finditer(text_lower):
        # Determine if positive or negative marker
        for name in match.groupdict():
            if match.group(name) is not None:
                marker_type = 'positive' if name.startswith('pos_') else 'negative'
                markers.append((match.start(), match.end(), marker_type))
                break

    if not markers:
        return [(text_lower, 'default')]

    # Build segments
    segments = []
    prev_end = 0
    prev_sentiment = 'default'

    for start, end, sentiment in markers:
        # Text before this marker
        if start > prev_end:
            segment_text = text_lower[prev_end:start].strip()
            if segment_text:
                segments.append((segment_text, prev_sentiment))
        prev_end = end
        prev_sentiment = sentiment

    # Remaining text after last marker
    if prev_end < len(text_lower):
        segment_text = text_lower[prev_end:].strip()
        if segment_text:
            segments.append((segment_text, prev_sentiment))

    return segments if segments else [(text_lower, 'default')]


def _find_tags_in_segment(segment: str, sentiment: str, found: set) -> List[Dict[str, str]]:
    """Find category tags in a single segment."""
    tags = []
    for category, markers in CATEGORY_MARKERS.items():
        if category in found:
            continue
        for marker in markers:
            if marker in segment:
                found.add(category)
                subcategory = IMPRESSION_CATEGORIES.get(category, [''])[0]
                tags.append({'category': category, 'subcategory': subcategory, 'sentiment': sentiment})
                break
    return tags


def _find_tags(text_lower: str, base_sentiment: str) -> List[Dict[str, str]]:
    """Find category tags in text with segment-aware sentiment."""
    segments = _segment_text(text_lower)
    found = set()
    tags = []

    for segment_text, segment_hint in segments:
        # Determine sentiment for this segment
        if segment_hint == 'default':
            sentiment = base_sentiment
        else:
            sentiment = segment_hint

        segment_tags = _find_tags_in_segment(segment_text, sentiment, found)
        tags.extend(segment_tags)

    return tags


def analyze_review_impressions(text: str, rating: int) -> Tuple[List[Dict[str, str]], float]:
    """
    Analyze review text and determine impression categories.

    Returns:
        (tags, sentiment_score) — теги категорий и ML-оценка тональности
    """
    # ML-анализ тональности
    ml_sentiment, ml_confidence = analyze_sentiment_ml(text)
    sentiment_score = sentiment_to_score(ml_sentiment, ml_confidence)

    # Fallback на рейтинг при низкой уверенности
    if ml_confidence < 0.6:
        base_sentiment = 'positive' if rating >= 4 else ('negative' if rating <= 2 else 'neutral')
    else:
        base_sentiment = ml_sentiment

    if not text:
        return ([{'category': 'Общее', 'subcategory': 'Общее впечатление', 'sentiment': base_sentiment}], sentiment_score)

    text_lower = text.lower()

    # Определение категорий по маркерам (оставляем regex для категорий)
    tags = _find_tags(text_lower, base_sentiment)

    if not tags:
        tags = [{'category': 'Общее', 'subcategory': 'Общее впечатление', 'sentiment': base_sentiment}]

    return (tags, sentiment_score)


def create_review(company: Company, rating: int, text: str, data: Dict[str, Any],
                  spot: Optional[Spot], qr: Optional[QR], photos: List) -> Review:
    """Create review and save photos"""
    # Анализируем впечатления с ML
    tags, sentiment_score = analyze_review_impressions(text, rating)

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
        tags=tags,
        sentiment_score=sentiment_score,  # ML-оценка тональности
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
