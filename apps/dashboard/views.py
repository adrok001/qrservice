from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, Q
from django.utils import timezone
from datetime import timedelta

from apps.accounts.models import Member
from apps.companies.models import Company
from apps.reviews.models import Review
from apps.qr.models import QR


def get_user_company(user):
    """Получить компанию пользователя (первую доступную)"""
    membership = Member.objects.filter(user=user, is_active=True).first()
    if membership:
        return membership.company
    return None


@login_required
def dashboard_index(request):
    """Главная страница дашборда"""
    company = get_user_company(request.user)
    if not company:
        return render(request, 'dashboard/no_company.html')

    # Период: последние 30 дней
    since = timezone.now() - timedelta(days=30)

    # Статистика отзывов
    reviews = Review.objects.filter(company=company)
    reviews_month = reviews.filter(created_at__gte=since)

    stats = {
        'avg_rating': reviews.aggregate(avg=Avg('rating'))['avg'] or 0,
        'new_reviews': reviews_month.count(),
        'negative_count': reviews_month.filter(rating__lte=3).count(),
        'total_scans': QR.objects.filter(company=company).aggregate(total=Count('scans'))['total'] or 0,
    }

    # Округляем рейтинг
    stats['avg_rating'] = round(stats['avg_rating'], 1)

    # Отзывы, требующие внимания (негативные без ответа)
    attention_reviews = reviews.filter(
        rating__lte=3,
        response='',
        status='new'
    ).order_by('-created_at')[:5]

    # Последние отзывы
    recent_reviews = reviews.order_by('-created_at')[:5]

    context = {
        'company': company,
        'stats': stats,
        'attention_reviews': attention_reviews,
        'recent_reviews': recent_reviews,
    }

    return render(request, 'dashboard/index.html', context)


@login_required
def reviews_list(request):
    """Список отзывов с фильтрами"""
    company = get_user_company(request.user)
    if not company:
        return render(request, 'dashboard/no_company.html')

    reviews = Review.objects.filter(company=company)

    # Фильтры
    source = request.GET.get('source')
    if source:
        reviews = reviews.filter(source=source)

    rating = request.GET.get('rating')
    if rating:
        reviews = reviews.filter(rating=int(rating))

    filter_type = request.GET.get('filter')
    if filter_type == 'negative':
        reviews = reviews.filter(rating__lte=3)
    elif filter_type == 'no_response':
        reviews = reviews.filter(response='')
    elif filter_type == 'new':
        reviews = reviews.filter(status='new')

    search = request.GET.get('search')
    if search:
        reviews = reviews.filter(
            Q(text__icontains=search) |
            Q(author_name__icontains=search)
        )

    # Сортировка
    reviews = reviews.order_by('-created_at')

    # Счётчики для табов
    counts = {
        'all': Review.objects.filter(company=company).count(),
        'new': Review.objects.filter(company=company, status='new').count(),
        'negative': Review.objects.filter(company=company, rating__lte=3).count(),
        'no_response': Review.objects.filter(company=company, response='').count(),
    }

    context = {
        'company': company,
        'reviews': reviews[:50],  # Пагинация потом
        'counts': counts,
        'current_filter': filter_type or 'all',
        'current_source': source,
        'search': search or '',
    }

    return render(request, 'dashboard/reviews.html', context)


@login_required
def qr_list(request):
    """Управление QR-кодами"""
    company = get_user_company(request.user)
    if not company:
        return render(request, 'dashboard/no_company.html')

    qr_codes = QR.objects.filter(company=company).order_by('-created_at')

    context = {
        'company': company,
        'qr_codes': qr_codes,
    }

    return render(request, 'dashboard/qr.html', context)
