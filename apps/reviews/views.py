import json
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, Http404
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt

from apps.companies.models import Company, Spot
from apps.qr.models import QR
from .models import Review


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

    context = {
        'company': company,
        'spot': spot,
        'qr_code': qr_code,
    }

    return render(request, 'reviews/feedback_form.html', context)


def feedback_step2(request, company_slug):
    """Форма отзыва — экран 2 (детали)"""
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

    context = {
        'company': company,
        'spot': spot,
        'qr_code': qr_code,
        'rating': rating,
        'is_positive': is_positive,
    }

    return render(request, 'reviews/feedback_step2.html', context)


@csrf_exempt
@require_POST
def submit_review(request):
    """API для отправки отзыва"""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    # Валидация
    company_id = data.get('company')
    rating = data.get('rating')
    text = data.get('text', '').strip()

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
        author_contact=data.get('author_contact', ''),
        ratings=data.get('ratings', {}),
        # is_public и sentiment устанавливаются автоматически в save()
    )

    return JsonResponse({
        'success': True,
        'review_id': str(review.id),
        'is_public': review.is_public,
    })


def thank_you(request):
    """Экран благодарности после отправки отзыва"""
    return render(request, 'reviews/thank_you.html')
