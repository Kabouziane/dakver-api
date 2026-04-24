"""
Fixtures pytest partagées entre tous les tests.
Principe : les fixtures sont composables — un test demande exactement
ce dont il a besoin, pas plus.
"""
import pytest
from rest_framework.test import APIClient

from .factories import (
    UserFactory, ClientFactory, DevisFactory, DevisLigneFactory,
    FactureFactory, FactureLigneFactory, MaintenanceFactory,
    PrestationFactory, CompteTransactionFactory,
)


# ─── Utilisateurs & clients ──────────────────────────────────────────────────

@pytest.fixture
def user(db):
    return UserFactory()


@pytest.fixture
def user2(db):
    return UserFactory()


@pytest.fixture
def client_profile(db, user):
    """Profil Client lié à user (créé par le signal, on fait get_or_create)."""
    return user.client


@pytest.fixture
def client_profile2(db, user2):
    return user2.client


@pytest.fixture
def admin_user(db):
    return UserFactory(is_staff=True, is_superuser=True)


# ─── APIClient authentifiés ──────────────────────────────────────────────────

@pytest.fixture
def api_client():
    """APIClient non authentifié — pour tester les 401."""
    return APIClient()


@pytest.fixture
def auth_client(db, user):
    """APIClient authentifié en tant que user (client 1)."""
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def auth_client2(db, user2):
    """APIClient authentifié en tant que user2 (client 2) — pour les tests d'isolation."""
    c = APIClient()
    c.force_authenticate(user=user2)
    return c


@pytest.fixture
def admin_client(db, admin_user):
    c = APIClient()
    c.force_authenticate(user=admin_user)
    return c


# ─── Données ─────────────────────────────────────────────────────────────────

@pytest.fixture
def devis(db, client_profile):
    return DevisFactory(client=client_profile, with_lines=2)


@pytest.fixture
def devis_other(db, client_profile2):
    """Devis appartenant au client 2 — ne doit jamais être visible par client 1."""
    return DevisFactory(client=client_profile2, with_lines=1)


@pytest.fixture
def facture(db, client_profile):
    return FactureFactory(client=client_profile, with_lines=2)


@pytest.fixture
def facture_other(db, client_profile2):
    return FactureFactory(client=client_profile2, with_lines=1)


@pytest.fixture
def maintenance(db, client_profile):
    return MaintenanceFactory(client=client_profile)


@pytest.fixture
def prestation(db, client_profile):
    return PrestationFactory(client=client_profile)


@pytest.fixture
def transaction(db, client_profile):
    return CompteTransactionFactory(client=client_profile)
