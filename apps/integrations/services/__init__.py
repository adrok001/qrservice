"""Services for external platform integrations."""
from typing import Optional, Tuple

from apps.accounts.models import Member
from apps.companies.models import Company, Connection, Platform

from .google_auth import GoogleAuthService
from .google_reviews import GoogleReviewsService


def check_integration_access(user, company: Company) -> Tuple[bool, Optional[Member]]:
    """Check if user has permission to manage integrations."""
    try:
        membership = Member.objects.get(user=user, company=company, is_active=True)
        return membership.can_manage(), membership
    except Member.DoesNotExist:
        return False, None


def check_connection_access(user, connection: Connection) -> Tuple[bool, Optional[Member]]:
    """Check if user has access to manage a specific connection."""
    membership = Member.objects.filter(
        user=user,
        company=connection.company,
        is_active=True
    ).first()
    if not membership:
        return False, None
    return membership.can_manage(), membership


def process_google_oauth_callback(code: str, company: Company) -> Connection:
    """Process Google OAuth callback and create/update connection."""
    auth_service = GoogleAuthService()
    tokens = auth_service.exchange_code_for_tokens(code, str(company.id))

    platform, _ = Platform.objects.get_or_create(
        id='google',
        defaults={'name': 'Google Business', 'is_active': True}
    )

    connection, _ = Connection.objects.update_or_create(
        company=company,
        platform=platform,
        defaults={
            'access_token': tokens['access_token'],
            'refresh_token': tokens.get('refresh_token', ''),
            'token_expires_at': tokens['expires_at'],
            'external_id': 'pending',
            'sync_enabled': True,
        }
    )
    return connection


__all__ = [
    'GoogleAuthService',
    'GoogleReviewsService',
    'check_integration_access',
    'check_connection_access',
    'process_google_oauth_callback',
]
