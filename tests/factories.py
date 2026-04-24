"""
Factory Boy factories — génèrent des objets réalistes pour les tests.
Principe : chaque factory produit un objet valide et cohérent par défaut.
Les tests surchargent uniquement ce qui les intéresse.
"""
from decimal import Decimal
from datetime import date, timedelta

import factory
from django.contrib.auth import get_user_model
from factory.django import DjangoModelFactory

from apps.clients.models import (
    Client, Devis, DevisLigne, Facture, FactureLigne,
    Maintenance, Prestation, CompteTransaction,
)

User = get_user_model()


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User

    username   = factory.Sequence(lambda n: f'user{n}')
    email      = factory.LazyAttribute(lambda o: f'{o.username}@example.com')
    first_name = factory.Faker('first_name', locale='fr_BE')
    last_name  = factory.Faker('last_name',  locale='fr_BE')
    password   = factory.PostGenerationMethodCall('set_password', 'password123!')
    is_active  = True


class ClientFactory(DjangoModelFactory):
    class Meta:
        model = Client
        # Évite de créer un Client si le User en a déjà un (signal)
        django_get_or_create = ('user',)

    user         = factory.SubFactory(UserFactory)
    phone        = factory.Faker('phone_number', locale='fr_BE')
    address      = factory.Faker('address', locale='fr_BE')
    company_name = ''
    vat_number   = ''


class ProClientFactory(ClientFactory):
    """Client professionnel (entreprise)."""
    company_name = factory.Faker('company', locale='fr_BE')
    vat_number   = factory.LazyAttribute(lambda _: f'BE {factory.Faker("numerify", text="####.###.###")}')


class DevisLigneFactory(DjangoModelFactory):
    class Meta:
        model = DevisLigne

    devis           = factory.SubFactory('tests.factories.DevisFactory')
    description     = factory.Faker('sentence', nb_words=6, locale='fr_BE')
    quantity        = Decimal('1.00')
    unit_price_excl = factory.LazyFunction(lambda: Decimal('500.00'))
    vat_rate        = Decimal('21.00')
    order           = factory.Sequence(lambda n: n)


class DevisFactory(DjangoModelFactory):
    class Meta:
        model = Devis

    client      = factory.SubFactory(ClientFactory)
    title       = factory.Faker('sentence', nb_words=5, locale='fr_BE')
    description = factory.Faker('paragraph', locale='fr_BE')
    status      = Devis.STATUS_SENT
    valid_until = factory.LazyFunction(lambda: date.today() + timedelta(days=30))

    @factory.post_generation
    def with_lines(self, create, extracted, **kwargs):
        """Usage: DevisFactory(with_lines=2)"""
        if not create:
            return
        count = extracted if extracted else 2
        DevisLigneFactory.create_batch(count, devis=self)


class FactureLigneFactory(DjangoModelFactory):
    class Meta:
        model = FactureLigne

    facture         = factory.SubFactory('tests.factories.FactureFactory')
    description     = factory.Faker('sentence', nb_words=6, locale='fr_BE')
    quantity        = Decimal('1.00')
    unit_price_excl = factory.LazyFunction(lambda: Decimal('1000.00'))
    vat_rate        = Decimal('21.00')
    order           = factory.Sequence(lambda n: n)


class FactureFactory(DjangoModelFactory):
    class Meta:
        model = Facture

    client   = factory.SubFactory(ClientFactory)
    title    = factory.Faker('sentence', nb_words=5, locale='fr_BE')
    status   = Facture.STATUS_PENDING
    due_date = factory.LazyFunction(lambda: date.today() + timedelta(days=30))

    @factory.post_generation
    def with_lines(self, create, extracted, **kwargs):
        if not create:
            return
        count = extracted if extracted else 2
        FactureLigneFactory.create_batch(count, facture=self)


class OverdueFactureFactory(FactureFactory):
    status   = Facture.STATUS_OVERDUE
    due_date = factory.LazyFunction(lambda: date.today() - timedelta(days=10))


class MaintenanceFactory(DjangoModelFactory):
    class Meta:
        model = Maintenance

    client       = factory.SubFactory(ClientFactory)
    title        = factory.Faker('sentence', nb_words=4, locale='fr_BE')
    description  = factory.Faker('paragraph', locale='fr_BE')
    scheduled_at = factory.Faker('future_datetime', end_date='+60d', tzinfo=None)
    status       = Maintenance.STATUS_SCHEDULED
    technician   = factory.Faker('name', locale='fr_BE')


class PrestationFactory(DjangoModelFactory):
    class Meta:
        model = Prestation

    client       = factory.SubFactory(ClientFactory)
    name         = 'Entretien annuel toiture verte'
    description  = factory.Faker('paragraph', locale='fr_BE')
    start_date   = factory.LazyFunction(lambda: date.today())
    status       = 'active'
    annual_price = Decimal('350.00')


class CompteTransactionFactory(DjangoModelFactory):
    class Meta:
        model = CompteTransaction

    client        = factory.SubFactory(ClientFactory)
    label         = factory.Faker('sentence', nb_words=4, locale='fr_BE')
    amount        = Decimal('500.00')
    balance_after = Decimal('500.00')
