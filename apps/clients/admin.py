import io
import zipfile
from django.contrib import admin
from django.conf import settings
from django.core.files.base import ContentFile
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from weasyprint import HTML

from .models import (
    Client, Devis, DevisLigne, Facture, FactureLigne,
    Maintenance, Prestation, CompteTransaction
)


# ─── Helpers PDF ─────────────────────────────────────────────────────────────

def _pdf_context(obj):
    """Contexte commun injecté dans tous les templates PDF."""
    return {
        'obj': obj,
        'lignes': obj.lignes.all(),
        'company': settings.COMPANY,
        'generated_at': timezone.now(),
    }


def _render_pdf(template_name, context):
    """Rendu HTML → PDF via WeasyPrint."""
    html_string = render_to_string(template_name, context)
    return HTML(string=html_string, base_url=str(settings.BASE_DIR)).write_pdf()


def _pdf_response(pdf_bytes, filename):
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def _zip_pdfs(items, template_name, filename_fn):
    """Génère un ZIP contenant les PDFs de plusieurs objets."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for obj in items:
            pdf = _render_pdf(template_name, _pdf_context(obj))
            zf.writestr(filename_fn(obj), pdf)
    buffer.seek(0)
    response = HttpResponse(buffer.read(), content_type='application/zip')
    response['Content-Disposition'] = 'attachment; filename="documents.zip"'
    return response


# ─── Inlines ─────────────────────────────────────────────────────────────────

class DevisLigneInline(admin.TabularInline):
    model = DevisLigne
    extra = 1
    fields = ['order', 'description', 'quantity', 'unit_price_excl', 'vat_rate']
    ordering = ['order']


class FactureLigneInline(admin.TabularInline):
    model = FactureLigne
    extra = 1
    fields = ['order', 'description', 'quantity', 'unit_price_excl', 'vat_rate']
    ordering = ['order']


# ─── Client ──────────────────────────────────────────────────────────────────

@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display   = ['__str__', 'phone', 'balance_display', 'unpaid_display', 'created_at']
    search_fields  = ['user__email', 'user__first_name', 'user__last_name', 'company_name', 'phone']
    readonly_fields = ['created_at', 'balance_display', 'unpaid_display']

    def balance_display(self, obj):
        b = obj.balance
        color = '#16a34a' if b >= 0 else '#dc2626'
        return format_html('<strong style="color:{}">{} €</strong>', color, b)
    balance_display.short_description = 'Solde'

    def unpaid_display(self, obj):
        a = obj.unpaid_amount
        color = '#dc2626' if a > 0 else '#16a34a'
        return format_html('<strong style="color:{}">{} €</strong>', color, a)
    unpaid_display.short_description = 'Impayé'


# ─── Devis ───────────────────────────────────────────────────────────────────

@admin.register(Devis)
class DevisAdmin(admin.ModelAdmin):
    list_display   = ['reference', 'client', 'title', 'amount_incl_display',
                      'status_badge', 'valid_until', 'pdf_button', 'created_at']
    list_filter    = ['status', 'created_at']
    search_fields  = ['reference', 'title', 'client__user__email',
                      'client__user__first_name', 'client__user__last_name']
    readonly_fields = ['reference', 'amount_excl_display', 'total_vat_display',
                       'amount_incl_display', 'pdf_button', 'created_at', 'updated_at']
    inlines        = [DevisLigneInline]
    actions        = ['action_generate_pdf']
    fieldsets = [
        (None, {'fields': ['client', 'reference', 'title', 'description', 'status', 'valid_until']}),
        ('Totaux', {'fields': ['amount_excl_display', 'total_vat_display', 'amount_incl_display'], 'classes': ['collapse']}),
        ('PDF', {'fields': ['pdf_file', 'pdf_button']}),
        ('Métadonnées', {'fields': ['created_at', 'updated_at'], 'classes': ['collapse']}),
    ]

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path('<int:pk>/pdf/', self.admin_site.admin_view(self.download_pdf), name='clients_devis_pdf'),
        ]
        return custom + urls

    # ── PDF download view ──
    def download_pdf(self, request, pk):
        devis = Devis.objects.prefetch_related('lignes').get(pk=pk)
        pdf_bytes = _render_pdf('pdf/devis.html', _pdf_context(devis))
        devis.pdf_file.save(f"{devis.reference}.pdf", ContentFile(pdf_bytes), save=True)
        return _pdf_response(pdf_bytes, f"{devis.reference}.pdf")

    # ── Admin action (liste) ──
    @admin.action(description='📄 Générer PDF(s)')
    def action_generate_pdf(self, request, queryset):
        qs = queryset.prefetch_related('lignes')
        if qs.count() == 1:
            return self.download_pdf(request, qs.first().pk)
        return _zip_pdfs(qs, 'pdf/devis.html', lambda d: f"{d.reference}.pdf")

    # ── Display helpers ──
    def amount_excl_display(self, obj):
        return f"{obj.amount_excl} €"
    amount_excl_display.short_description = 'Montant HTVA'

    def total_vat_display(self, obj):
        return f"{obj.total_vat} €"
    total_vat_display.short_description = 'TVA'

    def amount_incl_display(self, obj):
        return format_html('<strong>{} €</strong>', obj.amount_incl)
    amount_incl_display.short_description = 'Montant TVAC'

    def status_badge(self, obj):
        colors = {
            'draft': '#6b7280', 'sent': '#3b82f6', 'accepted': '#16a34a',
            'refused': '#dc2626', 'expired': '#f59e0b',
        }
        c = colors.get(obj.status, '#6b7280')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 10px;border-radius:12px;font-size:12px">{}</span>',
            c, obj.get_status_display()
        )
    status_badge.short_description = 'Statut'

    def pdf_button(self, obj):
        if not obj.pk:
            return '—'
        url = reverse('admin:clients_devis_pdf', args=[obj.pk])
        return format_html(
            '<a href="{}" target="_blank" class="button" style="background:#16a34a;color:#fff;padding:4px 12px;border-radius:6px;text-decoration:none;font-size:13px">📄 Télécharger PDF</a>',
            url
        )
    pdf_button.short_description = 'PDF'


# ─── Facture ─────────────────────────────────────────────────────────────────

@admin.register(Facture)
class FactureAdmin(admin.ModelAdmin):
    list_display   = ['reference', 'client', 'title', 'amount_incl_display',
                      'status_badge', 'due_date', 'pdf_button', 'created_at']
    list_filter    = ['status', 'due_date', 'created_at']
    search_fields  = ['reference', 'title', 'client__user__email',
                      'client__user__first_name', 'client__user__last_name']
    readonly_fields = ['reference', 'amount_excl_display', 'total_vat_display',
                       'amount_incl_display', 'pdf_button', 'paid_at', 'created_at', 'updated_at']
    inlines        = [FactureLigneInline]
    actions        = ['action_generate_pdf', 'action_mark_paid']
    fieldsets = [
        (None, {'fields': ['client', 'devis', 'reference', 'title', 'status', 'due_date', 'paid_at']}),
        ('Totaux', {'fields': ['amount_excl_display', 'total_vat_display', 'amount_incl_display'], 'classes': ['collapse']}),
        ('PDF', {'fields': ['pdf_file', 'pdf_button']}),
        ('Métadonnées', {'fields': ['created_at', 'updated_at'], 'classes': ['collapse']}),
    ]

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path('<int:pk>/pdf/', self.admin_site.admin_view(self.download_pdf), name='clients_facture_pdf'),
            path('<int:pk>/mark-paid/', self.admin_site.admin_view(self.mark_paid_view), name='clients_facture_mark_paid'),
        ]
        return custom + urls

    def download_pdf(self, request, pk):
        facture = Facture.objects.prefetch_related('lignes').get(pk=pk)
        pdf_bytes = _render_pdf('pdf/facture.html', _pdf_context(facture))
        facture.pdf_file.save(f"{facture.reference}.pdf", ContentFile(pdf_bytes), save=True)
        return _pdf_response(pdf_bytes, f"{facture.reference}.pdf")

    def mark_paid_view(self, request, pk):
        from django.shortcuts import redirect
        facture = Facture.objects.get(pk=pk)
        facture.mark_as_paid()
        self.message_user(request, f"{facture.reference} marquée comme payée.")
        return redirect(reverse('admin:clients_facture_changelist'))

    @admin.action(description='📄 Générer PDF(s)')
    def action_generate_pdf(self, request, queryset):
        qs = queryset.prefetch_related('lignes')
        if qs.count() == 1:
            return self.download_pdf(request, qs.first().pk)
        return _zip_pdfs(qs, 'pdf/facture.html', lambda f: f"{f.reference}.pdf")

    @admin.action(description='✅ Marquer comme payée(s)')
    def action_mark_paid(self, request, queryset):
        for f in queryset.filter(status__in=['pending', 'overdue']):
            f.mark_as_paid()
        self.message_user(request, f"{queryset.count()} facture(s) marquée(s) comme payée(s).")

    def amount_excl_display(self, obj):
        return f"{obj.amount_excl} €"
    amount_excl_display.short_description = 'Montant HTVA'

    def total_vat_display(self, obj):
        return f"{obj.total_vat} €"
    total_vat_display.short_description = 'TVA'

    def amount_incl_display(self, obj):
        return format_html('<strong>{} €</strong>', obj.amount_incl)
    amount_incl_display.short_description = 'Montant TVAC'

    def status_badge(self, obj):
        colors = {
            'pending': '#f59e0b', 'paid': '#16a34a',
            'overdue': '#dc2626', 'cancelled': '#6b7280',
        }
        c = colors.get(obj.status, '#6b7280')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 10px;border-radius:12px;font-size:12px">{}</span>',
            c, obj.get_status_display()
        )
    status_badge.short_description = 'Statut'

    def pdf_button(self, obj):
        if not obj.pk:
            return '—'
        pdf_url = reverse('admin:clients_facture_pdf', args=[obj.pk])
        paid_url = reverse('admin:clients_facture_mark_paid', args=[obj.pk])
        buttons = format_html(
            '<a href="{}" target="_blank" style="background:#16a34a;color:#fff;padding:4px 10px;border-radius:6px;text-decoration:none;font-size:13px;margin-right:6px">📄 PDF</a>',
            pdf_url
        )
        if obj.status in ['pending', 'overdue']:
            buttons += format_html(
                '<a href="{}" style="background:#3b82f6;color:#fff;padding:4px 10px;border-radius:6px;text-decoration:none;font-size:13px">✅ Marquer payée</a>',
                paid_url
            )
        return buttons
    pdf_button.short_description = 'Actions'


# ─── Maintenance ─────────────────────────────────────────────────────────────

@admin.register(Maintenance)
class MaintenanceAdmin(admin.ModelAdmin):
    list_display  = ['title', 'client', 'scheduled_at', 'status', 'technician']
    list_filter   = ['status', 'scheduled_at']
    search_fields = ['title', 'client__user__email', 'technician']
    readonly_fields = ['created_at']


# ─── Prestation ──────────────────────────────────────────────────────────────

@admin.register(Prestation)
class PrestationAdmin(admin.ModelAdmin):
    list_display  = ['name', 'client', 'status', 'start_date', 'end_date', 'annual_price']
    list_filter   = ['status']
    search_fields = ['name', 'client__user__email']
    readonly_fields = ['created_at']


# ─── Compte courant ──────────────────────────────────────────────────────────

@admin.register(CompteTransaction)
class CompteTransactionAdmin(admin.ModelAdmin):
    list_display  = ['label', 'client', 'amount_display', 'balance_after', 'related_invoice', 'date']
    list_filter   = ['date']
    search_fields = ['label', 'client__user__email']
    readonly_fields = ['balance_after', 'date']

    def has_change_permission(self, request, obj=None):
        return False  # Les transactions ne peuvent pas être modifiées

    def amount_display(self, obj):
        color = '#16a34a' if obj.amount >= 0 else '#dc2626'
        sign = '+' if obj.amount >= 0 else ''
        return format_html('<strong style="color:{}">{}{} €</strong>', color, sign, obj.amount)
    amount_display.short_description = 'Montant'
