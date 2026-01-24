"""Views for accounts app."""

from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages

from .models import User


def login_view(request):
    """Handle user login."""
    if request.user.is_authenticated:
        return redirect('dashboard:index')

    if request.method == 'POST':
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

    return render(request, 'accounts/login.html')


def register_view(request):
    """Handle user registration."""
    if request.user.is_authenticated:
        return redirect('dashboard:index')

    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')
        password_confirm = request.POST.get('password_confirm', '')

        # Валидация
        errors = []

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
            login(request, user)
            messages.success(request, 'Регистрация успешна!')
            return redirect('dashboard:index')

    return render(request, 'accounts/register.html')


def logout_view(request):
    """Handle user logout."""
    logout(request)
    return redirect('accounts:login')
