"""
Tests d'intégration des endpoints API.
Vérifie le comportement HTTP : status codes, structure des réponses,
logique métier côté API.
"""
from decimal import Decimal
from datetime import date, timedelta

import pytest

from apps.clients.models import Facture, CompteTransaction
from .factories import (
    FactureFactory, FactureLigneFactory, MaintenanceFactory,
    PrestationFactory, CompteTransactionFactory, DevisFactory,
)


# ─── Authentification requise ─────────────────────────────────────────────────

@pytest.mark.django_db
class TestAuthRequired:
    PROTECTED_ENDPOINTS = [
        '/api/v1/profile/',
        '/api/v1/devis/',
        '/api/v1/factures/',
        '/api/v1/factures/summary/',
        '/api/v1/maintenance/',
        '/api/v1/prestations/',
        '/api/v1/compte/',
        '/api/v1/dashboard/',
    ]

    @pytest.mark.parametrize('endpoint', PROTECTED_ENDPOINTS)
    def test_unauthenticated_returns_401(self, api_client, endpoint):
        resp = api_client.get(endpoint)
        assert resp.status_code == 401, f"{endpoint} should return 401 for unauthenticated requests"


# ─── Profile ──────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestProfileEndpoint:
    def test_get_profile_returns_200(self, auth_client):
        resp = auth_client.get('/api/v1/profile/')
        assert resp.status_code == 200

    def test_profile_contains_expected_fields(self, auth_client, user):
        resp = auth_client.get('/api/v1/profile/')
        data = resp.data
        assert data['email'] == user.email
        assert 'first_name' in data
        assert 'last_name' in data
        assert 'balance' in data
        assert 'unpaid_amount' in data

    def test_patch_profile_updates_phone(self, auth_client):
        resp = auth_client.patch('/api/v1/profile/', {'phone': '+32 2 999 88 77'}, format='json')
        assert resp.status_code == 200
        assert resp.data['phone'] == '+32 2 999 88 77'

    def test_patch_profile_cannot_change_email(self, auth_client, user):
        original_email = user.email
        auth_client.patch('/api/v1/profile/', {'email': 'hacker@evil.com'}, format='json')
        user.refresh_from_db()
        assert user.email == original_email


# ─── Devis ────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestDevisEndpoint:
    def test_list_devis_returns_200(self, auth_client, devis):
        resp = auth_client.get('/api/v1/devis/')
        assert resp.status_code == 200

    def test_list_devis_returns_pagination(self, auth_client, devis):
        resp = auth_client.get('/api/v1/devis/')
        assert 'results' in resp.data
        assert 'count' in resp.data

    def test_retrieve_devis_returns_detail(self, auth_client, devis):
        resp = auth_client.get(f'/api/v1/devis/{devis.id}/')
        assert resp.status_code == 200
        assert resp.data['reference'] == devis.reference
        assert 'lignes' in resp.data
        assert 'amount_excl' in resp.data
        assert 'amount_incl' in resp.data

    def test_devis_contains_pdf_url_if_file_exists(self, auth_client, devis):
        resp = auth_client.get(f'/api/v1/devis/{devis.id}/')
        # pdf_url peut être null si pas encore généré — c'est ok
        assert 'pdf_url' in resp.data

    def test_devis_status_label_is_human_readable(self, auth_client, devis):
        resp = auth_client.get(f'/api/v1/devis/{devis.id}/')
        assert resp.data['status_label'] in ['Brouillon', 'Envoyé', 'Accepté', 'Refusé', 'Expiré']

    def test_client_cannot_create_devis_via_api(self, auth_client, client_profile):
        """Les clients ne peuvent pas créer de devis — c'est réservé à l'admin."""
        resp = auth_client.post('/api/v1/devis/', {
            'title': 'Test', 'status': 'draft', 'valid_until': '2025-12-31'
        }, format='json')
        assert resp.status_code == 405  # Method Not Allowed


# ─── Factures ─────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestFactureEndpoint:
    def test_list_factures_returns_200(self, auth_client, facture):
        resp = auth_client.get('/api/v1/factures/')
        assert resp.status_code == 200

    def test_retrieve_facture_returns_detail(self, auth_client, facture):
        resp = auth_client.get(f'/api/v1/factures/{facture.id}/')
        assert resp.status_code == 200
        assert resp.data['reference'] == facture.reference
        assert 'lignes' in resp.data
        assert 'is_overdue' in resp.data

    def test_summary_structure(self, auth_client, client_profile):
        f = FactureFactory(client=client_profile, status='paid', with_lines=0)
        FactureLigneFactory(facture=f, quantity=1, unit_price_excl=Decimal('1000'), vat_rate=Decimal('21'))
        resp = auth_client.get('/api/v1/factures/summary/')
        assert resp.status_code == 200
        assert 'total_paid' in resp.data
        assert 'total_pending' in resp.data
        assert 'total_overdue' in resp.data
        assert 'balance' in resp.data

    def test_summary_paid_amount_correct(self, auth_client, client_profile):
        f = FactureFactory(client=client_profile, status='paid', with_lines=0)
        FactureLigneFactory(facture=f, quantity=1, unit_price_excl=Decimal('1000'), vat_rate=Decimal('21'))
        resp = auth_client.get('/api/v1/factures/summary/')
        assert float(resp.data['total_paid']) == pytest.approx(1210.0)


# ─── Maintenance ──────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestMaintenanceEndpoint:
    def test_list_maintenance_returns_200(self, auth_client, maintenance):
        resp = auth_client.get('/api/v1/maintenance/')
        assert resp.status_code == 200

    def test_retrieve_maintenance_returns_detail(self, auth_client, maintenance):
        resp = auth_client.get(f'/api/v1/maintenance/{maintenance.id}/')
        assert resp.status_code == 200
        assert 'title' in resp.data
        assert 'scheduled_at' in resp.data
        assert 'status_label' in resp.data
        assert 'technician' in resp.data

    def test_maintenance_ordered_by_scheduled_date(self, auth_client, client_profile):
        from .factories import MaintenanceFactory
        from django.utils import timezone
        from datetime import timedelta
        m1 = MaintenanceFactory(client=client_profile,
                                 scheduled_at=timezone.now() + timedelta(days=10))
        m2 = MaintenanceFactory(client=client_profile,
                                 scheduled_at=timezone.now() + timedelta(days=5))
        resp = auth_client.get('/api/v1/maintenance/')
        ids = [m['id'] for m in resp.data['results']]
        assert ids.index(m2.id) < ids.index(m1.id)


# ─── Prestations ──────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestPrestationEndpoint:
    def test_list_prestations_returns_200(self, auth_client, prestation):
        resp = auth_client.get('/api/v1/prestations/')
        assert resp.status_code == 200

    def test_prestation_has_expected_fields(self, auth_client, prestation):
        resp = auth_client.get(f'/api/v1/prestations/{prestation.id}/')
        assert resp.status_code == 200
        for field in ['name', 'status', 'status_label', 'start_date', 'annual_price']:
            assert field in resp.data


# ─── Compte courant ───────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestCompteEndpoint:
    def test_list_transactions_returns_200(self, auth_client, client_profile):
        CompteTransaction.add(client=client_profile, label='Test', amount=Decimal('100'))
        resp = auth_client.get('/api/v1/compte/')
        assert resp.status_code == 200

    def test_transaction_fields(self, auth_client, client_profile):
        CompteTransaction.add(client=client_profile, label='Paiement FAC-2025-0001', amount=Decimal('500'))
        resp = auth_client.get('/api/v1/compte/')
        tx = resp.data['results'][0]
        assert 'label' in tx
        assert 'amount' in tx
        assert 'balance_after' in tx
        assert 'date' in tx

    def test_transactions_ordered_newest_first(self, auth_client, client_profile):
        tx1 = CompteTransaction.add(client=client_profile, label='T1', amount=Decimal('100'))
        tx2 = CompteTransaction.add(client=client_profile, label='T2', amount=Decimal('200'))
        resp = auth_client.get('/api/v1/compte/')
        ids = [t['id'] for t in resp.data['results']]
        assert ids.index(tx2.id) < ids.index(tx1.id)


# ─── Dashboard ────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestDashboardEndpoint:
    def test_dashboard_returns_200(self, auth_client):
        resp = auth_client.get('/api/v1/dashboard/')
        assert resp.status_code == 200

    def test_dashboard_structure(self, auth_client):
        resp = auth_client.get('/api/v1/dashboard/')
        for key in ['balance', 'unpaid_amount', 'next_maintenance',
                    'pending_devis_count', 'active_services', 'recent_invoices']:
            assert key in resp.data, f"Dashboard missing key: {key}"

    def test_dashboard_next_maintenance_is_future(self, auth_client, client_profile):
        from django.utils import timezone
        from datetime import timedelta
        m_past = MaintenanceFactory(
            client=client_profile,
            scheduled_at=timezone.now() - timedelta(days=1),
            status='scheduled',
        )
        m_future = MaintenanceFactory(
            client=client_profile,
            scheduled_at=timezone.now() + timedelta(days=5),
            status='scheduled',
        )
        resp = auth_client.get('/api/v1/dashboard/')
        assert resp.data['next_maintenance'] is not None
        assert resp.data['next_maintenance']['id'] == m_future.id

    def test_dashboard_next_maintenance_null_if_none_scheduled(self, auth_client):
        resp = auth_client.get('/api/v1/dashboard/')
        assert resp.data['next_maintenance'] is None

    def test_dashboard_pending_devis_count(self, auth_client, client_profile):
        DevisFactory(client=client_profile, status='sent')
        DevisFactory(client=client_profile, status='sent')
        DevisFactory(client=client_profile, status='accepted')  # ne compte pas
        resp = auth_client.get('/api/v1/dashboard/')
        assert resp.data['pending_devis_count'] == 2

    def test_dashboard_recent_invoices_limited_to_5(self, auth_client, client_profile):
        for _ in range(7):
            FactureFactory(client=client_profile, with_lines=1)
        resp = auth_client.get('/api/v1/dashboard/')
        assert len(resp.data['recent_invoices']) <= 5
