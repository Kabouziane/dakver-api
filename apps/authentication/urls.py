from django.urls import path
from .views import GoogleLoginView, AppleLoginView

urlpatterns = [
    path('auth/google/', GoogleLoginView.as_view(), name='google_login'),
    path('auth/apple/',  AppleLoginView.as_view(),  name='apple_login'),
]
