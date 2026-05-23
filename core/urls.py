# ==========================================
# CORE/URLS.PY
# Zakaz — App core URL config
# Versão: 0.7.0 — Adicionadas rotas /industria/
# e /gestor/ para testes de integração e
# compatibilidade com documentação externa.
# ==========================================

from django.urls import path
from . import views

urlpatterns = [

    # ------------------------------------------
    # PÚBLICO: Home e Portaria
    # ------------------------------------------
    path('',              views.home,                 name='home'),
    path('portaria/',     views.consulta_portaria,    name='consulta'),
    # ------------------------------------------
    # PORTAL DO CLIENTE
    # ------------------------------------------
    path('cliente/login/',      views.cliente_login,      name='cliente_login'),
    path('cliente/dashboard/',  views.cliente_dashboard,  name='cliente_dashboard'),
    path('cliente/pedido/<int:pk>/', views.cliente_detalhe_pedido,
         name='cliente_detalhe_pedido'),
    path('cliente/logout/',     views.logout_view,        name='cliente_logout'),

    # ------------------------------------------
    # AUTH: Login e Logout (rotas canônicas)
    # ------------------------------------------
    path('portal/login/',  views.login_industria, name='login_industria'),
    path('portal/logout/', views.logout_view,      name='logout'),
    path('logout/',        views.logout_view),
    path('staff/login/',   views.staff_login,      name='staff_login'),

    # ------------------------------------------
    # ONBOARDING: Cadastro
    # ------------------------------------------
    path('cadastro/', views.cadastro_industria, name='cadastro_industria'),

    # ------------------------------------------
    # PORTAL DA INDÚSTRIA — rotas canônicas
    # ------------------------------------------
    path('portal/dashboard/',
         views.dashboard_industria, name='dashboard_industria'),
    path('portal/agendamento/novo/',
         views.novo_agendamento,    name='novo_agendamento'),
    path('portal/agendamento/<int:agendamento_id>/nfe/',
         views.upload_nfe,          name='upload_nfe'),

    # ------------------------------------------
    # PORTAL DA INDÚSTRIA — aliases /industria/
    # (documentação externa e testes de integração)
    # ------------------------------------------
    path('industria/login/',
         views.login_industria,         name='industria_login'),
    path('industria/cadastro/',
         views.industria_cadastro,      name='industria_cadastro'),
    path('industria/dashboard/',
         views.dashboard_industria,     name='industria_dashboard'),
    path('industria/agendamento/novo/',
         views.novo_agendamento,        name='industria_novo_agendamento'),
    path('industria/nfe/<int:agendamento_id>/',
         views.upload_nfe,              name='industria_nfe'),

    # ------------------------------------------
    # PORTAL DA INDÚSTRIA — novas páginas
    # ------------------------------------------
    path('industria/agendamento/<int:agendamento_id>/',
         views.detalhe_agendamento,              name='industria_detalhe'),
    path('industria/agendamento/<int:agendamento_id>/cancelar/',
         views.cancelar_agendamento_industria,   name='industria_cancelar'),
    path('industria/perfil/',
         views.perfil_industria,                 name='industria_perfil'),
    path('industria/agendamentos/',
         views.lista_agendamentos_status,        name='industria_lista'),

    # ------------------------------------------
    # GESTÃO ZAKAZ (staff)
    # ------------------------------------------
    path('dashboard/', views.dashboard_logistica, name='dashboard'),
    path('gestor/checkin/<int:agendamento_id>/',
         views.gestor_checkin,          name='gestor_checkin'),
    path('gestor/status/<int:agendamento_id>/',
         views.gestor_status,           name='gestor_status'),
    path('gestor/agendamento/<int:pk>/',
         views.gestor_detalhe,          name='gestor_detalhe'),

    # ------------------------------------------
    # PORTAL FISCAL (staff)
    # ------------------------------------------
    path('fiscal/',
         views.fiscal_dashboard, name='fiscal_dashboard'),
    path('fiscal/agendamento/<int:pk>/',
         views.fiscal_aprovar,   name='fiscal_aprovar'),

    # ------------------------------------------
    # API INTERNA (AJAX)
    # ------------------------------------------
    path('api/cnpj/<str:cnpj>/', views.api_consulta_cnpj, name='api_consulta_cnpj'),
    path('industria/slots/', views.ajax_slots_disponiveis, name='ajax_slots_disponiveis'),
    path('industria/lacunas/', views.ajax_lacunas_dia, name='ajax_lacunas_dia'),
]
