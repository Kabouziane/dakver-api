"""
Tests d'authentification — JWT, registration, token lifecycle.
Vérifie : login, logout, refresh, registration avec création automatique du profil,
blacklist des tokens après logout.
"""
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.clients.models import Client
from .factories import UserFactory

User = get_user_model()


# ─── Registration ─────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestRegistration:
    REGISTER_URL = '/api/v1/auth/register/'

    def test_registration_returns_201(self, api_client):
        resp = api_client.post(self.REGISTER_URL, {
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password1': 'StrongPass123!',
            'password2': 'StrongPass123!',
        }, format='json')
        assert resp.status_code == 201

    def test_registration_creates_user(self, api_client):
        api_client.post(self.REGISTER_URL, {
            'username': 'johndoe',
            'email': 'johndoe@example.com',
            'password1': 'StrongPass123!',
            'password2': 'StrongPass123!',
        }, format='json')
        assert User.objects.filter(email='johndoe@example.com').exists()

    def test_registration_creates_client_profile_automatically(self, api_client):
        """Le signal post_save doit créer un Client dès la création du User."""
        api_client.post(self.REGISTER_URL, {
            'username': 'signaltest',
            'email': 'signal@example.com',
            'password1': 'StrongPass123!',
            'password2': 'StrongPass123!',
        }, format='json')
        user = User.objects.get(email='signal@example.com')
        assert hasattr(user, 'client')
        assert isinstance(user.client, Client)

    def test_registration_password_mismatch_returns_400(self, api_client):
        resp = api_client.post(self.REGISTER_URL, {
            'username': 'badpass',
            'email': 'badpass@example.com',
            'password1': 'StrongPass123!',
            'password2': 'DifferentPass456!',
        }, format='json')
        assert resp.status_code == 400

    def test_registration_duplicate_email_returns_400(self, api_client, user):
        resp = api_client.post(self.REGISTER_URL, {
            'username': 'duplicate',
            'email': user.email,  # email déjà existant
            'password1': 'StrongPass123!',
            'password2': 'StrongPass123!',
        }, format='json')
        assert resp.status_code == 400

    def test_registration_returns_access_token(self, api_client):
        resp = api_client.post(self.REGISTER_URL, {
            'username': 'tokentest',
            'email': 'tokentest@example.com',
            'password1': 'StrongPass123!',
            'password2': 'StrongPass123!',
        }, format='json')
        assert resp.status_code == 201
        assert 'access' in resp.data


# ─── Login ────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestLogin:
    LOGIN_URL = '/api/v1/auth/login/'

    def test_login_with_valid_credentials_returns_200(self, api_client, user):
        resp = api_client.post(self.LOGIN_URL, {
            'username': user.username,
            'password': 'password123!',
        }, format='json')
        assert resp.status_code == 200

    def test_login_returns_access_token(self, api_client, user):
        resp = api_client.post(self.LOGIN_URL, {
            'username': user.username,
            'password': 'password123!',
        }, format='json')
        assert 'access' in resp.data

    def test_login_with_email_works(self, api_client, user):
        resp = api_client.post(self.LOGIN_URL, {
            'email': user.email,
            'password': 'password123!',
        }, format='json')
        assert resp.status_code == 200

    def test_login_wrong_password_returns_400(self, api_client, user):
        resp = api_client.post(self.LOGIN_URL, {
            'username': user.username,
            'password': 'wrongpassword',
        }, format='json')
        assert resp.status_code == 400

    def test_login_nonexistent_user_returns_400(self, api_client):
        resp = api_client.post(self.LOGIN_URL, {
            'username': 'nobody',
            'password': 'password123!',
        }, format='json')
        assert resp.status_code == 400

    def test_login_inactive_user_returns_400(self, api_client):
        inactive = UserFactory(is_active=False)
        resp = api_client.post(self.LOGIN_URL, {
            'username': inactive.username,
            'password': 'password123!',
        }, format='json')
        assert resp.status_code == 400


# ─── Logout ───────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestLogout:
    LOGOUT_URL = '/api/v1/auth/logout/'
    LOGIN_URL  = '/api/v1/auth/login/'

    def test_logout_authenticated_returns_200(self, auth_client, user):
        # D'abord on récupère un vrai refresh token via login
        plain = APIClient()
        login_resp = plain.post(self.LOGIN_URL, {
            'username': user.username,
            'password': 'password123!',
        }, format='json')
        refresh = login_resp.data.get('refresh', '')
        resp = auth_client.post(self.LOGOUT_URL, {'refresh': refresh}, format='json')
        assert resp.status_code == 200

    def test_logout_unauthenticated_returns_401(self, api_client):
        resp = api_client.post(self.LOGOUT_URL, {}, format='json')
        assert resp.status_code == 401


# ─── Token refresh ────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestTokenRefresh:
    REFRESH_URL = '/api/v1/auth/token/refresh/'
    LOGIN_URL   = '/api/v1/auth/login/'

    def test_refresh_with_valid_token_returns_new_access(self, api_client, user):
        login_resp = api_client.post(self.LOGIN_URL, {
            'username': user.username,
            'password': 'password123!',
        }, format='json')
        refresh = login_resp.data['refresh']
        resp = api_client.post(self.REFRESH_URL, {'refresh': refresh}, format='json')
        assert resp.status_code == 200
        assert 'access' in resp.data

    def test_refresh_with_invalid_token_returns_401(self, api_client):
        resp = api_client.post(self.REFRESH_URL, {'refresh': 'not.a.valid.token'}, format='json')
        assert resp.status_code == 401

    def test_new_access_token_allows_authenticated_request(self, api_client, user):
        """Un token rafraîchi doit permettre d'accéder aux endpoints protégés."""
        login_resp = api_client.post(self.LOGIN_URL, {
            'username': user.username,
            'password': 'password123!',
        }, format='json')
        refresh = login_resp.data['refresh']
        refresh_resp = api_client.post(self.REFRESH_URL, {'refresh': refresh}, format='json')
        new_access = refresh_resp.data['access']

        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {new_access}')
        resp = api_client.get('/api/v1/profile/')
        assert resp.status_code == 200


# ─── Password change ──────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestPasswordChange:
    CHANGE_URL = '/api/v1/auth/password/change/'

    def test_password_change_returns_200(self, auth_client):
        resp = auth_client.post(self.CHANGE_URL, {
            'old_password': 'password123!',
            'new_password1': 'NewStrongPass456!',
            'new_password2': 'NewStrongPass456!',
        }, format='json')
        assert resp.status_code == 200

    def test_password_change_wrong_old_password_returns_400(self, auth_client):
        resp = auth_client.post(self.CHANGE_URL, {
            'old_password': 'wrongpassword',
            'new_password1': 'NewStrongPass456!',
            'new_password2': 'NewStrongPass456!',
        }, format='json')
        assert resp.status_code == 400

    def test_password_change_unauthenticated_returns_401(self, api_client):
        resp = api_client.post(self.CHANGE_URL, {
            'old_password': 'password123!',
            'new_password1': 'NewPass456!',
            'new_password2': 'NewPass456!',
        }, format='json')
        assert resp.status_code == 401

    def test_new_password_too_common_returns_400(self, auth_client):
        resp = auth_client.post(self.CHANGE_URL, {
            'old_password': 'password123!',
            'new_password1': 'password',
            'new_password2': 'password',
        }, format='json')
        assert resp.status_code == 400
