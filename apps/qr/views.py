import uuid
from django.shortcuts import redirect, get_object_or_404
from django.http import Http404
from django.views import View

from .models import QR, QRScan


class QRRedirectView(View):
    """Редирект по QR-коду на форму отзыва"""

    def get(self, request, code):
        # Находим QR-код
        qr = get_object_or_404(QR, code=code.upper())

        # Проверяем активность
        if not qr.is_active:
            raise Http404("QR-код неактивен")

        if not qr.company.is_active:
            raise Http404("Компания неактивна")

        # Логируем сканирование
        session_id = request.session.session_key or str(uuid.uuid4())[:8]
        QRScan.objects.create(
            qr=qr,
            ip_address=self.get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
            session_id=session_id
        )

        # Увеличиваем счётчик
        qr.increment_scans()

        # Редирект на форму отзыва
        return redirect(qr.get_redirect_url())

    def get_client_ip(self, request):
        """Получить IP клиента"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')
