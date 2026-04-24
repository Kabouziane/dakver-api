from rest_framework import serializers
from .models import (
    Client, Devis, DevisLigne, Facture, FactureLigne,
    Maintenance, Prestation, CompteTransaction
)


class ClientSerializer(serializers.ModelSerializer):
    email      = serializers.EmailField(source='user.email', read_only=True)
    first_name = serializers.CharField(source='user.first_name')
    last_name  = serializers.CharField(source='user.last_name')
    balance    = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    unpaid_amount = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = Client
        fields = ['id', 'email', 'first_name', 'last_name', 'company_name',
                  'phone', 'address', 'vat_number', 'balance', 'unpaid_amount', 'created_at']
        read_only_fields = ['id', 'email', 'created_at', 'balance', 'unpaid_amount']

    def update(self, instance, validated_data):
        user_data = validated_data.pop('user', {})
        if user_data:
            user = instance.user
            for attr, value in user_data.items():
                setattr(user, attr, value)
            user.save()
        return super().update(instance, validated_data)


class DevisLigneSerializer(serializers.ModelSerializer):
    total_excl = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    vat_amount = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    total_incl = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = DevisLigne
        fields = ['id', 'description', 'quantity', 'unit_price_excl', 'vat_rate',
                  'total_excl', 'vat_amount', 'total_incl', 'order']


class DevisSerializer(serializers.ModelSerializer):
    lignes       = DevisLigneSerializer(many=True, read_only=True)
    amount_excl  = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    total_vat    = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    amount_incl  = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    pdf_url      = serializers.SerializerMethodField()
    status_label = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Devis
        fields = ['id', 'reference', 'title', 'description', 'status', 'status_label',
                  'valid_until', 'amount_excl', 'total_vat', 'amount_incl',
                  'lignes', 'pdf_url', 'created_at', 'updated_at']
        read_only_fields = ['id', 'reference', 'created_at', 'updated_at']

    def get_pdf_url(self, obj):
        if obj.pdf_file:
            request = self.context.get('request')
            return request.build_absolute_uri(obj.pdf_file.url) if request else obj.pdf_file.url
        return None


class FactureLigneSerializer(serializers.ModelSerializer):
    total_excl = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    vat_amount = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    total_incl = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = FactureLigne
        fields = ['id', 'description', 'quantity', 'unit_price_excl', 'vat_rate',
                  'total_excl', 'vat_amount', 'total_incl', 'order']


class FactureSerializer(serializers.ModelSerializer):
    lignes       = FactureLigneSerializer(many=True, read_only=True)
    amount_excl  = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    total_vat    = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    amount_incl  = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    pdf_url      = serializers.SerializerMethodField()
    status_label = serializers.CharField(source='get_status_display', read_only=True)
    is_overdue   = serializers.BooleanField(read_only=True)

    class Meta:
        model = Facture
        fields = ['id', 'reference', 'title', 'status', 'status_label', 'is_overdue',
                  'due_date', 'paid_at', 'amount_excl', 'total_vat', 'amount_incl',
                  'lignes', 'pdf_url', 'created_at', 'updated_at']
        read_only_fields = ['id', 'reference', 'created_at', 'updated_at']

    def get_pdf_url(self, obj):
        if obj.pdf_file:
            request = self.context.get('request')
            return request.build_absolute_uri(obj.pdf_file.url) if request else obj.pdf_file.url
        return None


class FactureSummarySerializer(serializers.Serializer):
    total_paid    = serializers.DecimalField(max_digits=10, decimal_places=2)
    total_pending = serializers.DecimalField(max_digits=10, decimal_places=2)
    total_overdue = serializers.DecimalField(max_digits=10, decimal_places=2)
    balance       = serializers.DecimalField(max_digits=10, decimal_places=2)


class MaintenanceSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Maintenance
        fields = ['id', 'title', 'description', 'scheduled_at', 'completed_at',
                  'status', 'status_label', 'technician', 'notes', 'created_at']
        read_only_fields = ['id', 'created_at']


class PrestationSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Prestation
        fields = ['id', 'name', 'description', 'start_date', 'end_date',
                  'status', 'status_label', 'annual_price', 'created_at']
        read_only_fields = ['id', 'created_at']


class CompteTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompteTransaction
        fields = ['id', 'label', 'amount', 'balance_after', 'date']
        read_only_fields = fields


class DashboardSerializer(serializers.Serializer):
    balance              = serializers.DecimalField(max_digits=10, decimal_places=2)
    unpaid_amount        = serializers.DecimalField(max_digits=10, decimal_places=2)
    next_maintenance     = MaintenanceSerializer(allow_null=True)
    pending_devis_count  = serializers.IntegerField()
    active_services      = PrestationSerializer(many=True)
    recent_invoices      = FactureSerializer(many=True)
