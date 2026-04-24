"""
Tests de l'interface admin Django.
Vérifie : génération PDF, action mark_paid, téléchargement ZIP,
accès réservé au staff, badges de statut.
"""
from decimal import Decimal
from unittest.mock import patch, MagicMock

import pytest
from django.urls import reverse

from apps.clients.models import Facture, CompteTransaction
from .factories import (
    UserFactory, FactureFactory, FactureLigneFactory,
    DevisFactory, DevisLigneFactory,
)


# ─── Accès admin ─────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestAdminAccess:
    def test_admin_requires_staff(self, auth_client):
        """Un utilisateur non-staff ne peut pas accéder à l'admin."""
        resp = auth_client.get('/admin/')
        # Redirige vers le login ou 403
        assert resp.status_code in (302, 403)

    def test_admin_accessible_for_staff(self, admin_client):
        resp = admin_client.get('/admin/')
        assert resp.status_code == 200

    def test_facture_list_accessible(self, admin_client):
        resp = admin_client.get('/admin/clients/facture/')
        assert resp.status_code == 200

    def test_devis_list_accessible(self, admin_client):
        resp = admin_client.get('/admin/clients/devis/')
        assert resp.status_code == 200

    def test_client_list_accessible(self, admin_client):
        resp = admin_client.get('/admin/clients/client/')
        assert resp.status_code == 200


# ─── PDF Devis ────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestDevisPDF:
    def test_pdf_endpoint_requires_staff(self, auth_client, client_profile):
        devis = DevisFactory(client=client_profile, with_lines=1)
        resp = auth_client.get(f'/admin/clients/devis/{devis.id}/pdf/')
        assert resp.status_code in (302, 403)

    @patch('apps.clients.admin.HTML')
    def test_pdf_endpoint_returns_pdf_content_type(self, mock_html, admin_client, client_profile):
        """Vérifie que le endpoint PDF retourne application/pdf."""
        devis = DevisFactory(client=client_profile, with_lines=1)

        # Mock WeasyPrint pour éviter la dépendance système (libpango)
        mock_pdf = MagicMock()
        mock_pdf.write_pdf.return_value = b'%PDF-1.4 fake pdf content'
        mock_html.return_value = mock_pdf

        resp = admin_client.get(f'/admin/clients/devis/{devis.id}/pdf/')
        assert resp.status_code == 200
        assert resp['Content-Type'] == 'application/pdf'

    @patch('apps.clients.admin.HTML')
    def test_pdf_filename_contains_reference(self, mock_html, admin_client, client_profile):
        """Le nom du fichier PDF doit contenir la référence du devis."""
        devis = DevisFactory(client=client_profile, with_lines=1)
        mock_pdf = MagicMock()
        mock_pdf.write_pdf.return_value = b'%PDF-1.4 fake pdf'
        mock_html.return_value = mock_pdf

        resp = admin_client.get(f'/admin/clients/devis/{devis.id}/pdf/')
        assert resp.status_code == 200
        content_disposition = resp.get('Content-Disposition', '')
        assert devis.reference in content_disposition

    def test_pdf_endpoint_404_for_nonexistent_devis(self, admin_client):
        resp = admin_client.get('/admin/clients/devis/99999/pdf/')
        assert resp.status_code == 404


# ─── PDF Facture ──────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestFacturePDF:
    @patch('apps.clients.admin.HTML')
    def test_facture_pdf_returns_pdf_content_type(self, mock_html, admin_client, client_profile):
        facture = FactureFactory(client=client_profile, with_lines=1)
        mock_pdf = MagicMock()
        mock_pdf.write_pdf.return_value = b'%PDF-1.4 fake pdf'
        mock_html.return_value = mock_pdf

        resp = admin_client.get(f'/admin/clients/facture/{facture.id}/pdf/')
        assert resp.status_code == 200
        assert resp['Content-Type'] == 'application/pdf'

    @patch('apps.clients.admin.HTML')
    def test_facture_pdf_filename_contains_reference(self, mock_html, admin_client, client_profile):
        facture = FactureFactory(client=client_profile, with_lines=1)
        mock_pdf = MagicMock()
        mock_pdf.write_pdf.return_value = b'%PDF-1.4 fake pdf'
        mock_html.return_value = mock_pdf

        resp = admin_client.get(f'/admin/clients/facture/{facture.id}/pdf/')
        content_disposition = resp.get('Content-Disposition', '')
        assert facture.reference in content_disposition


# ─── Action : mark_paid ───────────────────────────────────────────────────────

@pytest.mark.django_db
class TestMarkPaidAction:
    def test_mark_paid_action_updates_status(self, admin_client, client_profile):
        facture = FactureFactory(client=client_profile, with_lines=1, status='pending')
        resp = admin_client.post('/admin/clients/facture/', {
            'action': 'action_mark_paid',
            '_selected_action': [facture.id],
        })
        # Django admin redirige après une action
        assert resp.status_code in (200, 302)
        facture.refresh_from_db()
        assert facture.status == Facture.STATUS_PAID

    def test_mark_paid_action_creates_transaction(self, admin_client, client_profile):
        facture = FactureFactory(client=client_profile, with_lines=0, status='pending')
        FactureLigneFactory(facture=facture, quantity=1, unit_price_excl=Decimal('1000'), vat_rate=Decimal('21'))

        admin_client.post('/admin/clients/facture/', {
            'action': 'action_mark_paid',
            '_selected_action': [facture.id],
        })
        assert CompteTransaction.objects.filter(
            client=client_profile,
            related_invoice=facture,
        ).exists()

    def test_mark_paid_action_bulk(self, admin_client, client_profile):
        """L'action fonctionne sur plusieurs factures en même temps."""
        f1 = FactureFactory(client=client_profile, with_lines=1, status='pending')
        f2 = FactureFactory(client=client_profile, with_lines=1, status='pending')

        admin_client.post('/admin/clients/facture/', {
            'action': 'action_mark_paid',
            '_selected_action': [f1.id, f2.id],
        })
        f1.refresh_from_db()
        f2.refresh_from_db()
        assert f1.status == Facture.STATUS_PAID
        assert f2.status == Facture.STATUS_PAID

    def test_mark_paid_already_paid_is_idempotent(self, admin_client, client_profile):
        """Appeler mark_paid sur une facture déjà payée ne crée pas de doublon."""
        facture = FactureFactory(client=client_profile, with_lines=1, status='paid')
        initial_tx_count = CompteTransaction.objects.filter(client=client_profile).count()

        admin_client.post('/admin/clients/facture/', {
            'action': 'action_mark_paid',
            '_selected_action': [facture.id],
        })
        final_tx_count = CompteTransaction.objects.filter(client=client_profile).count()
        # Pas de nouvelle transaction créée
        assert final_tx_count == initial_tx_count


# ─── Action : téléchargement ZIP ─────────────────────────────────────────────

@pytest.mark.django_db
class TestZipDownloadAction:
    @patch('apps.clients.admin.HTML')
    def test_zip_devis_action_returns_zip(self, mock_html, admin_client, client_profile):
        d1 = DevisFactory(client=client_profile, with_lines=1)
        d2 = DevisFactory(client=client_profile, with_lines=1)
        mock_pdf = MagicMock()
        mock_pdf.write_pdf.return_value = b'%PDF-1.4 fake'
        mock_html.return_value = mock_pdf

        resp = admin_client.post('/admin/clients/devis/', {
            'action': 'action_generate_pdf',
            '_selected_action': [d1.id, d2.id],
        })
        assert resp.status_code == 200
        assert resp['Content-Type'] == 'application/zip'

    @patch('apps.clients.admin.HTML')
    def test_zip_factures_action_returns_zip(self, mock_html, admin_client, client_profile):
        f1 = FactureFactory(client=client_profile, with_lines=1)
        f2 = FactureFactory(client=client_profile, with_lines=1)
        mock_pdf = MagicMock()
        mock_pdf.write_pdf.return_value = b'%PDF-1.4 fake'
        mock_html.return_value = mock_pdf

        resp = admin_client.post('/admin/clients/facture/', {
            'action': 'action_generate_pdf',
            '_selected_action': [f1.id, f2.id],
        })
        assert resp.status_code == 200
        assert resp['Content-Type'] == 'application/zip'


# ─── Changelist : filtres et recherche ───────────────────────────────────────

@pytest.mark.django_db
class TestAdminFilters:
    def test_facture_filter_by_status(self, admin_client, client_profile):
        FactureFactory(client=client_profile, with_lines=1, status='paid')
        FactureFactory(client=client_profile, with_lines=1, status='pending')

        resp = admin_client.get('/admin/clients/facture/?status=paid')
        assert resp.status_code == 200

    def test_facture_search_by_reference(self, admin_client, client_profile):
        facture = FactureFactory(client=client_profile, with_lines=1)
        resp = admin_client.get(f'/admin/clients/facture/?q={facture.reference}')
        assert resp.status_code == 200

    def test_devis_filter_by_status(self, admin_client, client_profile):
        DevisFactory(client=client_profile, with_lines=1, status='draft')
        resp = admin_client.get('/admin/clients/devis/?status=draft')
        assert resp.status_code == 200
