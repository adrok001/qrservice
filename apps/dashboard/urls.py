from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.dashboard_index, name='index'),
    path('reviews/', views.reviews_list, name='reviews'),
    path('qr/', views.qr_list, name='qr'),
]
