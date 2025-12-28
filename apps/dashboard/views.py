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

    qr_codes = QR.objects.filter(company=company).select_related('spot').order_by('-created_at')

    context = {
        'company': company,
        'qr_codes': qr_codes,
    }

    return render(request, 'dashboard/qr.html', context)


@login_required
def qr_create(request):
    """Создание нового QR-кода"""
    from apps.companies.models import Spot

    company = get_user_company(request.user)
    if not company:
        return render(request, 'dashboard/no_company.html')

    spots = Spot.objects.filter(company=company, is_active=True)

    if request.method == 'POST':
        spot_id = request.POST.get('spot')
        color = request.POST.get('color', '#000000')
        background = request.POST.get('background', '#FFFFFF')

        qr = QR.objects.create(
            company=company,
            spot_id=spot_id if spot_id else None,
            color=color,
            background=background,
            created_by=request.user
        )

        # Генерируем изображение QR
        generate_qr_image(qr)

        return redirect('dashboard:qr')

    context = {
        'company': company,
        'spots': spots,
    }

    return render(request, 'dashboard/qr_form.html', context)


@login_required
def qr_edit(request, qr_id):
    """Редактирование QR-кода"""
    from apps.companies.models import Spot

    company = get_user_company(request.user)
    if not company:
        return render(request, 'dashboard/no_company.html')

    qr = get_object_or_404(QR, id=qr_id, company=company)
    spots = Spot.objects.filter(company=company, is_active=True)

    if request.method == 'POST':
        spot_id = request.POST.get('spot')
        color = request.POST.get('color', '#000000')
        background = request.POST.get('background', '#FFFFFF')
        is_active = request.POST.get('is_active') == 'on'

        qr.spot_id = spot_id if spot_id else None
        qr.color = color
        qr.background = background
        qr.is_active = is_active
        qr.save()

        # Регенерируем изображение если изменились цвета
        generate_qr_image(qr)

        return redirect('dashboard:qr')

    context = {
        'company': company,
        'qr': qr,
        'spots': spots,
    }

    return render(request, 'dashboard/qr_form.html', context)


@login_required
def qr_delete(request, qr_id):
    """Удаление QR-кода"""
    company = get_user_company(request.user)
    if not company:
        return render(request, 'dashboard/no_company.html')

    qr = get_object_or_404(QR, id=qr_id, company=company)

    if request.method == 'POST':
        qr.delete()
        return redirect('dashboard:qr')

    context = {
        'company': company,
        'qr': qr,
    }

    return render(request, 'dashboard/qr_delete.html', context)


def generate_qr_image(qr):
    """Генерация изображения QR-кода"""
    import qrcode
    from io import BytesIO
    from django.core.files.base import ContentFile
    from django.conf import settings

    # URL для QR-кода
    base_url = getattr(settings, 'SITE_URL', 'http://localhost:8000')
    url = f"{base_url}/{qr.code}"

    # Создаём QR-код
    qr_image = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr_image.add_data(url)
    qr_image.make(fit=True)

    # Цвета
    fill_color = qr.color or '#000000'
    back_color = qr.background or '#FFFFFF'

    img = qr_image.make_image(fill_color=fill_color, back_color=back_color)

    # Сохраняем в BytesIO
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)

    # Сохраняем в модель
    filename = f'qr_{qr.code}.png'
    qr.image.save(filename, ContentFile(buffer.read()), save=True)
