from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('generate/', views.generate_qr, name='generate_qr'),
    path('quick/', views.generate_inline, name='generate_inline'),
    path('qr/<int:pk>/', views.qrcode_detail, name='qrcode_detail'),
    path('download/', views.download_qr, name='download_qr'),
]
