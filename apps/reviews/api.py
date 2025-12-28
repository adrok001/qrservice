import json
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.utils import timezone

from apps.accounts.models import Member
from .models import Review


@login_required
@require_POST
def respond_to_review(request, review_id):
    """API для ответа на отзыв"""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
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
