from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

admin.site.site_header = 'ToitureVerte — Administration'
admin.site.site_title = 'ToitureVerte'
admin.site.index_title = 'Espace Administration'

urlpatterns = [
    path('admin/', admin.site.urls),
    # Tout l'auth sous /api/v1/auth/ pour cohérence
    path('api/v1/auth/', include('dj_rest_auth.urls')),
    path('api/v1/auth/register/', include('dj_rest_auth.registration.urls')),
    path('api/v1/auth/social/', include('allauth.socialaccount.urls')),
    # API v1
    path('api/v1/', include('apps.clients.urls')),
    path('api/v1/', include('apps.authentication.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
