from decimal import Decimal
from django.db import models, transaction
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()


class Client(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='client')
    company_name = models.CharField('Société', max_length=200, blank=True)
    phone = models.CharField('Téléphone', max_length=20, blank=True)
    address = models.TextField('Adresse', blank=True)
    vat_number = models.CharField('Numéro TVA', max_length=30, blank=True)
    notes = models.TextField('Notes internes', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Client'
        verbose_name_plural = 'Clients'
        ordering = ['-created_at']

    def __str__(self):
        name = self.user.get_full_name() or self.user.email
        return f"{name}" + (f" ({self.company_name})" if self.company_name else "")

    @property
    def balance(self):
        last = self.transactions.order_by('-date').first()
        return last.balance_after if last else Decimal('0.00')

    @property
    def unpaid_amount(self):
        # amount_incl est une @property calculée en Python (sum des lignes),
        # pas un champ DB — on itère donc en Python.
        return sum(
            f.amount_incl
            for f in self.factures.filter(
                status__in=['pending', 'overdue']
            ).prefetch_related('lignes')
        ) or Decimal('0.00')


# ─── Devis ────────────────────────────────────────────────────────────────────

class Devis(models.Model):
    STATUS_DRAFT     = 'draft'
    STATUS_SENT      = 'sent'
    STATUS_ACCEPTED  = 'accepted'
    STATUS_REFUSED   = 'refused'
    STATUS_EXPIRED   = 'expired'
    STATUS_CHOICES = [
        (STATUS_DRAFT,    'Brouillon'),
        (STATUS_SENT,     'Envoyé'),
        (STATUS_ACCEPTED, 'Accepté'),
        (STATUS_REFUSED,  'Refusé'),
        (STATUS_EXPIRED,  'Expiré'),
    ]

    client      = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='devis', verbose_name='Client')
    reference   = models.CharField('Référence', max_length=20, unique=True, blank=True)
    title       = models.CharField('Titre', max_length=200)
    description = models.TextField('Description', blank=True)
    status      = models.CharField('Statut', max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    valid_until = models.DateField('Valable jusqu\'au')
    pdf_file    = models.FileField('PDF', upload_to='devis/', blank=True, null=True)
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Devis'
        verbose_name_plural = 'Devis'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.reference} — {self.client}"

    def save(self, *args, **kwargs):
        if not self.reference:
            with transaction.atomic():
                # select_for_update() verrouille les lignes : pas de doublon en concurrence
                year = timezone.now().year
                count = Devis.objects.select_for_update().filter(
                    created_at__year=year
                ).count() + 1
                self.reference = f"DEV-{year}-{count:04d}"
        super().save(*args, **kwargs)

    @property
    def amount_excl(self):
        return sum(l.total_excl for l in self.lignes.all()) or Decimal('0.00')

    @property
    def total_vat(self):
        return sum(l.vat_amount for l in self.lignes.all()) or Decimal('0.00')

    @property
    def amount_incl(self):
        return self.amount_excl + self.total_vat


class DevisLigne(models.Model):
    devis           = models.ForeignKey(Devis, on_delete=models.CASCADE, related_name='lignes')
    description     = models.CharField('Description', max_length=300)
    quantity        = models.DecimalField('Quantité', max_digits=8, decimal_places=2, default=1)
    unit_price_excl = models.DecimalField('Prix unitaire HTVA', max_digits=10, decimal_places=2)
    vat_rate        = models.DecimalField('TVA %', max_digits=5, decimal_places=2, default=Decimal('21.00'))
    order           = models.PositiveSmallIntegerField('Ordre', default=0)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return self.description

    @property
    def total_excl(self):
        return (self.quantity * self.unit_price_excl).quantize(Decimal('0.01'))

    @property
    def vat_amount(self):
        return (self.total_excl * self.vat_rate / 100).quantize(Decimal('0.01'))

    @property
    def total_incl(self):
        return (self.total_excl + self.vat_amount).quantize(Decimal('0.01'))


# ─── Facture ──────────────────────────────────────────────────────────────────

class Facture(models.Model):
    STATUS_PENDING   = 'pending'
    STATUS_PAID      = 'paid'
    STATUS_OVERDUE   = 'overdue'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_PENDING,   'En attente'),
        (STATUS_PAID,      'Payée'),
        (STATUS_OVERDUE,   'En retard'),
        (STATUS_CANCELLED, 'Annulée'),
    ]

    client      = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='factures', verbose_name='Client')
    devis       = models.ForeignKey(Devis, on_delete=models.SET_NULL, null=True, blank=True, related_name='factures', verbose_name='Devis lié')
    reference   = models.CharField('Référence', max_length=20, unique=True, blank=True)
    title       = models.CharField('Titre', max_length=200)
    status      = models.CharField('Statut', max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    due_date    = models.DateField('Échéance')
    paid_at     = models.DateTimeField('Payée le', null=True, blank=True)
    pdf_file    = models.FileField('PDF', upload_to='factures/', blank=True, null=True)
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Facture'
        verbose_name_plural = 'Factures'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.reference} — {self.client}"

    def save(self, *args, **kwargs):
        if not self.reference:
            with transaction.atomic():
                year = timezone.now().year
                count = Facture.objects.select_for_update().filter(
                    created_at__year=year
                ).count() + 1
                self.reference = f"FAC-{year}-{count:04d}"
        super().save(*args, **kwargs)

    @property
    def amount_excl(self):
        return sum(l.total_excl for l in self.lignes.all()) or Decimal('0.00')

    @property
    def total_vat(self):
        return sum(l.vat_amount for l in self.lignes.all()) or Decimal('0.00')

    @property
    def amount_incl(self):
        return self.amount_excl + self.total_vat

    @property
    def is_overdue(self):
        if self.status == self.STATUS_OVERDUE:
            return True
        return self.status == self.STATUS_PENDING and self.due_date < timezone.now().date()

    def mark_as_paid(self):
        """Marque la facture comme payée et crée une transaction de crédit.
        Idempotente : un deuxième appel sur une facture déjà payée est ignoré.
        """
        if self.status == self.STATUS_PAID:
            return
        self.status = self.STATUS_PAID
        self.paid_at = timezone.now()
        self.save(update_fields=['status', 'paid_at', 'updated_at'])
        CompteTransaction.add(
            client=self.client,
            label=f"Paiement {self.reference}",
            amount=self.amount_incl,
            related_invoice=self,
        )


class FactureLigne(models.Model):
    facture         = models.ForeignKey(Facture, on_delete=models.CASCADE, related_name='lignes')
    description     = models.CharField('Description', max_length=300)
    quantity        = models.DecimalField('Quantité', max_digits=8, decimal_places=2, default=1)
    unit_price_excl = models.DecimalField('Prix unitaire HTVA', max_digits=10, decimal_places=2)
    vat_rate        = models.DecimalField('TVA %', max_digits=5, decimal_places=2, default=Decimal('21.00'))
    order           = models.PositiveSmallIntegerField('Ordre', default=0)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return self.description

    @property
    def total_excl(self):
        return (self.quantity * self.unit_price_excl).quantize(Decimal('0.01'))

    @property
    def vat_amount(self):
        return (self.total_excl * self.vat_rate / 100).quantize(Decimal('0.01'))

    @property
    def total_incl(self):
        return (self.total_excl + self.vat_amount).quantize(Decimal('0.01'))


# ─── Maintenance ──────────────────────────────────────────────────────────────

class Maintenance(models.Model):
    STATUS_SCHEDULED   = 'scheduled'
    STATUS_COMPLETED   = 'completed'
    STATUS_CANCELLED   = 'cancelled'
    STATUS_RESCHEDULED = 'rescheduled'
    STATUS_CHOICES = [
        (STATUS_SCHEDULED,   'Planifiée'),
        (STATUS_COMPLETED,   'Effectuée'),
        (STATUS_CANCELLED,   'Annulée'),
        (STATUS_RESCHEDULED, 'Reportée'),
    ]

    client       = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='maintenance', verbose_name='Client')
    title        = models.CharField('Titre', max_length=200)
    description  = models.TextField('Description', blank=True)
    scheduled_at = models.DateTimeField('Planifiée le')
    completed_at = models.DateTimeField('Effectuée le', null=True, blank=True)
    status       = models.CharField('Statut', max_length=20, choices=STATUS_CHOICES, default=STATUS_SCHEDULED)
    technician   = models.CharField('Technicien', max_length=100, blank=True)
    notes        = models.TextField('Rapport d\'intervention', blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Maintenance'
        verbose_name_plural = 'Maintenances'
        ordering = ['scheduled_at']

    def __str__(self):
        return f"{self.title} — {self.client} ({self.scheduled_at.strftime('%d/%m/%Y')})"


# ─── Prestation ───────────────────────────────────────────────────────────────

class Prestation(models.Model):
    STATUS_CHOICES = [
        ('active',    'Active'),
        ('paused',    'Suspendue'),
        ('completed', 'Terminée'),
        ('cancelled', 'Annulée'),
    ]

    client       = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='prestations', verbose_name='Client')
    name         = models.CharField('Nom', max_length=200)
    description  = models.TextField('Description', blank=True)
    start_date   = models.DateField('Début')
    end_date     = models.DateField('Fin', null=True, blank=True)
    status       = models.CharField('Statut', max_length=20, choices=STATUS_CHOICES, default='active')
    annual_price = models.DecimalField('Prix annuel', max_digits=10, decimal_places=2, null=True, blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Prestation'
        verbose_name_plural = 'Prestations'
        ordering = ['-start_date']

    def __str__(self):
        return f"{self.name} — {self.client}"


# ─── Compte courant ───────────────────────────────────────────────────────────

class CompteTransaction(models.Model):
    client          = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='transactions', verbose_name='Client')
    label           = models.CharField('Libellé', max_length=200)
    amount          = models.DecimalField('Montant', max_digits=10, decimal_places=2,
                                          help_text='Positif = crédit, négatif = débit')
    balance_after   = models.DecimalField('Solde après', max_digits=10, decimal_places=2)
    related_invoice = models.ForeignKey(Facture, on_delete=models.SET_NULL, null=True, blank=True,
                                        verbose_name='Facture liée')
    date            = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Transaction'
        verbose_name_plural = 'Transactions'
        ordering = ['-date']

    def __str__(self):
        sign = '+' if self.amount >= 0 else ''
        return f"{self.label} ({sign}{self.amount} €) — {self.client}"

    @classmethod
    def add(cls, client, label, amount, related_invoice=None):
        """Crée une transaction en calculant le nouveau solde automatiquement."""
        previous = cls.objects.filter(client=client).order_by('-date').first()
        balance_before = previous.balance_after if previous else Decimal('0.00')
        return cls.objects.create(
            client=client,
            label=label,
            amount=amount,
            balance_after=(balance_before + amount).quantize(Decimal('0.01')),
            related_invoice=related_invoice,
        )
