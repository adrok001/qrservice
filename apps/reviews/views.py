import json
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, Http404
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt

from apps.companies.models import Company, Spot
from apps.qr.models import QR
from .models import Review, ReviewPhoto


def feedback_form(request, company_slug):
    """Форма отзыва — экран 1 (выбор звёзд)"""
    company = get_object_or_404(Company, slug=company_slug, is_active=True)

    # Получаем spot если передан
    spot = None
    spot_id = request.GET.get('spot')
    if spot_id:
        try:
            spot = Spot.objects.get(id=spot_id, company=company)
        except (Spot.DoesNotExist, ValueError):
            pass

    # QR-код для отслеживания
    qr_code = request.GET.get('qr', '')

    # Настройки формы
    feedback_settings = company.get_feedback_settings()

    context = {
        'company': company,
        'spot': spot,
        'qr_code': qr_code,
        'settings': feedback_settings,
    }

    return render(request, 'reviews/feedback_form.html', context)


def feedback_step2(request, company_slug):
    """Форма отзыва — экран 2 (детали)"""
    from apps.companies.models import Connection

    company = get_object_or_404(Company, slug=company_slug, is_active=True)

    rating = int(request.GET.get('rating', 0))
    if not 1 <= rating <= 5:
        return redirect('feedback:form', company_slug=company_slug)

    spot_id = request.GET.get('spot')
    spot = None
    if spot_id:
        try:
            spot = Spot.objects.get(id=spot_id, company=company)
        except (Spot.DoesNotExist, ValueError):
            pass

    qr_code = request.GET.get('qr', '')

    # Определяем тип флоу
    is_positive = rating >= 4

    # Для позитивных отзывов — получаем платформы для редиректа
    platforms = []
    if is_positive:
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

    # Настройки формы
    feedback_settings = company.get_feedback_settings()

    context = {
        'company': company,
        'spot': spot,
        'qr_code': qr_code,
        'rating': rating,
        'is_positive': is_positive,
        'platforms': platforms,
        'settings': feedback_settings,
    }

    return render(request, 'reviews/feedback_step2.html', context)


@csrf_exempt
@require_POST
def submit_review(request):
    """API для отправки отзыва (FormData или JSON)"""
    # Определяем формат данных
    content_type = request.content_type or ''

    if 'multipart/form-data' in content_type:
        # FormData (с файлами)
        data = request.POST
        photos = request.FILES.getlist('photos')
    elif 'application/json' in content_type:
        # JSON
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        photos = []
    else:
        # Fallback - попробуем POST
        data = request.POST if request.POST else {}
        photos = request.FILES.getlist('photos')
        if not data:
            try:
                data = json.loads(request.body)
            except (json.JSONDecodeError, ValueError):
                return JsonResponse({'error': 'Invalid data'}, status=400)

    # Валидация
    company_id = data.get('company')
    rating = data.get('rating')
    text = (data.get('text') or '').strip()

    if not company_id or not rating:
        return JsonResponse({'error': 'company и rating обязательны'}, status=400)

    try:
        company = Company.objects.get(id=company_id, is_active=True)
    except Company.DoesNotExist:
        return JsonResponse({'error': 'Компания не найдена'}, status=404)

    rating = int(rating)
    if not 1 <= rating <= 5:
        return JsonResponse({'error': 'rating должен быть от 1 до 5'}, status=400)

    # Для негативных отзывов текст обязателен
    if rating <= 3 and not text:
        return JsonResponse({'error': 'Для оценки 1-3 текст обязателен'}, status=400)

    # Валидация фото (до 5 штук, по 10 МБ каждое)
    allowed_types = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
    max_photos = 5
    max_size = 10 * 1024 * 1024  # 10 MB

    if len(photos) > max_photos:
        return JsonResponse({'error': f'Максимум {max_photos} фото'}, status=400)

    for photo in photos:
        if photo.content_type not in allowed_types:
            return JsonResponse({'error': f'Неподдерживаемый формат: {photo.name}'}, status=400)
        if photo.size > max_size:
            return JsonResponse({'error': f'Файл слишком большой: {photo.name}'}, status=400)

    # Получаем связанные объекты
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

    # Создаём отзыв
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
    )

    # Сохраняем прикреплённые фото
    for photo in photos:
        ReviewPhoto.objects.create(review=review, image=photo)

    # Отправляем уведомление о негативном отзыве в Telegram
    if review.is_negative:
        from apps.notifications.telegram import notify_negative_review
        try:
            notify_negative_review(review)
        except Exception:
            pass  # Не блокируем отправку отзыва если уведомление не отправилось

    return JsonResponse({
        'success': True,
        'review_id': str(review.id),
        'is_public': review.is_public,
    })


def thank_you(request):
    """Экран благодарности после отправки отзыва"""
    # Пробуем получить настройки компании
    company_slug = request.GET.get('c')
    settings = None
    company = None

    if company_slug:
        try:
            company = Company.objects.get(slug=company_slug, is_active=True)
            settings = company.get_feedback_settings()
        except Company.DoesNotExist:
            pass

    # Дефолтные настройки если компания не найдена
    if not settings:
        settings = {
            'thank_you_title': 'Спасибо за отзыв!',
            'thank_you_subtitle': 'Ваше мнение помогает нам становиться лучше',
            'bg_color': '#f8f9fa',
        }

    context = {
        'company': company,
        'settings': settings,
    }
    return render(request, 'reviews/thank_you.html', context)
