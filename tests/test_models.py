"""
Tests unitaires des modèles.
Vérifie la logique métier pure, sans HTTP.
"""
from decimal import Decimal
from datetime import date, timedelta

import pytest
from django.utils import timezone
from freezegun import freeze_time

from apps.clients.models import (
    Client, Devis, DevisLigne, Facture, FactureLigne,
    Maintenance, CompteTransaction,
)
from .factories import (
    UserFactory, ClientFactory, DevisFactory, DevisLigneFactory,
    FactureFactory, FactureLigneFactory, CompteTransactionFactory,
)


# ─── Signal : création automatique du profil Client ──────────────────────────

@pytest.mark.django_db
class TestClientSignal:
    def test_client_created_automatically_on_user_creation(self):
        user = UserFactory()
        assert hasattr(user, 'client')
        assert isinstance(user.client, Client)

    def test_client_not_duplicated_on_user_save(self):
        user = UserFactory()
        user.first_name = 'Updated'
        user.save()
        assert Client.objects.filter(user=user).count() == 1


# ─── Devis ────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestDevisModel:
    def test_reference_auto_generated(self):
        devis = DevisFactory()
        assert devis.reference.startswith('DEV-')
        year = date.today().year
        assert str(year) in devis.reference

    def test_reference_not_overwritten_if_set(self):
        devis = DevisFactory()
        original = devis.reference
        devis.title = 'Updated'
        devis.save()
        devis.refresh_from_db()
        assert devis.reference == original

    def test_amount_excl_is_sum_of_lines(self):
        devis = DevisFactory(with_lines=0)
        DevisLigneFactory(devis=devis, quantity=Decimal('2'), unit_price_excl=Decimal('100.00'), vat_rate=Decimal('21'))
        DevisLigneFactory(devis=devis, quantity=Decimal('1'), unit_price_excl=Decimal('300.00'), vat_rate=Decimal('21'))
        # 2×100 + 1×300 = 500
        assert devis.amount_excl == Decimal('500.00')

    def test_total_vat_computed_correctly(self):
        devis = DevisFactory(with_lines=0)
        DevisLigneFactory(devis=devis, quantity=Decimal('1'), unit_price_excl=Decimal('100.00'), vat_rate=Decimal('21'))
        assert devis.total_vat == Decimal('21.00')

    def test_amount_incl_equals_excl_plus_vat(self):
        devis = DevisFactory(with_lines=0)
        DevisLigneFactory(devis=devis, quantity=Decimal('1'), unit_price_excl=Decimal('100.00'), vat_rate=Decimal('21'))
        assert devis.amount_incl == Decimal('121.00')

    def test_amount_zero_if_no_lines(self):
        devis = DevisFactory(with_lines=0)
        assert devis.amount_excl == Decimal('0.00')
        assert devis.amount_incl == Decimal('0.00')

    @freeze_time('2025-06-15')
    def test_reference_sequential_within_year(self):
        d1 = DevisFactory()
        d2 = DevisFactory()
        # Les deux doivent avoir 2025 et des numéros différents
        assert d1.reference != d2.reference
        assert '2025' in d1.reference
        assert '2025' in d2.reference

    def test_str_contains_reference_and_client(self):
        devis = DevisFactory()
        s = str(devis)
        assert devis.reference in s


# ─── DevisLigne ───────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestDevisLigneModel:
    def test_total_excl(self):
        ligne = DevisLigneFactory(quantity=Decimal('3'), unit_price_excl=Decimal('50.00'))
        assert ligne.total_excl == Decimal('150.00')

    def test_vat_amount_21_percent(self):
        ligne = DevisLigneFactory(quantity=Decimal('1'), unit_price_excl=Decimal('100.00'), vat_rate=Decimal('21'))
        assert ligne.vat_amount == Decimal('21.00')

    def test_vat_amount_6_percent(self):
        ligne = DevisLigneFactory(quantity=Decimal('1'), unit_price_excl=Decimal('100.00'), vat_rate=Decimal('6'))
        assert ligne.vat_amount == Decimal('6.00')

    def test_total_incl(self):
        ligne = DevisLigneFactory(quantity=Decimal('2'), unit_price_excl=Decimal('100.00'), vat_rate=Decimal('21'))
        # (2 × 100) × 1.21 = 242
        assert ligne.total_incl == Decimal('242.00')

    def test_total_rounded_to_cents(self):
        ligne = DevisLigneFactory(quantity=Decimal('3'), unit_price_excl=Decimal('10.333'), vat_rate=Decimal('21'))
        # Vérifie que le résultat a 2 décimales
        assert ligne.total_excl == ligne.total_excl.quantize(Decimal('0.01'))


# ─── Facture ──────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestFactureModel:
    def test_reference_auto_generated(self):
        facture = FactureFactory()
        assert facture.reference.startswith('FAC-')

    def test_is_overdue_false_for_future_due_date(self):
        facture = FactureFactory(
            status=Facture.STATUS_PENDING,
            due_date=date.today() + timedelta(days=10),
        )
        assert facture.is_overdue is False

    def test_is_overdue_true_for_past_due_date(self):
        facture = FactureFactory(
            status=Facture.STATUS_PENDING,
            due_date=date.today() - timedelta(days=1),
        )
        assert facture.is_overdue is True

    def test_is_overdue_false_if_already_paid(self):
        facture = FactureFactory(
            status=Facture.STATUS_PAID,
            due_date=date.today() - timedelta(days=5),
        )
        assert facture.is_overdue is False

    def test_mark_as_paid_updates_status(self):
        facture = FactureFactory(with_lines=1)
        facture.mark_as_paid()
        facture.refresh_from_db()
        assert facture.status == Facture.STATUS_PAID
        assert facture.paid_at is not None

    def test_mark_as_paid_creates_transaction(self):
        facture = FactureFactory(with_lines=1)
        facture.mark_as_paid()
        assert CompteTransaction.objects.filter(
            client=facture.client,
            related_invoice=facture,
        ).exists()

    def test_mark_as_paid_transaction_amount_matches_invoice(self):
        facture = FactureFactory(with_lines=0)
        FactureLigneFactory(facture=facture, quantity=1, unit_price_excl=Decimal('1000'), vat_rate=Decimal('21'))
        facture.mark_as_paid()
        tx = CompteTransaction.objects.get(related_invoice=facture)
        assert tx.amount == Decimal('1210.00')


# ─── CompteTransaction ────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestCompteTransaction:
    def test_first_transaction_balance_equals_amount(self, client_profile):
        tx = CompteTransaction.add(client=client_profile, label='Test', amount=Decimal('500'))
        assert tx.balance_after == Decimal('500.00')

    def test_second_transaction_cumulates_balance(self, client_profile):
        CompteTransaction.add(client=client_profile, label='Tx1', amount=Decimal('500'))
        tx2 = CompteTransaction.add(client=client_profile, label='Tx2', amount=Decimal('200'))
        assert tx2.balance_after == Decimal('700.00')

    def test_negative_transaction_reduces_balance(self, client_profile):
        CompteTransaction.add(client=client_profile, label='Crédit', amount=Decimal('1000'))
        tx = CompteTransaction.add(client=client_profile, label='Débit', amount=Decimal('-300'))
        assert tx.balance_after == Decimal('700.00')

    def test_client_balance_property_matches_last_transaction(self, client_profile):
        CompteTransaction.add(client=client_profile, label='T1', amount=Decimal('500'))
        CompteTransaction.add(client=client_profile, label='T2', amount=Decimal('250'))
        assert client_profile.balance == Decimal('750.00')

    def test_balance_zero_if_no_transactions(self, client_profile):
        assert client_profile.balance == Decimal('0.00')

    def test_transactions_are_isolated_between_clients(self, client_profile, client_profile2):
        CompteTransaction.add(client=client_profile, label='T1', amount=Decimal('1000'))
        CompteTransaction.add(client=client_profile2, label='T2', amount=Decimal('500'))
        assert client_profile.balance == Decimal('1000.00')
        assert client_profile2.balance == Decimal('500.00')


# ─── Client properties ────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestClientProperties:
    def test_unpaid_amount_sums_pending_and_overdue(self, client_profile):
        FactureLigneFactory(
            facture=FactureFactory(client=client_profile, status='pending', with_lines=0),
            quantity=1, unit_price_excl=Decimal('1000'), vat_rate=Decimal('21'),
        )
        FactureLigneFactory(
            facture=FactureFactory(client=client_profile, status='overdue', with_lines=0),
            quantity=1, unit_price_excl=Decimal('500'), vat_rate=Decimal('21'),
        )
        # 1210 + 605 = 1815
        assert client_profile.unpaid_amount == Decimal('1815.00')

    def test_unpaid_amount_excludes_paid_invoices(self, client_profile):
        FactureLigneFactory(
            facture=FactureFactory(client=client_profile, status='paid', with_lines=0),
            quantity=1, unit_price_excl=Decimal('1000'), vat_rate=Decimal('21'),
        )
        assert client_profile.unpaid_amount == Decimal('0.00')
