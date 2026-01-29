"""Signals for handling OAuth user events."""

import logging
from allauth.account.signals import user_signed_up
from django.dispatch import receiver

from .services.oauth import handle_oauth_signup

logger = logging.getLogger(__name__)


@receiver(user_signed_up)
def oauth_user_signed_up(sender, request, user, **kwargs):
    """
    Handle OAuth user signup.

    Creates company, member, and sets welcome flag when user signs up via OAuth.

    Args:
        sender: Signal sender
        request: HTTP request
        user: Newly created user
        **kwargs: Additional signal arguments (includes 'sociallogin')
    """
    # Check if this is OAuth signup (has sociallogin in kwargs)
    if 'sociallogin' in kwargs:
        logger.info(f'OAuth signup for user {user.email}')

        try:
            handle_oauth_signup(user, request)
            logger.info(f'Successfully set up OAuth user {user.email}')
        except Exception as e:
            logger.error(f'Error setting up OAuth user {user.email}: {e}')
            raise
