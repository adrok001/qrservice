"""Views for accounts app."""

import time
import logging
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages

from .models import User, Member
from apps.companies.models import Company

logger = logging.getLogger(__name__)

# Bot protection settings
HONEYPOT_FIELD = 'website'  # Bots often fill this
MIN_FORM_TIME = 3  # Minimum seconds to fill form (humans need at least 3s)
MAX_FORM_TIME = 3600  # Maximum seconds (1 hour, prevents replay)


def _check_bot_protection(request):
    """
    Check honeypot and time-based bot protection.
    Returns error message if bot detected, None otherwise.
    """
    # Honeypot check - field should be empty
    honeypot = request.POST.get(HONEYPOT_FIELD, '')
    if honeypot:
        logger.warning(f"Bot detected (honeypot): IP={_get_ip(request)}")
        return 'bot_detected'

    # Time-based check
    form_timestamp = request.POST.get('_ts', '')
    if form_timestamp:
        try:
            submitted_time = int(form_timestamp)
            elapsed = time.time() - submitted_time

            if elapsed < MIN_FORM_TIME:
                logger.warning(f"Bot detected (too fast: {elapsed:.1f}s): IP={_get_ip(request)}")
                return 'bot_detected'

            if elapsed > MAX_FORM_TIME:
                logger.warning(f"Form expired ({elapsed:.0f}s): IP={_get_ip(request)}")
                return 'form_expired'
        except (ValueError, TypeError):
            pass

    return None


def _get_ip(request):
    """Get client IP address."""
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        return x_forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', 'unknown')


def login_view(request):
    """Handle user login."""
    if request.user.is_authenticated:
        return redirect('dashboard:index')

    if request.method == 'POST':
        # Bot protection
        bot_check = _check_bot_protection(request)
        if bot_check == 'bot_detected':
            messages.error(request, 'Ошибка отправки формы. Попробуйте ещё раз.')
            return render(request, 'accounts/login.html', {'form_timestamp': int(time.time())})

        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')

        if not email or not password:
            messages.error(request, 'Введите email и пароль')
        else:
            user = authenticate(request, username=email, password=password)
            if user is not None:
                login(request, user)
                next_url = request.GET.get('next', '/dashboard/')
                return redirect(next_url)
            else:
                messages.error(request, 'Неверный email или пароль')

    return render(request, 'accounts/login.html', {'form_timestamp': int(time.time())})


def register_view(request):
    """Handle user registration."""
    if request.user.is_authenticated:
        return redirect('dashboard:index')

    if request.method == 'POST':
        # Bot protection
        bot_check = _check_bot_protection(request)
        if bot_check == 'bot_detected':
            messages.error(request, 'Ошибка отправки формы. Попробуйте ещё раз.')
            return render(request, 'accounts/register.html', {'form_timestamp': int(time.time())})
        if bot_check == 'form_expired':
            messages.error(request, 'Форма устарела. Пожалуйста, заполните заново.')
            return render(request, 'accounts/register.html', {'form_timestamp': int(time.time())})

        name = request.POST.get('name', '').strip()
        email = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')
        password_confirm = request.POST.get('password_confirm', '')

        # Валидация
        errors = []

        if not name:
            errors.append('Введите имя')

        if not email:
            errors.append('Введите email')
        elif User.objects.filter(email=email).exists():
            errors.append('Пользователь с таким email уже существует')

        if not password:
            errors.append('Введите пароль')
        elif len(password) < 8:
            errors.append('Пароль должен содержать минимум 8 символов')
        elif password != password_confirm:
            errors.append('Пароли не совпадают')

        if errors:
            for error in errors:
                messages.error(request, error)
        else:
            # Создаём пользователя
            user = User.objects.create_user(email=email, password=password)
            user.first_name = name
            user.save()

            # Создаём компанию автоматически
            company = Company.objects.create(
                name=f'Компания {name}',
                address='',
            )
            Member.objects.create(
                user=user,
                company=company,
                role=Member.Role.OWNER,
            )

            login(request, user)

            # Флаг для показа приветствия
            request.session['show_welcome'] = True
            request.session['selected_company_id'] = str(company.id)

            return redirect('dashboard:company_settings')

    return render(request, 'accounts/register.html', {'form_timestamp': int(time.time())})


def logout_view(request):
    """Handle user logout."""
    logout(request)
    return redirect('accounts:login')
