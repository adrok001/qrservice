from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt

from apps.companies.models import Company, Spot
from .models import Review
from .services import (
    ReviewError,
    parse_request_data,
    validate_review_data,
    validate_photos,
    get_related_objects,
    create_review,
    send_review_notification,
    get_spot_from_request,
    get_redirect_platforms,
)


def feedback_form(request: HttpRequest, company_slug: str) -> HttpResponse:
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


def feedback_step2(request: HttpRequest, company_slug: str) -> HttpResponse:
    """Форма отзыва — экран 2 (детали)"""
    company = get_object_or_404(Company, slug=company_slug, is_active=True)

    rating = int(request.GET.get('rating', 0))
    if not 1 <= rating <= 5:
        return redirect('feedback:form', company_slug=company_slug)

    is_positive = rating >= 4

    context = {
        'company': company,
        'spot': get_spot_from_request(request.GET.get('spot'), company),
        'qr_code': request.GET.get('qr', ''),
        'rating': rating,
        'is_positive': is_positive,
        'platforms': get_redirect_platforms(company) if is_positive else [],
        'settings': company.get_feedback_settings(),
    }

    return render(request, 'reviews/feedback_step2.html', context)


# CSRF отключён: публичный API для формы обратной связи.
# Форма встраивается на внешние сайты и отправляет данные через JS fetch.
# Защита обеспечена валидацией company_id и rate limiting на уровне веб-сервера.
@csrf_exempt
@require_POST
def submit_review(request: HttpRequest) -> JsonResponse:
    """API для отправки отзыва (FormData или JSON)"""
    try:
        data, photos = parse_request_data(request)
        company, rating, text = validate_review_data(data)
        validate_photos(photos)
        spot, qr = get_related_objects(data, company)
        review = create_review(company, rating, text, data, spot, qr, photos)
        send_review_notification(review)

        return JsonResponse({
            'success': True,
            'review_id': str(review.id),
            'is_public': review.is_public,
        })
    except ReviewError as e:
        return JsonResponse({'error': e.message}, status=e.status)


def thank_you(request: HttpRequest) -> HttpResponse:
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
