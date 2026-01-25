from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from apps.companies.models import Spot, Company, Connection, Platform
from apps.accounts.models import Member
from apps.qr.models import QR
from .services import (
    get_user_companies,
    get_current_company,
    get_review_counts,
    filter_reviews,
    update_feedback_settings,
    generate_qr_image,
    get_platforms_with_connections,
    update_company_info,
    update_platform_connections,
    auto_fill_address,
    build_platform_data,
    build_dashboard_context,
    build_form_settings_platform_data,
)


@login_required
def switch_company(request: HttpRequest, company_id: str) -> HttpResponseRedirect:
    """Switch between companies"""
    companies = get_user_companies(request.user)
    company_ids = [str(c.id) for c in companies]

    if company_id in company_ids:
        request.session['selected_company_id'] = company_id

    return redirect(request.META.get('HTTP_REFERER', 'dashboard:index'))


@login_required
def dashboard_index(request: HttpRequest) -> HttpResponse:
    """Dashboard main page."""
    company, companies = get_current_company(request)
    if not company:
        return render(request, 'dashboard/no_company.html')

    context = build_dashboard_context(company, companies, request)
    return render(request, 'dashboard/index.html', context)


@login_required
def reviews_list(request: HttpRequest) -> HttpResponse:
    """Reviews list with filters"""
    company, companies = get_current_company(request)
    if not company:
        return render(request, 'dashboard/no_company.html')

    reviews = filter_reviews(company, request.GET)
    filter_type = request.GET.get('filter')

    context = {
        'company': company,
        'companies': companies,
        'reviews': reviews[:50] if isinstance(reviews, list) else list(reviews)[:50],
        'counts': get_review_counts(company),
        'current_filter': filter_type or 'all',
        'current_source': request.GET.get('source'),
        'current_sentiment': request.GET.get('sentiment'),
        'current_category': request.GET.get('category'),
        'search': request.GET.get('search', ''),
    }
    return render(request, 'dashboard/reviews.html', context)


@login_required
def qr_list(request: HttpRequest) -> HttpResponse:
    """QR codes management"""
    company, companies = get_current_company(request)
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
def qr_create(request: HttpRequest) -> HttpResponse:
    """Create new QR code"""
    company, companies = get_current_company(request)
    if not company:
        return render(request, 'dashboard/no_company.html')

    spots = Spot.objects.filter(company=company, is_active=True)

    if request.method == 'POST':
        qr = QR.objects.create(
            company=company,
            spot_id=request.POST.get('spot') or None,
            color=request.POST.get('color', '#000000'),
            background=request.POST.get('background', '#FFFFFF'),
            created_by=request.user
        )
        generate_qr_image(qr)
        return redirect('dashboard:qr')

    return render(request, 'dashboard/qr_form.html', {
        'company': company,
        'companies': companies,
        'spots': spots,
    })


@login_required
def qr_edit(request: HttpRequest, qr_id: str) -> HttpResponse:
    """Edit QR code"""
    company, companies = get_current_company(request)
    if not company:
        return render(request, 'dashboard/no_company.html')

    qr = get_object_or_404(QR, id=qr_id, company=company)
    spots = Spot.objects.filter(company=company, is_active=True)

    if request.method == 'POST':
        qr.spot_id = request.POST.get('spot') or None
        qr.color = request.POST.get('color', '#000000')
        qr.background = request.POST.get('background', '#FFFFFF')
        qr.is_active = request.POST.get('is_active') == 'on'
        qr.save()
        generate_qr_image(qr)
        return redirect('dashboard:qr')

    return render(request, 'dashboard/qr_form.html', {
        'company': company,
        'companies': companies,
        'qr': qr,
        'spots': spots,
    })


@login_required
def qr_delete(request: HttpRequest, qr_id: str) -> HttpResponse:
    """Delete QR code"""
    company, companies = get_current_company(request)
    if not company:
        return render(request, 'dashboard/no_company.html')

    qr = get_object_or_404(QR, id=qr_id, company=company)

    if request.method == 'POST':
        qr.delete()
        return redirect('dashboard:qr')

    return render(request, 'dashboard/qr_delete.html', {
        'company': company,
        'companies': companies,
        'qr': qr,
    })


@login_required
def form_settings(request: HttpRequest) -> HttpResponse:
    """Feedback form settings."""
    company, companies = get_current_company(request)
    if not company:
        return render(request, 'dashboard/no_company.html')

    platform_data, platforms = build_form_settings_platform_data(company)

    if request.method == 'POST':
        update_feedback_settings(company, request.POST, platforms)
        return redirect('dashboard:form_settings')

    return render(request, 'dashboard/form_settings.html', {
        'company': company,
        'companies': companies,
        'feedback_settings': company.get_feedback_settings(),
        'platforms': platform_data,
    })


@login_required
def company_settings(request: HttpRequest) -> HttpResponse:
    """Company settings (logo, name, address)"""
    company, companies = get_current_company(request)
    if not company:
        return render(request, 'dashboard/no_company.html')

    if request.method == 'POST':
        update_company_info(company, request.POST, request.FILES)
        auto_fill_address(company, request.POST)
        return redirect('dashboard:company_settings')

    return render(request, 'dashboard/company_settings.html', {
        'company': company,
        'companies': companies,
    })


@login_required
def map_links_settings(request: HttpRequest) -> HttpResponse:
    """Map links settings (Yandex, Google, 2GIS)."""
    company, companies = get_current_company(request)
    if not company:
        return render(request, 'dashboard/no_company.html')

    platforms, connections = get_platforms_with_connections(company)

    if request.method == 'POST':
        update_platform_connections(company, platforms, request.POST, connections)
        messages.success(request, 'Ссылки сохранены')
        return redirect('dashboard:map_links_settings')

    return render(request, 'dashboard/map_links_settings.html', {
        'company': company,
        'companies': companies,
        'platforms': build_platform_data(platforms, connections),
    })


@login_required
def create_company(request: HttpRequest) -> HttpResponse:
    """Create new company from manual entry."""
    if request.method == 'POST':
        company_name = request.POST.get('company_name', '').strip()
        company_address = request.POST.get('company_address', '').strip()

        if not company_name:
            messages.error(request, 'Введите название компании')
            return redirect('dashboard:create_company')

        info = {'name': company_name, 'address': company_address}

        # Создаём компанию
        company = Company.objects.create(
            name=info['name'],
            address=info.get('address', ''),
        )

        # Создаём Member с ролью owner
        Member.objects.create(
            user=request.user,
            company=company,
            role=Member.Role.OWNER,
        )

        # Устанавливаем как текущую компанию
        request.session['selected_company_id'] = str(company.id)

        messages.success(request, f'Компания "{company.name}" создана! Теперь настройте её.')
        return redirect('dashboard:company_settings')

    # GET — показываем форму
    companies = get_user_companies(request.user)
    return render(request, 'dashboard/create_company.html', {
        'companies': companies,
    })
