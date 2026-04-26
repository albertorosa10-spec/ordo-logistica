# ==========================================
# SETUP/URLS.PY
# Ordo Logística — Project URL config
# Versão: 0.6.0
# ==========================================

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # Painel Administrativo Django (Gestão Ordo)
    path('admin/', admin.site.urls),

    # Todas as URLs do app core (inclui home, portal, api, portaria)
    path('', include('core.urls')),

] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)