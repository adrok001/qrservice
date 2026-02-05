"""OAuth business logic for user authentication and account linking."""

from typing import Optional
from django.contrib.auth import get_user_model
from django.http import HttpRequest

from apps.companies.models import Company
from apps.accounts.models import Member
from apps.accounts.services.signup import connect_to_demo_company

User = get_user_model()


def handle_oauth_signup(user: User, request: HttpRequest) -> None:
    """
    Handle new OAuth user signup.

    Creates company, member, sets welcome flag, and marks email as verified.

    Args:
        user: Newly created user from OAuth
        request: HTTP request object
    """
    # Create company for new user
    company_name = f'Компания {user.first_name or user.email.split("@")[0]}'
    company = Company.objects.create(
        name=company_name,
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


def can_auto_link_oauth(user: User) -> bool:
    """
    Check if OAuth account can be automatically linked to existing user.

    Auto-link is safe when user has no password (OAuth-only account).

    Args:
        user: Existing user to check

    Returns:
        True if safe to auto-link, False if need password confirmation
    """
    return not user.has_usable_password()


def link_oauth_to_user(user: User, sociallogin) -> None:
    """
    Link OAuth account to existing user.

    Args:
        user: Existing user
        sociallogin: SocialLogin object from allauth
    """
    # Connect social account to user
    sociallogin.connect(None, user)

    # Mark email as verified if not already
    if not user.email_verified:
        user.email_verified = True
        user.save(update_fields=['email_verified'])


def get_user_by_email(email: str) -> Optional[User]:
    """
    Get user by email address.

    Args:
        email: Email address

    Returns:
        User if exists, None otherwise
    """
    try:
        return User.objects.get(email=email)
    except User.DoesNotExist:
        return None
