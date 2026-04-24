"""
Tests d'isolation — le test le plus CRITIQUE de l'application.

Principe : un client authentifié NE DOIT JAMAIS pouvoir voir,
modifier ou deviner les données d'un autre client.
Ces tests vérifient l'isolation de chaque endpoint.
"""
import pytest


@pytest.mark.django_db
class TestDevisIsolation:
    def test_list_returns_only_own_devis(self, auth_client, auth_client2,
                                          devis, devis_other):
        resp = auth_client.get('/api/v1/devis/')
        ids = [d['id'] for d in resp.data['results']]
        assert devis.id in ids
        assert devis_other.id not in ids

    def test_retrieve_other_client_devis_returns_404(self, auth_client, devis_other):
        """Le client 1 ne peut pas accéder au devis du client 2, même en devinant l'ID."""
        resp = auth_client.get(f'/api/v1/devis/{devis_other.id}/')
        assert resp.status_code == 404

    def test_client2_cannot_see_client1_devis(self, auth_client2, devis):
        resp = auth_client2.get(f'/api/v1/devis/{devis.id}/')
        assert resp.status_code == 404


@pytest.mark.django_db
class TestFactureIsolation:
    def test_list_returns_only_own_factures(self, auth_client, auth_client2,
                                             facture, facture_other):
        resp = auth_client.get('/api/v1/factures/')
        ids = [f['id'] for f in resp.data['results']]
        assert facture.id in ids
        assert facture_other.id not in ids

    def test_retrieve_other_client_facture_returns_404(self, auth_client, facture_other):
        resp = auth_client.get(f'/api/v1/factures/{facture_other.id}/')
        assert resp.status_code == 404

    def test_summary_uses_only_own_factures(self, auth_client, auth_client2,
                                              client_profile, client_profile2):
        from decimal import Decimal
        from .factories import FactureFactory, FactureLigneFactory
        f1 = FactureFactory(client=client_profile, status='pending', with_lines=0)
        FactureLigneFactory(facture=f1, quantity=1, unit_price_excl=Decimal('1000'), vat_rate=Decimal('21'))
        f2 = FactureFactory(client=client_profile2, status='pending', with_lines=0)
        FactureLigneFactory(facture=f2, quantity=1, unit_price_excl=Decimal('5000'), vat_rate=Decimal('21'))

        resp = auth_client.get('/api/v1/factures/summary/')
        assert resp.status_code == 200
        # Client 1 ne voit que sa propre facture (1210, pas 6050)
        assert float(resp.data['total_pending']) == pytest.approx(1210.0)


@pytest.mark.django_db
class TestMaintenanceIsolation:
    def test_list_returns_only_own_maintenance(self, auth_client, auth_client2,
                                                maintenance, client_profile2):
        from .factories import MaintenanceFactory
        other = MaintenanceFactory(client=client_profile2)
        resp = auth_client.get('/api/v1/maintenance/')
        ids = [m['id'] for m in resp.data['results']]
        assert maintenance.id in ids
        assert other.id not in ids

    def test_retrieve_other_client_maintenance_returns_404(self, auth_client, client_profile2):
        from .factories import MaintenanceFactory
        other = MaintenanceFactory(client=client_profile2)
        resp = auth_client.get(f'/api/v1/maintenance/{other.id}/')
        assert resp.status_code == 404


@pytest.mark.django_db
class TestCompteIsolation:
    def test_compte_returns_only_own_transactions(self, auth_client, client_profile, client_profile2):
        from decimal import Decimal
        from apps.clients.models import CompteTransaction
        tx1 = CompteTransaction.add(client=client_profile, label='T1', amount=Decimal('100'))
        CompteTransaction.add(client=client_profile2, label='T2', amount=Decimal('999'))

        resp = auth_client.get('/api/v1/compte/')
        ids = [t['id'] for t in resp.data['results']]
        assert tx1.id in ids
        # Vérifie que la transaction de client2 n'est pas dans la liste
        assert all(t['balance_after'] != '999.00' for t in resp.data['results'])


@pytest.mark.django_db
class TestDashboardIsolation:
    def test_dashboard_uses_only_own_data(self, auth_client, auth_client2,
                                           client_profile, client_profile2):
        from .factories import MaintenanceFactory, FactureFactory, FactureLigneFactory, PrestationFactory
        from decimal import Decimal

        # Client 1 : 1 maintenance, 1 prestation
        MaintenanceFactory(client=client_profile)
        PrestationFactory(client=client_profile)

        # Client 2 : données différentes
        MaintenanceFactory(client=client_profile2)

        resp1 = auth_client.get('/api/v1/dashboard/')
        resp2 = auth_client2.get('/api/v1/dashboard/')

        assert resp1.status_code == 200
        assert resp2.status_code == 200
        # Les deux dashboards sont indépendants
        assert resp1.data != resp2.data
