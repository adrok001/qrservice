from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, Q
from django.utils import timezone
from datetime import timedelta

from apps.accounts.models import Member
from apps.companies.models import Company
from apps.reviews.models import Review
from apps.qr.models import QR


def get_user_companies(user):
    """Получить все компании пользователя"""
    memberships = Member.objects.filter(user=user, is_active=True).select_related('company')
    return [m.company for m in memberships]


def get_user_company(request):
    """Получить текущую компанию пользователя (из сессии или первую доступную)"""
    user = request.user
    companies = get_user_companies(user)

    if not companies:
        return None, []

    # Проверяем сессию
    selected_id = request.session.get('selected_company_id')
    if selected_id:
        for company in companies:
            if str(company.id) == selected_id:
                return company, companies

    # Возвращаем первую компанию
    return companies[0], companies


@login_required
def switch_company(request, company_id):
    """Переключение между компаниями"""
    companies = get_user_companies(request.user)
    company_ids = [str(c.id) for c in companies]

    if company_id in company_ids:
        request.session['selected_company_id'] = company_id

    return redirect(request.META.get('HTTP_REFERER', 'dashboard:index'))


@login_required
def dashboard_index(request):
    """Главная страница дашборда"""
    company, companies = get_user_company(request)
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
        'companies': companies,
        'stats': stats,
        'attention_reviews': attention_reviews,
        'recent_reviews': recent_reviews,
    }

    return render(request, 'dashboard/index.html', context)


@login_required
def reviews_list(request):
    """Список отзывов с фильтрами"""
    company, companies = get_user_company(request)
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
        'companies': companies,
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
    company, companies = get_user_company(request)
    if not company:
        return render(request, 'dashboard/no_company.html')

    qr_codes = QR.objects.filter(company=company).select_related('spot').order_by('-created_at')

    context = {
        'company': company,
        'companies': companies,
        'qr_codes': qr_codes,
    }

    return render(request, 'dashboard/qr.html', context)


@login_required
def qr_create(request):
    """Создание нового QR-кода"""
    from apps.companies.models import Spot

    company, companies = get_user_company(request)
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
        'companies': companies,
        'spots': spots,
    }

    return render(request, 'dashboard/qr_form.html', context)


@login_required
def qr_edit(request, qr_id):
    """Редактирование QR-кода"""
    from apps.companies.models import Spot

    company, companies = get_user_company(request)
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
        'companies': companies,
        'qr': qr,
        'spots': spots,
    }

    return render(request, 'dashboard/qr_form.html', context)


@login_required
def qr_delete(request, qr_id):
    """Удаление QR-кода"""
    company, companies = get_user_company(request)
    if not company:
        return render(request, 'dashboard/no_company.html')

    qr = get_object_or_404(QR, id=qr_id, company=company)

    if request.method == 'POST':
        qr.delete()
        return redirect('dashboard:qr')

    context = {
        'company': company,
        'companies': companies,
        'qr': qr,
    }

    return render(request, 'dashboard/qr_delete.html', context)


@login_required
def form_settings(request):
    """Настройки формы обратной связи"""
    from apps.companies.models import Connection

    company, companies = get_user_company(request)
    if not company:
        return render(request, 'dashboard/no_company.html')

    # Получаем подключённые платформы
    connections = Connection.objects.filter(company=company).select_related('platform')

    if request.method == 'POST':
        # Получаем текущие настройки
        settings = company.settings or {}
        feedback = settings.get('feedback', {})

        # Обновляем
        feedback['title'] = request.POST.get('title', '').strip() or 'Как вам у нас?'
        feedback['subtitle'] = request.POST.get('subtitle', '').strip()
        feedback['bg_color'] = request.POST.get('bg_color', '#f8f9fa')
        feedback['positive_title'] = request.POST.get('positive_title', '').strip()
        feedback['positive_subtitle'] = request.POST.get('positive_subtitle', '').strip()
        feedback['negative_title'] = request.POST.get('negative_title', '').strip()
        feedback['negative_subtitle'] = request.POST.get('negative_subtitle', '').strip()
        feedback['thank_you_title'] = request.POST.get('thank_you_title', '').strip()
        feedback['thank_you_subtitle'] = request.POST.get('thank_you_subtitle', '').strip()
        feedback['show_internal_form'] = request.POST.get('show_internal_form') == 'on'

        settings['feedback'] = feedback
        company.settings = settings
        company.save(update_fields=['settings'])

        # Обновляем статус платформ
        enabled_platforms = request.POST.getlist('platforms')
        for conn in connections:
            conn.sync_enabled = conn.platform_id in enabled_platforms
            conn.save(update_fields=['sync_enabled'])

        return redirect('dashboard:form_settings')

    context = {
        'company': company,
        'companies': companies,
        'feedback_settings': company.get_feedback_settings(),
        'connections': connections,
    }

    return render(request, 'dashboard/form_settings.html', context)


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


@login_required
def company_settings(request):
    """Настройки компании (логотип, название)"""
    company, companies = get_user_company(request)
    if not company:
        return render(request, 'dashboard/no_company.html')

    if request.method == 'POST':
        # Обновляем название
        name = request.POST.get('name', '').strip()
        if name:
            company.name = name

        # Загружаем логотип
        if 'logo' in request.FILES:
            logo = request.FILES['logo']
            # Проверяем тип файла
            if logo.content_type in ['image/jpeg', 'image/png', 'image/gif', 'image/webp']:
                # Удаляем старый логотип
                if company.logo:
                    company.logo.delete(save=False)
                company.logo = logo

        # Удаление логотипа
        if request.POST.get('delete_logo') == '1':
            if company.logo:
                company.logo.delete(save=False)
                company.logo = None

        company.save()
        return redirect('dashboard:company_settings')

    context = {
        'company': company,
        'companies': companies,
    }

    return render(request, 'dashboard/company_settings.html', context)
