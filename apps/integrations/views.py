"""Views for platform integrations (OAuth callbacks, settings)."""

import json
import logging
import secrets
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect, JsonResponse, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.accounts.models import Member, User
from apps.companies.models import Company, Connection, Platform
from apps.dashboard.services import get_current_company

from .services import (
    GoogleAuthService,
    check_integration_access,
    check_connection_access,
    process_google_oauth_callback,
)
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

    has_access, _ = check_integration_access(request.user, company)
    if not has_access:
        messages.error(request, 'У вас нет прав для управления интеграциями')
        return redirect('dashboard:index')

    return render(request, 'integrations/settings.html', {
        'company': company,
        'companies': companies,
        'connections': Connection.objects.filter(company=company).select_related('platform'),
        'google_configured': GoogleAuthService().is_configured,
        'platforms': Platform.objects.filter(is_active=True),
    })


@login_required
def google_connect(request):
    """Start Google OAuth flow."""
    company = get_user_company(request.user)
    if not company:
        messages.error(request, 'Нет доступной компании')
        return redirect('dashboard:index')

    has_access, _ = check_integration_access(request.user, company)
    if not has_access:
        messages.error(request, 'У вас нет прав для подключения интеграций')
        return redirect('dashboard:index')

    auth_service = GoogleAuthService()
    if not auth_service.is_configured:
        messages.error(request, 'Google API не настроен. Добавьте GOOGLE_CLIENT_ID и GOOGLE_CLIENT_SECRET.')
        return redirect('integrations:settings')

    try:
        auth_url = auth_service.get_authorization_url(state=str(company.id))
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

    try:
        company = Company.objects.get(id=state)
        has_access, _ = check_integration_access(request.user, company)
        if not has_access:
            raise ValueError('No permission')
    except (Company.DoesNotExist, ValueError):
        messages.error(request, 'Нет доступа к компании')
        return redirect('dashboard:index')

    try:
        connection = process_google_oauth_callback(code, company)
        messages.success(request, 'Google Business успешно подключен!')
        return redirect('integrations:google_select_location', connection_id=connection.id)
    except Exception as e:
        logger.exception('Failed to process OAuth callback')
        messages.error(request, f'Ошибка авторизации: {str(e)}')
        return redirect('integrations:settings')


@login_required
def google_select_location(request, connection_id):
    """Select Google Business location after OAuth."""
    connection = get_object_or_404(Connection, id=connection_id)

    has_access, _ = check_connection_access(request.user, connection)
    if not has_access:
        messages.error(request, 'Нет доступа')
        return redirect('dashboard:index')

    if request.method == 'POST':
        account_id = request.POST.get('account_id', '').strip()
        location_id = request.POST.get('location_id', '').strip()

        if account_id and location_id:
            connection.google_account_id = account_id
            connection.google_location_id = location_id
            connection.external_id = f'{account_id}/{location_id}'
            connection.external_url = request.POST.get('external_url', '').strip()
            connection.save()
            messages.success(request, 'Локация успешно настроена!')
            sync_google_reviews.delay(str(connection.id))
            return redirect('integrations:settings')
        messages.error(request, 'Укажите Account ID и Location ID')

    return render(request, 'integrations/google_select_location.html', {
        'connection': connection,
        'company': connection.company,
    })


@login_required
def google_disconnect(request, connection_id):
    """Disconnect Google integration."""
    connection = get_object_or_404(Connection, id=connection_id, platform_id='google')

    has_access, _ = check_connection_access(request.user, connection)
    if not has_access:
        messages.error(request, 'Нет доступа')
        return redirect('dashboard:index')

    if request.method == 'POST':
        connection.delete()
        messages.success(request, 'Google отключен')

    return redirect('integrations:settings')


@login_required
@require_POST
def google_sync_now(request, connection_id):
    """Manually trigger review sync."""
    connection = get_object_or_404(Connection, id=connection_id, platform_id='google')

    has_access, _ = check_connection_access(request.user, connection)
    if not has_access:
        return JsonResponse({'error': 'Нет доступа'}, status=403)

    sync_google_reviews.delay(str(connection.id))
    return JsonResponse({'success': True, 'message': 'Синхронизация запущена'})


@login_required
@require_POST
def telegram_save(request):
    """Save Telegram notification settings."""
    company, _ = get_current_company(request)
    if not company:
        messages.error(request, 'Нет доступной компании')
        return redirect('dashboard:index')

    has_access, _ = check_integration_access(request.user, company)
    if not has_access:
        messages.error(request, 'У вас нет прав для управления настройками')
        return redirect('integrations:settings')

    company.set_telegram_settings(
        request.POST.get('bot_token', '').strip(),
        request.POST.get('chat_id', '').strip(),
        request.POST.get('enabled') == 'on'
    )
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


@login_required
def telegram_connect(request):
    """Generate Telegram connection link and redirect user to Telegram bot."""
    user = request.user

    # Generate a unique token for this user
    token = secrets.token_urlsafe(32)
    user.telegram_link_token = token
    user.save(update_fields=['telegram_link_token'])

    # Create deep link to Telegram bot
    bot_username = getattr(settings, 'TELEGRAM_BOT_USERNAME', 'TopNaKarte_notifications_bot')
    telegram_url = f"https://t.me/{bot_username}?start={token}"

    return HttpResponseRedirect(telegram_url)


@login_required
@require_POST
def telegram_disconnect(request):
    """Disconnect Telegram from user account."""
    user = request.user
    user.telegram_id = None
    user.telegram_link_token = None
    user.save(update_fields=['telegram_id', 'telegram_link_token'])

    messages.success(request, 'Telegram отключён')
    return redirect('integrations:settings')


@csrf_exempt
@require_POST
def telegram_webhook(request):
    """
    Webhook endpoint for Telegram bot.
    Receives updates when user starts the bot with a token.
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponse('Bad request', status=400)

    # Check if this is a message
    message = data.get('message')
    if not message:
        return HttpResponse('OK')

    # Get chat/user info
    chat = message.get('chat', {})
    telegram_id = chat.get('id')
    text = message.get('text', '')

    if not telegram_id:
        return HttpResponse('OK')

    # Handle /start command with token
    if text.startswith('/start '):
        token = text[7:].strip()  # Remove '/start ' prefix

        if token:
            # Find user with this token
            try:
                user = User.objects.get(telegram_link_token=token)
                user.telegram_id = telegram_id
                user.telegram_link_token = None  # Clear token after use
                user.save(update_fields=['telegram_id', 'telegram_link_token'])

                # Send confirmation message
                _send_telegram_confirmation(telegram_id, user.email)

                logger.info(f"Telegram connected for user {user.email}")
            except User.DoesNotExist:
                logger.warning(f"Invalid telegram link token: {token}")

    return HttpResponse('OK')


def _send_telegram_confirmation(chat_id: int, email: str) -> None:
    """Send confirmation message to user via Telegram."""
    from apps.notifications.telegram import send_telegram_message

    bot_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
    if not bot_token:
        return

    message = "✅ Готово! Уведомления подключены."

    send_telegram_message(bot_token, str(chat_id), message)


@login_required
@require_POST
def telegram_notify_settings(request):
    """Update Telegram notification preferences (all reviews vs only negative)."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    notify_all = data.get('notify_all', False)

    user = request.user
    user.telegram_notify_all = bool(notify_all)
    user.save(update_fields=['telegram_notify_all'])

    return JsonResponse({'success': True, 'notify_all': user.telegram_notify_all})
