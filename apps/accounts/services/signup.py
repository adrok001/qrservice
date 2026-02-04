"""User signup business logic."""

from typing import Tuple
from django.contrib.auth import get_user_model
from django.http import HttpRequest

from apps.companies.models import Company
from apps.accounts.models import Member

User = get_user_model()


def create_user_with_company(
    name: str,
    email: str,
    password: str,
    request: HttpRequest
) -> Tuple[User, Company]:
    """
    Create new user with associated company and member.

    This is the main signup flow for regular (non-OAuth) users.
    Creates:
    1. User account
    2. Company with default name
    3. Member with OWNER role
    4. Sets session flags for welcome banner

    Args:
        name: User's first name
        email: User's email address
        password: User's password
        request: HTTP request for session management

    Returns:
        Tuple of (User, Company)
    """
    # Create user account
    user = User.objects.create_user(email=email, password=password)
    user.first_name = name
    user.save()

    # Create company for the user
    company = Company.objects.create(
        name=f'Компания {name}',
        address='',
    )

    # Create member with OWNER role
    Member.objects.create(
        user=user,
        company=company,
        role=Member.Role.OWNER,
    )

    # Connect to demo company (if exists)
    connect_to_demo_company(user)

    # Set session flags for welcome banner
    request.session['show_welcome'] = True
    request.session['selected_company_id'] = str(company.id)

    return user, company


def connect_to_demo_company(user: User) -> None:
    """
    Connect user to demo company as viewer.

    Automatically adds new users to demo company so they can see
    real example reviews immediately after registration.
    """
    try:
        demo_company = Company.objects.filter(is_demo=True, is_active=True).first()
        if demo_company:
            # Check if already connected
            if not Member.objects.filter(user=user, company=demo_company).exists():
                Member.objects.create(
                    user=user,
                    company=demo_company,
                    role=Member.Role.VIEWER,
                )
    except Exception:
        # Don't fail registration if demo connection fails
        pass


def validate_signup_data(name: str, email: str, password: str, password_confirm: str) -> list[str]:
    """
    Validate signup form data.

    Args:
        name: User's name
        email: Email address
        password: Password
        password_confirm: Password confirmation

    Returns:
        List of validation errors (empty if valid)
    """
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

    return errors
