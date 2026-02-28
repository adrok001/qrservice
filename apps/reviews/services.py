"""
Review business logic services.
Keeps views thin by extracting validation and processing logic.
"""
import json
from typing import Tuple, Optional, Dict, Any, List

from apps.companies.models import Company, Spot
from apps.qr.models import QR
from .models import Review, ReviewPhoto
from .segment_analyzer import find_aspect_tags, analyze_sentiment_dict


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
    return data, request.FILES.getlist('photos')


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


def analyze_review_impressions(text: str, rating: int) -> Tuple[List[Dict[str, str]], float]:
    """
    Analyze review text and determine impression categories.

    Использует словарный метод (RuSentiLex + HoReCa-словари).
    Точность 78% на 1593 реальных отзывах (vs 71% у ML).

    Returns:
        (tags, sentiment_score) — теги категорий и словарная оценка тональности
    """
    # Словарный анализ тональности
    sentiment, pos_count, neg_count = analyze_sentiment_dict(text)

    # Расчёт score от -1.0 до +1.0
    total = pos_count + neg_count
    if total > 0:
        sentiment_score = round((pos_count - neg_count) / total, 2)
    else:
        # Fallback на рейтинг если нет маркеров
        sentiment_score = 1.0 if rating >= 4 else (-1.0 if rating <= 2 else 0.0)

    # Определяем базовую тональность
    if sentiment == 'neutral' and total == 0:
        # Нет маркеров — используем рейтинг
        base_sentiment = 'positive' if rating >= 4 else ('negative' if rating <= 2 else 'neutral')
    else:
        base_sentiment = sentiment

    default_tag = [{'category': 'Общее', 'subcategory': 'Общее впечатление', 'sentiment': base_sentiment}]

    if not text:
        return (default_tag, sentiment_score)

    tags = find_aspect_tags(text)
    return (tags or default_tag, sentiment_score)


def is_tags_complex(rating: int, tags: List[Dict[str, str]]) -> bool:
    """
    Определяет, является ли отзыв «сложным» — конфликт между рейтингом и sentiment тегов.

    Словарный анализатор ошибается на сарказме, контексте и сложных отрицаниях.
    Если рейтинг и теги противоречат друг другу — помечаем отзыв как сложный,
    чтобы не вводить предпринимателя в заблуждение.
    """
    if not tags or not isinstance(tags, list):
        return False

    pos = sum(1 for t in tags if isinstance(t, dict) and t.get('sentiment') == 'positive')
    neg = sum(1 for t in tags if isinstance(t, dict) and t.get('sentiment') == 'negative')

    # Низкий рейтинг, но все теги positive
    if rating <= 3 and neg == 0 and pos > 0:
        return True

    # 1 звезда, но positive перевешивают negative
    if rating == 1 and neg < pos and neg > 0:
        return True

    # 5 звёзд, но все теги negative
    if rating == 5 and pos == 0 and neg > 0:
        return True

    # Высокий рейтинг, но negative сильно больше positive
    if rating >= 4 and neg > pos * 2 and neg > 0:
        return True

    return False


def create_review(company: Company, rating: int, text: str, data: Dict[str, Any],
                  spot: Optional[Spot], qr: Optional[QR], photos: List) -> Review:
    """Create review and save photos"""
    from .cache import get_analysis_cached
    tags, sentiment_score = get_analysis_cached(text, rating)

    review = Review.objects.create(
        company=company,
        source=Review.Source.INTERNAL,
        spot=spot,
        qr=qr,
        rating=rating,
        text=text,
        author_name=data.get('author_name', 'Аноним') or 'Аноним',
        author_contact=data.get('author_contact') or '',
        wants_contact=bool(data.get('wants_contact')),
        ratings=data.get('ratings') if isinstance(data.get('ratings'), dict) else {},
        tags=tags,
        tags_complex=is_tags_complex(rating, tags),
        sentiment_score=sentiment_score,
    )

    for photo in photos:
        ReviewPhoto.objects.create(review=review, image=photo)

    return review


def send_review_notification(review: Review):
    """
    Send Telegram notification for review.

    Уведомления отправляются:
    - Всем участникам с Telegram — для негативных отзывов (rating <= 3)
    - Участникам с telegram_notify_all=True — для всех отзывов
    """
    from apps.notifications.telegram import notify_review
    try:
        notify_review(review)
    except Exception:
        pass


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
        company=company, sync_enabled=True
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
