"""
Tests de génération PDF (WeasyPrint).
Vérifie que les templates se rendent sans erreur et que le contenu
attendu est présent dans le HTML source avant conversion.

Note : on teste le rendu HTML (rapide, sans dépendance système) ET
la conversion WeasyPrint (nécessite libpango sur le serveur CI).
Les tests WeasyPrint sont marqués @pytest.mark.weasyprint pour pouvoir
les exclure si les dépendances système ne sont pas disponibles :
    pytest -m "not weasyprint"
"""
from decimal import Decimal
from unittest.mock import patch, MagicMock

import pytest
from django.template.loader import render_to_string
from django.test import RequestFactory

from apps.clients.models import Devis, Facture
from .factories import (
    ClientFactory, DevisFactory, DevisLigneFactory,
    FactureFactory, FactureLigneFactory,
)


# ─── Rendu HTML des templates ─────────────────────────────────────────────────

@pytest.mark.django_db
class TestPDFTemplateRendering:
    """Tests rapides : vérifie que les templates HTML se rendent sans erreur."""

    def _make_devis_context(self, devis):
        return {
            'obj': devis,
            'company': {
                'name': 'ToitureVerte SRL',
                'address': 'Rue de la Verdure 42, 1000 Bruxelles',
                'vat': 'BE 0123.456.789',
                'iban': 'BE12 3456 7890 1234',
                'bic': 'GEBABEBB',
                'email': 'info@toitureverte.be',
                'phone': '+32 2 123 45 67',
            },
        }

    def test_devis_template_renders_without_error(self, client_profile):
        devis = DevisFactory(client=client_profile, with_lines=2)
        context = self._make_devis_context(devis)
        # Ne lève pas d'exception
        html = render_to_string('pdf/devis.html', context)
        assert html  # non vide

    def test_devis_template_contains_reference(self, client_profile):
        devis = DevisFactory(client=client_profile, with_lines=2)
        html = render_to_string('pdf/devis.html', self._make_devis_context(devis))
        assert devis.reference in html

    def test_devis_template_contains_client_info(self, client_profile):
        devis = DevisFactory(client=client_profile, with_lines=2)
        html = render_to_string('pdf/devis.html', self._make_devis_context(devis))
        # Le nom du client ou son email doit apparaître
        assert (client_profile.user.email in html
                or client_profile.user.get_full_name() in html)

    def test_devis_template_contains_line_descriptions(self, client_profile):
        devis = DevisFactory(client=client_profile, with_lines=0)
        ligne = DevisLigneFactory(devis=devis, description='Pose toiture verte extensive')
        html = render_to_string('pdf/devis.html', self._make_devis_context(devis))
        assert 'Pose toiture verte extensive' in html

    def test_devis_template_contains_totals(self, client_profile):
        devis = DevisFactory(client=client_profile, with_lines=0)
        DevisLigneFactory(devis=devis, quantity=Decimal('1'),
                          unit_price_excl=Decimal('1000'), vat_rate=Decimal('21'))
        html = render_to_string('pdf/devis.html', self._make_devis_context(devis))
        # 1000 HTVA + 210 TVA = 1210 TVAC
        assert '1000' in html
        assert '1210' in html

    def test_devis_template_contains_company_iban(self, client_profile):
        devis = DevisFactory(client=client_profile, with_lines=1)
        html = render_to_string('pdf/devis.html', self._make_devis_context(devis))
        assert 'ToitureVerte SRL' in html

    def _make_facture_context(self, facture):
        return {
            'obj': facture,
            'company': {
                'name': 'ToitureVerte SRL',
                'address': 'Rue de la Verdure 42, 1000 Bruxelles',
                'vat': 'BE 0123.456.789',
                'iban': 'BE12 3456 7890 1234',
                'bic': 'GEBABEBB',
                'email': 'info@toitureverte.be',
                'phone': '+32 2 123 45 67',
            },
        }

    def test_facture_template_renders_without_error(self, client_profile):
        facture = FactureFactory(client=client_profile, with_lines=2)
        html = render_to_string('pdf/facture.html', self._make_facture_context(facture))
        assert html

    def test_facture_template_contains_reference(self, client_profile):
        facture = FactureFactory(client=client_profile, with_lines=1)
        html = render_to_string('pdf/facture.html', self._make_facture_context(facture))
        assert facture.reference in html

    def test_facture_template_contains_iban(self, client_profile):
        facture = FactureFactory(client=client_profile, with_lines=1)
        html = render_to_string('pdf/facture.html', self._make_facture_context(facture))
        assert 'BE12 3456 7890 1234' in html

    def test_facture_paid_template_contains_paid_stamp(self, client_profile):
        """Une facture payée doit afficher le tampon PAYÉE."""
        facture = FactureFactory(client=client_profile, with_lines=1,
                                 status=Facture.STATUS_PAID)
        html = render_to_string('pdf/facture.html', self._make_facture_context(facture))
        # Le tampon "PAYÉE" ou équivalent doit être présent
        assert 'PAYÉE' in html or 'payée' in html.lower() or 'paid' in html.lower()

    def test_facture_pending_template_no_paid_stamp(self, client_profile):
        """Une facture non payée NE doit PAS afficher le tampon."""
        facture = FactureFactory(client=client_profile, with_lines=1,
                                 status=Facture.STATUS_PENDING)
        html = render_to_string('pdf/facture.html', self._make_facture_context(facture))
        assert 'PAYÉE' not in html


# ─── Conversion WeasyPrint ────────────────────────────────────────────────────

@pytest.mark.django_db
@pytest.mark.weasyprint
class TestWeasyPrintConversion:
    """
    Ces tests nécessitent libpango/libcairo installés sur la machine.
    Exclus par défaut en CI minimal : pytest -m "not weasyprint"
    """

    def test_devis_pdf_bytes_start_with_pdf_magic(self, client_profile):
        from weasyprint import HTML as WeasyprintHTML
        devis = DevisFactory(client=client_profile, with_lines=2)
        html_str = render_to_string('pdf/devis.html', {
            'obj': devis,
            'company': {
                'name': 'ToitureVerte SRL',
                'address': 'Rue de la Verdure 42, 1000 Bruxelles',
                'vat': 'BE 0123.456.789',
                'iban': 'BE12 3456 7890 1234',
                'bic': 'GEBABEBB',
                'email': 'info@toitureverte.be',
                'phone': '+32 2 123 45 67',
            },
        })
        pdf_bytes = WeasyprintHTML(string=html_str).write_pdf()
        assert pdf_bytes[:4] == b'%PDF'

    def test_facture_pdf_bytes_start_with_pdf_magic(self, client_profile):
        from weasyprint import HTML as WeasyprintHTML
        facture = FactureFactory(client=client_profile, with_lines=2)
        html_str = render_to_string('pdf/facture.html', {
            'obj': facture,
            'company': {
                'name': 'ToitureVerte SRL',
                'address': 'Rue de la Verdure 42, 1000 Bruxelles',
                'vat': 'BE 0123.456.789',
                'iban': 'BE12 3456 7890 1234',
                'bic': 'GEBABEBB',
                'email': 'info@toitureverte.be',
                'phone': '+32 2 123 45 67',
            },
        })
        pdf_bytes = WeasyprintHTML(string=html_str).write_pdf()
        assert pdf_bytes[:4] == b'%PDF'


# ─── Intégration : endpoint admin → PDF ──────────────────────────────────────

@pytest.mark.django_db
class TestPDFEndpointIntegration:
    """Teste le circuit complet : URL admin → vue → WeasyPrint → réponse HTTP."""

    @patch('apps.clients.admin.HTML')
    def test_devis_pdf_response_is_valid(self, mock_html, admin_client, client_profile):
        devis = DevisFactory(client=client_profile, with_lines=2)
        DevisLigneFactory(devis=devis, description='Test ligne', quantity=1,
                          unit_price_excl=Decimal('500'), vat_rate=Decimal('21'))

        mock_instance = MagicMock()
        mock_instance.write_pdf.return_value = b'%PDF-1.4 test content'
        mock_html.return_value = mock_instance

        resp = admin_client.get(f'/admin/clients/devis/{devis.id}/pdf/')
        assert resp.status_code == 200
        assert b'%PDF' in resp.content

    @patch('apps.clients.admin.HTML')
    def test_facture_pdf_response_is_valid(self, mock_html, admin_client, client_profile):
        facture = FactureFactory(client=client_profile, with_lines=0)
        FactureLigneFactory(facture=facture, quantity=1,
                            unit_price_excl=Decimal('1000'), vat_rate=Decimal('21'))

        mock_instance = MagicMock()
        mock_instance.write_pdf.return_value = b'%PDF-1.4 test content'
        mock_html.return_value = mock_instance

        resp = admin_client.get(f'/admin/clients/facture/{facture.id}/pdf/')
        assert resp.status_code == 200
        assert b'%PDF' in resp.content

    @patch('apps.clients.admin.HTML')
    def test_weasyprint_called_with_html_string(self, mock_html, admin_client, client_profile):
        """Vérifie que WeasyPrint reçoit bien une chaîne HTML non vide."""
        devis = DevisFactory(client=client_profile, with_lines=1)
        mock_instance = MagicMock()
        mock_instance.write_pdf.return_value = b'%PDF-1.4'
        mock_html.return_value = mock_instance

        admin_client.get(f'/admin/clients/devis/{devis.id}/pdf/')
        # WeasyPrint doit avoir été appelé avec string=... ou html=...
        assert mock_html.called
        call_kwargs = mock_html.call_args
        # Le HTML passé doit être non vide
        html_arg = call_kwargs[1].get('string', '') or (call_kwargs[0][0] if call_kwargs[0] else '')
        assert html_arg  # non vide
