from django.urls import path
from .views import QRRedirectView

app_name = 'qr'

urlpatterns = [
    # QR-редирект: /{CODE} -> форма отзыва
    path('<str:code>', QRRedirectView.as_view(), name='redirect'),
]
