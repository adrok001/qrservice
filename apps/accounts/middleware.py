"""
Rate limiting middleware for bot protection.
Simple in-memory implementation without external dependencies.
"""
import time
from collections import defaultdict
from threading import Lock
from django.http import HttpResponseForbidden


class RateLimitMiddleware:
    """
    Rate limiting by IP address.

    Settings (in settings.py):
        RATE_LIMIT_REQUESTS = 5  # max requests
        RATE_LIMIT_WINDOW = 60   # per N seconds
        RATE_LIMIT_PATHS = ['/accounts/register/', '/accounts/login/']
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.requests = defaultdict(list)
        self.lock = Lock()

    def __call__(self, request):
        from django.conf import settings

        # Get settings with defaults
        max_requests = getattr(settings, 'RATE_LIMIT_REQUESTS', 5)
        window = getattr(settings, 'RATE_LIMIT_WINDOW', 60)
        protected_paths = getattr(settings, 'RATE_LIMIT_PATHS', [
            '/accounts/register/',
            '/accounts/login/',
        ])

        # Only check POST requests to protected paths
        if request.method == 'POST' and request.path in protected_paths:
            ip = self._get_client_ip(request)

            if self._is_rate_limited(ip, max_requests, window):
                return HttpResponseForbidden(
                    '<h1>Слишком много запросов</h1>'
                    '<p>Пожалуйста, подождите минуту и попробуйте снова.</p>'
                )

        return self.get_response(request)

    def _get_client_ip(self, request):
        """Extract client IP from request."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '0.0.0.0')

    def _is_rate_limited(self, ip, max_requests, window):
        """Check if IP exceeded rate limit."""
        now = time.time()

        with self.lock:
            # Clean old requests
            self.requests[ip] = [
                req_time for req_time in self.requests[ip]
                if now - req_time < window
            ]

            # Check limit
            if len(self.requests[ip]) >= max_requests:
                return True

            # Record this request
            self.requests[ip].append(now)
            return False
