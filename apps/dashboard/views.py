from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required

from apps.companies.models import Company, Spot, Connection
from apps.qr.models import QR
from .services import (
    get_user_companies,
    get_current_company,
    get_dashboard_stats,
    get_attention_reviews,
    get_recent_reviews,
    get_review_counts,
    filter_reviews,
    update_feedback_settings,
    generate_qr_image,
)


@login_required
def switch_company(request, company_id):
    """Switch between companies"""
    companies = get_user_companies(request.user)
    company_ids = [str(c.id) for c in companies]

    if company_id in company_ids:
        request.session['selected_company_id'] = company_id

    return redirect(request.META.get('HTTP_REFERER', 'dashboard:index'))


@login_required
def dashboard_index(request):
    """Dashboard main page"""
    company, companies = get_current_company(request)
    if not company:
        return render(request, 'dashboard/no_company.html')

    context = {
        'company': company,
        'companies': companies,
        'stats': get_dashboard_stats(company),
        'attention_reviews': get_attention_reviews(company),
        'recent_reviews': get_recent_reviews(company),
    }
    return render(request, 'dashboard/index.html', context)


@login_required
def reviews_list(request):
    """Reviews list with filters"""
    company, companies = get_current_company(request)
    if not company:
        return render(request, 'dashboard/no_company.html')

    reviews = filter_reviews(company, request.GET)
    filter_type = request.GET.get('filter')

    context = {
        'company': company,
        'companies': companies,
        'reviews': reviews[:50],
        'counts': get_review_counts(company),
        'current_filter': filter_type or 'all',
        'current_source': request.GET.get('source'),
        'search': request.GET.get('search', ''),
    }
    return render(request, 'dashboard/reviews.html', context)


@login_required
def qr_list(request):
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
def qr_create(request):
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
def qr_edit(request, qr_id):
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
def qr_delete(request, qr_id):
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
def form_settings(request):
    """Feedback form settings"""
    from apps.companies.models import Platform

    company, companies = get_current_company(request)
    if not company:
        return render(request, 'dashboard/no_company.html')

    # Get all active platforms with their connections for this company
    platforms = Platform.objects.filter(is_active=True)
    connections = {c.platform_id: c for c in Connection.objects.filter(company=company)}

    # Build platform data with connection info
    platform_data = []
    for platform in platforms:
        conn = connections.get(platform.id)
        platform_data.append({
            'id': platform.id,
            'name': platform.name,
            'enabled': conn.sync_enabled if conn else False,
            'url': conn.external_url if conn else '',
        })

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
def company_settings(request):
    """Company settings (logo, name)"""
    company, companies = get_current_company(request)
    if not company:
        return render(request, 'dashboard/no_company.html')

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if name:
            company.name = name

        if 'logo' in request.FILES:
            logo = request.FILES['logo']
            allowed_types = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
            if logo.content_type in allowed_types:
                if company.logo:
                    company.logo.delete(save=False)
                company.logo = logo

        if request.POST.get('delete_logo') == '1' and company.logo:
            company.logo.delete(save=False)
            company.logo = None

        company.save()
        return redirect('dashboard:company_settings')

    return render(request, 'dashboard/company_settings.html', {
        'company': company,
        'companies': companies,
    })
