from decimal import Decimal
from django.utils import timezone
from rest_framework import viewsets, mixins, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    Client, Devis, Facture, Maintenance, Prestation, CompteTransaction
)
from .serializers import (
    ClientSerializer, DevisSerializer, FactureSerializer, FactureSummarySerializer,
    MaintenanceSerializer, PrestationSerializer, CompteTransactionSerializer,
    DashboardSerializer
)
from .vies import check_vat


class ClientViewSet(mixins.RetrieveModelMixin,
                    mixins.UpdateModelMixin,
                    viewsets.GenericViewSet):
    """Profil du client connecté — lecture et mise à jour uniquement."""
    serializer_class = ClientSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user.client


class DevisViewSet(mixins.ListModelMixin,
                   mixins.RetrieveModelMixin,
                   viewsets.GenericViewSet):
    """Devis du client connecté — lecture seule côté client."""
    serializer_class = DevisSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Isolation stricte : un client ne voit que ses propres devis
        return Devis.objects.filter(
            client=self.request.user.client
        ).prefetch_related('lignes')


class FactureViewSet(mixins.ListModelMixin,
                     mixins.RetrieveModelMixin,
                     viewsets.GenericViewSet):
    """Factures du client connecté."""
    serializer_class = FactureSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Facture.objects.filter(
            client=self.request.user.client
        ).prefetch_related('lignes')

    @action(detail=False, methods=['get'], url_path='summary')
    def summary(self, request):
        client = request.user.client
        # amount_incl est une @property calculée en Python — on ne peut pas
        # faire Sum('amount_incl') en ORM. On itère avec prefetch pour éviter N+1.
        factures = client.factures.prefetch_related('lignes')
        data = {
            'total_paid':    sum(f.amount_incl for f in factures if f.status == 'paid')    or Decimal('0.00'),
            'total_pending': sum(f.amount_incl for f in factures if f.status == 'pending') or Decimal('0.00'),
            'total_overdue': sum(f.amount_incl for f in factures if f.status == 'overdue') or Decimal('0.00'),
            'balance': client.balance,
        }
        return Response(FactureSummarySerializer(data).data)


class MaintenanceViewSet(mixins.ListModelMixin,
                         mixins.RetrieveModelMixin,
                         viewsets.GenericViewSet):
    """Planning de maintenance du client connecté."""
    serializer_class = MaintenanceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Maintenance.objects.filter(client=self.request.user.client)


class PrestationViewSet(mixins.ListModelMixin,
                        mixins.RetrieveModelMixin,
                        viewsets.GenericViewSet):
    """Prestations en cours et historique."""
    serializer_class = PrestationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Prestation.objects.filter(client=self.request.user.client)


class CompteViewSet(mixins.ListModelMixin,
                    viewsets.GenericViewSet):
    """Historique du compte courant."""
    serializer_class = CompteTransactionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return CompteTransaction.objects.filter(client=self.request.user.client)


class VatValidateView(APIView):
    """
    GET /api/v1/vat/validate/?number=BE0123456789
    Valide un numéro de TVA via l'API VIES (Commission Européenne).
    Retourne les données entreprise si disponibles.
    Authentification requise — évite l'abus de l'endpoint comme proxy public.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        number = request.query_params.get('number', '').strip()
        if not number:
            return Response(
                {'valid': False, 'error': 'Paramètre number requis.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = check_vat(number)

        payload = {
            'valid':       result.valid,
            'name':        result.name,
            'address':     result.address,
            'unavailable': result.unavailable,
            'error':       result.error,
        }

        if result.unavailable:
            # VIES down : on répond 503 pour que le client puisse l'ignorer gracieusement
            return Response(payload, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        return Response(payload)


class DashboardView(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Résumé global du tableau de bord."""
    permission_classes = [IsAuthenticated]

    def list(self, request):
        client = request.user.client
        now = timezone.now()

        next_maintenance = Maintenance.objects.filter(
            client=client,
            status='scheduled',
            scheduled_at__gte=now,
        ).order_by('scheduled_at').first()

        data = {
            'balance': client.balance,
            'unpaid_amount': client.unpaid_amount,
            'next_maintenance': MaintenanceSerializer(next_maintenance).data if next_maintenance else None,
            'pending_devis_count': client.devis.filter(status__in=['sent', 'draft']).count(),
            'active_services': PrestationSerializer(
                client.prestations.filter(status='active'), many=True
            ).data,
            'recent_invoices': FactureSerializer(
                client.factures.prefetch_related('lignes').order_by('-created_at')[:5],
                many=True,
                context={'request': request},
            ).data,
        }
        return Response(data)
