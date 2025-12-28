from django.urls import path
from . import views

app_name = 'feedback'

urlpatterns = [
    # Статические страницы (до slug паттернов!)
    path('thank-you/', views.thank_you, name='thank_you'),

    # API для отправки отзыва
    path('api/submit/', views.submit_review, name='submit'),

    # Форма отзыва (slug паттерны в конце)
    path('<slug:company_slug>/', views.feedback_form, name='form'),
    path('<slug:company_slug>/step2/', views.feedback_step2, name='step2'),
]
