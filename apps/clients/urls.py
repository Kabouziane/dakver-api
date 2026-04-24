from rest_framework.routers import DefaultRouter
from django.urls import path
from .views import (
    ClientViewSet, DevisViewSet, FactureViewSet,
    MaintenanceViewSet, PrestationViewSet, CompteViewSet, DashboardView
)

router = DefaultRouter()
router.register('profile',     ClientViewSet,     basename='profile')
router.register('devis',       DevisViewSet,      basename='devis')
router.register('factures',    FactureViewSet,    basename='factures')
router.register('maintenance', MaintenanceViewSet, basename='maintenance')
router.register('prestations', PrestationViewSet, basename='prestations')
router.register('compte',      CompteViewSet,     basename='compte')
router.register('dashboard',   DashboardView,     basename='dashboard')

urlpatterns = router.urls
