"""Google OAuth2 authentication service for Business Profile API."""

import logging
from datetime import timedelta
from typing import Optional
from urllib.parse import urlencode

from django.conf import settings
from django.utils import timezone

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from apps.companies.models import Connection

logger = logging.getLogger(__name__)


class GoogleAuthService:
    """
    Handles OAuth2 authentication with Google Business Profile API.

    Usage:
        # Start OAuth flow
        auth_service = GoogleAuthService()
        auth_url = auth_service.get_authorization_url(state='company_123')

        # Handle callback
        tokens = auth_service.exchange_code_for_tokens(code, state)

        # Refresh token when needed
        new_token = auth_service.refresh_access_token(connection)
    """

    SCOPES = settings.GOOGLE_SCOPES

    def __init__(self):
        self.client_id = settings.GOOGLE_CLIENT_ID
        self.client_secret = settings.GOOGLE_CLIENT_SECRET
        self.redirect_uri = settings.GOOGLE_REDIRECT_URI

    @property
    def is_configured(self) -> bool:
        """Check if Google OAuth is properly configured."""
        return bool(
            self.client_id
            and self.client_secret
            and self.client_id != 'your_client_id_here'
        )

    def get_authorization_url(self, state: str = '') -> str:
        """
        Generate OAuth2 authorization URL for Google consent screen.

        Args:
            state: State parameter to pass through OAuth flow (e.g., company_id)

        Returns:
            Authorization URL to redirect user to
        """
        if not self.is_configured:
            raise ValueError(
                'Google OAuth not configured. '
                'Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env'
            )

        flow = self._create_flow()
        authorization_url, _ = flow.authorization_url(
            access_type='offline',  # Get refresh token
            include_granted_scopes='true',
            state=state,
            prompt='consent',  # Force consent screen for refresh token
        )
        return authorization_url

    def exchange_code_for_tokens(
        self,
        code: str,
        state: str = ''
    ) -> dict:
        """
        Exchange authorization code for access and refresh tokens.

        Args:
            code: Authorization code from OAuth callback
            state: State parameter from callback

        Returns:
            Dict with access_token, refresh_token, expires_at
        """
        if not self.is_configured:
            raise ValueError('Google OAuth not configured')

        flow = self._create_flow()
        flow.fetch_token(code=code)

        credentials = flow.credentials
        expires_at = timezone.now() + timedelta(seconds=credentials.expiry.timestamp() - timezone.now().timestamp())

        return {
            'access_token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'expires_at': expires_at,
            'token_uri': credentials.token_uri,
        }

    def refresh_access_token(self, connection: Connection) -> Optional[str]:
        """
        Refresh access token using refresh token.

        Args:
            connection: Connection object with refresh_token

        Returns:
            New access token or None if refresh failed
        """
        if not connection.refresh_token:
            logger.warning(f'No refresh token for connection {connection.id}')
            return None

        try:
            credentials = Credentials(
                token=connection.access_token,
                refresh_token=connection.refresh_token,
                token_uri='https://oauth2.googleapis.com/token',
                client_id=self.client_id,
                client_secret=self.client_secret,
            )

            # Force refresh
            from google.auth.transport.requests import Request
            credentials.refresh(Request())

            # Update connection
            connection.access_token = credentials.token
            connection.token_expires_at = timezone.now() + timedelta(seconds=3600)
            connection.save(update_fields=['access_token', 'token_expires_at', 'updated_at'])

            logger.info(f'Refreshed token for connection {connection.id}')
            return credentials.token

        except Exception as e:
            logger.error(f'Failed to refresh token for connection {connection.id}: {e}')
            connection.last_sync_status = Connection.SyncStatus.ERROR
            connection.last_sync_error = f'Token refresh failed: {str(e)}'
            connection.save(update_fields=['last_sync_status', 'last_sync_error', 'updated_at'])
            return None

    def get_credentials(self, connection: Connection) -> Optional[Credentials]:
        """
        Get valid credentials for API calls.

        Automatically refreshes token if expired.

        Args:
            connection: Connection object with tokens

        Returns:
            Google Credentials object or None
        """
        if not connection.access_token:
            return None

        # Refresh if expired or about to expire
        if not connection.is_token_valid:
            new_token = self.refresh_access_token(connection)
            if not new_token:
                return None

        return Credentials(
            token=connection.access_token,
            refresh_token=connection.refresh_token,
            token_uri='https://oauth2.googleapis.com/token',
            client_id=self.client_id,
            client_secret=self.client_secret,
        )

    def _create_flow(self) -> Flow:
        """Create OAuth2 flow object."""
        client_config = {
            'web': {
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
                'token_uri': 'https://oauth2.googleapis.com/token',
                'redirect_uris': [self.redirect_uri],
            }
        }
        return Flow.from_client_config(
            client_config,
            scopes=self.SCOPES,
            redirect_uri=self.redirect_uri,
        )
