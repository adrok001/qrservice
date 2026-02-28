import json
import logging
import uuid
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.utils import timezone

from apps.accounts.models import Member
from .models import Review
from .impression_categories import IMPRESSION_CATEGORIES

logger = logging.getLogger(__name__)

VALID_CATEGORIES = set(IMPRESSION_CATEGORIES.keys())
VALID_SUBCATEGORIES = {}
for cat, subcats in IMPRESSION_CATEGORIES.items():
    for sub in subcats:
        VALID_SUBCATEGORIES[(cat, sub)] = True


@login_required
@require_POST
def respond_to_review(request: HttpRequest, review_id: uuid.UUID) -> JsonResponse:
    """API для ответа на отзыв"""
    logger.info(f"respond_to_review called with review_id={review_id}")

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        logger.error("Invalid JSON in request body")
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    response_text = data.get('response', '').strip()
    if not response_text:
        return JsonResponse({'error': 'Ответ не может быть пустым'}, status=400)

    try:
        review = Review.objects.get(id=review_id)
    except Review.DoesNotExist:
        return JsonResponse({'error': 'Отзыв не найден'}, status=404)

    # Проверяем права
    membership = Member.objects.filter(
        user=request.user,
        company=review.company,
        is_active=True
    ).first()

    if not membership or not membership.can_respond():
        return JsonResponse({'error': 'Нет прав для ответа'}, status=403)

    # Сохраняем ответ
    review.response = response_text
    review.response_at = timezone.now()
    review.response_by = request.user
    review.status = Review.Status.RESOLVED
    review.save()

    # Если это отзыв из Google — отправляем ответ в Google
    pushed_to_google = False
    if review.source == Review.Source.GOOGLE and review.external_id:
        try:
            from apps.integrations.tasks import push_review_reply
            push_review_reply.delay(str(review.id))
            pushed_to_google = True
        except Exception:
            # Celery may not be running, continue anyway
            pass

    return JsonResponse({
        'success': True,
        'response': response_text,
        'response_at': review.response_at.isoformat(),
        'pushed_to_google': pushed_to_google,
    })


@login_required
@require_POST
def manual_tag_review(request: HttpRequest, review_id: uuid.UUID) -> JsonResponse:
    """API для ручной маркировки сложного отзыва"""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    tags = data.get('tags', [])
    if not tags:
        return JsonResponse({'error': 'Укажите хотя бы одну категорию'}, status=400)

    try:
        review = Review.objects.get(id=review_id)
    except Review.DoesNotExist:
        return JsonResponse({'error': 'Отзыв не найден'}, status=404)

    membership = Member.objects.filter(
        user=request.user,
        company=review.company,
        is_active=True
    ).first()
    if not membership:
        return JsonResponse({'error': 'Нет прав'}, status=403)

    validated_tags = []
    for tag in tags:
        cat = tag.get('category', '')
        sub = tag.get('subcategory', '')
        sent = tag.get('sentiment', '')
        if (cat, sub) in VALID_SUBCATEGORIES and sent in ('positive', 'negative'):
            validated_tags.append({
                'category': cat,
                'subcategory': sub,
                'sentiment': sent,
                'marker': 'manual',
                'evidence': [],
            })

    if not validated_tags:
        return JsonResponse({'error': 'Некорректные данные'}, status=400)

    review.tags = validated_tags
    review.tags_complex = False
    review.save(update_fields=['tags', 'tags_complex'])

    return JsonResponse({'success': True, 'tags': validated_tags})
