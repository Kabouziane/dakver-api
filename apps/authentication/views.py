from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.apple.views import AppleOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from dj_rest_auth.registration.views import SocialLoginView
from dj_rest_auth.views import LoginView
from decouple import config

from .throttles import LoginRateThrottle


class ThrottledLoginView(LoginView):
    """Login avec throttle strict : 5 tentatives/minute par IP."""
    throttle_classes = [LoginRateThrottle]


class GoogleLoginView(SocialLoginView):
    """POST /api/v1/auth/google/ — échange un code Google contre un JWT."""
    adapter_class   = GoogleOAuth2Adapter
    callback_url    = config('FRONTEND_URL', default='http://localhost:3000') + '/espace-client/callback/google'
    client_class    = OAuth2Client


class AppleLoginView(SocialLoginView):
    """POST /api/v1/auth/apple/ — échange un code Apple contre un JWT."""
    adapter_class = AppleOAuth2Adapter
    callback_url  = config('FRONTEND_URL', default='http://localhost:3000') + '/espace-client/callback/apple'
    client_class  = OAuth2Client
