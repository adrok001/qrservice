"""Views for platform integrations (OAuth callbacks, settings)."""

import logging
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST

from apps.accounts.models import Member
from apps.companies.models import Company, Connection, Platform
from apps.dashboard.services import get_current_company

from .services import GoogleAuthService, GoogleReviewsService
from .tasks import sync_google_reviews

logger = logging.getLogger(__name__)


def get_user_company(user):
    """Get the company for current user."""
    membership = Member.objects.filter(user=user, is_active=True).first()
    return membership.company if membership else None


@login_required
def integrations_settings(request):
    """Settings page for managing platform integrations."""
    company, companies = get_current_company(request)
    if not company:
        return render(request, 'dashboard/no_company.html')

    # Check user permissions
    membership = Member.objects.get(user=request.user, company=company)
    if not membership.can_manage():
        messages.error(request, 'У вас нет прав для управления интеграциями')
        return redirect('dashboard:index')

    # Get existing connections
    connections = Connection.objects.filter(company=company).select_related('platform')

    # Check if Google OAuth is configured
    auth_service = GoogleAuthService()

    context = {
        'company': company,
        'companies': companies,
        'connections': connections,
        'google_configured': auth_service.is_configured,
        'platforms': Platform.objects.filter(is_active=True),
    }

    return render(request, 'integrations/settings.html', context)


@login_required
def google_connect(request):
    """Start Google OAuth flow."""
    company = get_user_company(request.user)
    if not company:
        messages.error(request, 'Нет доступной компании')
        return redirect('dashboard:index')

    # Check permissions
    membership = Member.objects.get(user=request.user, company=company)
    if not membership.can_manage():
        messages.error(request, 'У вас нет прав для подключения интеграций')
        return redirect('dashboard:index')

    auth_service = GoogleAuthService()

    if not auth_service.is_configured:
        messages.error(
            request,
            'Google API не настроен. Добавьте GOOGLE_CLIENT_ID и '
            'GOOGLE_CLIENT_SECRET в .env файл.'
        )
        return redirect('integrations:settings')

    try:
        # Use company ID as state parameter
        state = str(company.id)
        auth_url = auth_service.get_authorization_url(state=state)
        return HttpResponseRedirect(auth_url)
    except Exception as e:
        logger.exception('Failed to start Google OAuth')
        messages.error(request, f'Ошибка при подключении: {str(e)}')
        return redirect('integrations:settings')


@login_required
def google_callback(request):
    """Handle Google OAuth callback."""
    code = request.GET.get('code')
    state = request.GET.get('state')  # company_id
    error = request.GET.get('error')

    if error:
        messages.error(request, f'Google отклонил авторизацию: {error}')
        return redirect('integrations:settings')

    if not code or not state:
        messages.error(request, 'Неверные параметры callback')
        return redirect('integrations:settings')

    # Verify company access
    try:
        company = Company.objects.get(id=state)
        membership = Member.objects.get(
            user=request.user,
            company=company,
            is_active=True
        )
        if not membership.can_manage():
            raise ValueError('No permission')
    except (Company.DoesNotExist, Member.DoesNotExist, ValueError):
        messages.error(request, 'Нет доступа к компании')
        return redirect('dashboard:index')

    # Exchange code for tokens
    auth_service = GoogleAuthService()
    try:
        tokens = auth_service.exchange_code_for_tokens(code, state)
    except Exception as e:
        logger.exception('Failed to exchange OAuth code')
        messages.error(request, f'Ошибка авторизации: {str(e)}')
        return redirect('integrations:settings')

    # Get or create Google platform
    platform, _ = Platform.objects.get_or_create(
        id='google',
        defaults={'name': 'Google Business', 'is_active': True}
    )

    # Create or update connection
    connection, created = Connection.objects.update_or_create(
        company=company,
        platform=platform,
        defaults={
            'access_token': tokens['access_token'],
            'refresh_token': tokens.get('refresh_token', ''),
            'token_expires_at': tokens['expires_at'],
            'external_id': 'pending',  # Will be updated after fetching account info
            'sync_enabled': True,
        }
    )

    if created:
        messages.success(request, 'Google Business успешно подключен!')
    else:
        messages.success(request, 'Подключение к Google Business обновлено!')

    # Redirect to account selection page (or settings if no account selection needed)
    return redirect('integrations:google_select_location', connection_id=connection.id)


@login_required
def google_select_location(request, connection_id):
    """
    Select Google Business location after OAuth.

    In a full implementation, this would:
    1. Fetch list of accounts from Google
    2. Fetch locations for selected account
    3. Let user select which location to connect

    For now, we'll show a form to manually enter the IDs.
    """
    connection = get_object_or_404(Connection, id=connection_id)

    # Verify access
    membership = Member.objects.filter(
        user=request.user,
        company=connection.company,
        is_active=True
    ).first()
    if not membership or not membership.can_manage():
        messages.error(request, 'Нет доступа')
        return redirect('dashboard:index')

    if request.method == 'POST':
        account_id = request.POST.get('account_id', '').strip()
        location_id = request.POST.get('location_id', '').strip()
        external_url = request.POST.get('external_url', '').strip()

        if account_id and location_id:
            connection.google_account_id = account_id
            connection.google_location_id = location_id
            connection.external_id = f'{account_id}/{location_id}'
            connection.external_url = external_url
            connection.save()

            messages.success(request, 'Локация успешно настроена!')

            # Trigger initial sync
            sync_google_reviews.delay(str(connection.id))

            return redirect('integrations:settings')
        else:
            messages.error(request, 'Укажите Account ID и Location ID')

    context = {
        'connection': connection,
        'company': connection.company,
    }
    return render(request, 'integrations/google_select_location.html', context)


@login_required
def google_disconnect(request, connection_id):
    """Disconnect Google integration."""
    connection = get_object_or_404(Connection, id=connection_id, platform_id='google')

    # Verify access
    membership = Member.objects.filter(
        user=request.user,
        company=connection.company,
        is_active=True
    ).first()
    if not membership or not membership.can_manage():
        messages.error(request, 'Нет доступа')
        return redirect('dashboard:index')

    if request.method == 'POST':
        company_name = connection.company.name
        connection.delete()
        messages.success(request, f'Google отключен от {company_name}')

    return redirect('integrations:settings')


@login_required
@require_POST
def google_sync_now(request, connection_id):
    """Manually trigger review sync."""
    connection = get_object_or_404(Connection, id=connection_id, platform_id='google')

    # Verify access
    membership = Member.objects.filter(
        user=request.user,
        company=connection.company,
        is_active=True
    ).first()
    if not membership:
        return JsonResponse({'error': 'Нет доступа'}, status=403)

    # Queue sync task
    sync_google_reviews.delay(str(connection.id))

    return JsonResponse({
        'success': True,
        'message': 'Синхронизация запущена'
    })


@login_required
@require_POST
def telegram_save(request):
    """Save Telegram notification settings."""
    company, _ = get_current_company(request)
    if not company:
        messages.error(request, 'Нет доступной компании')
        return redirect('dashboard:index')

    # Check permissions
    membership = Member.objects.get(user=request.user, company=company)
    if not membership.can_manage():
        messages.error(request, 'У вас нет прав для управления настройками')
        return redirect('integrations:settings')

    bot_token = request.POST.get('bot_token', '').strip()
    chat_id = request.POST.get('chat_id', '').strip()
    enabled = request.POST.get('enabled') == 'on'

    company.set_telegram_settings(bot_token, chat_id, enabled)
    messages.success(request, 'Настройки Telegram сохранены')

    return redirect('integrations:settings')


@login_required
@require_POST
def telegram_test(request):
    """Send test Telegram notification."""
    from apps.notifications.telegram import send_telegram_message

    company, _ = get_current_company(request)
    if not company:
        return JsonResponse({'error': 'Нет доступной компании'}, status=400)

    telegram_settings = company.get_telegram_settings()
    bot_token = telegram_settings.get('bot_token')
    chat_id = telegram_settings.get('chat_id')

    if not bot_token or not chat_id:
        return JsonResponse({'error': 'Укажите токен бота и Chat ID'}, status=400)

    message = (
        f"✅ <b>Тестовое уведомление</b>\n\n"
        f"Уведомления настроены для компании <b>{company.name}</b>.\n\n"
        f"Вы будете получать сообщения о негативных отзывах (1-3 звезды)."
    )

    success = send_telegram_message(bot_token, chat_id, message)

    if success:
        return JsonResponse({'success': True, 'message': 'Тестовое сообщение отправлено!'})
    else:
        return JsonResponse({'error': 'Ошибка отправки. Проверьте токен и Chat ID.'}, status=400)
