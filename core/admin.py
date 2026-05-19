# ==========================================
# CORE/ADMIN.PY
# Zakaz — v0.8.0
# ==========================================

from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html
from datetime import timedelta
from .models import (
    EmpresaOperadora, Doca, Fornecedor,
    Agendamento, AgendamentoDoca, LogAgendamento,
    Cliente, PedidoCliente, SlotFixo,
)

@admin.register(EmpresaOperadora)
class EmpresaOperadoraAdmin(admin.ModelAdmin):
    list_display  = ['razao_social', 'cnpj', 'nome_fantasia', 'ativa']
    list_filter   = ['ativa']
    search_fields = ['razao_social', 'cnpj']

@admin.register(Doca)
class DocaAdmin(admin.ModelAdmin):
    list_display  = ['codigo', 'tipo_maximo', 'temperatura_controlada', 'ativa']
    list_filter   = ['ativa', 'temperatura_controlada']
    search_fields = ['codigo']

@admin.register(Fornecedor)
class FornecedorAdmin(admin.ModelAdmin):
    list_display  = ['razao_social', 'cnpj', 'score_pontualidade', 'permite_multi_doca', 'bloqueado']
    list_filter   = ['bloqueado', 'permite_multi_doca']
    search_fields = ['razao_social', 'cnpj']

class AgendamentoDocaInline(admin.TabularInline):
    model = AgendamentoDoca
    extra = 1

class LogAgendamentoInline(admin.TabularInline):
    model           = LogAgendamento
    extra           = 0
    readonly_fields = ['status_anterior', 'status_novo', 'data', 'usuario']
    can_delete      = False

@admin.register(Agendamento)
class AgendamentoAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'fornecedor', 'numero_pedido',
        'inicio', 'fim_estimado',
        'tipo_carga', 'status_colorido',
        'alerta_prazo_nfe', 'codigo_descarga',
    ]
    # 'status' removido do list_filter pois o campo físico foi deletado ou sincronizado
    list_filter   = ['tipo_carga', 'nfe_validada'] 
    search_fields = ['numero_pedido', 'chave_nfe', 'fornecedor__razao_social']
    readonly_fields = [
        'fim_estimado', 'nfe_validada', 'nfe_vinculada_em',
        'codigo_descarga', 'horario_chegada_real', 'criado_em',
        'horario_entrada_patio', 'horario_inicio_descarga', 'horario_finalizacao',
    ]
    inlines = [AgendamentoDocaInline, LogAgendamentoInline]
    ordering = ['inicio']

    fieldsets = (
        ('Pré-agendamento', {
            'fields': (
                'fornecedor', 'numero_pedido',
                'inicio', 'fim_estimado',
                'tipo_carga', 'qtd_itens',
            )
        }),
        ('NF-e', {
            'fields': (
                'chave_nfe', 'arquivo_xml',
                'nfe_validada', 'nfe_vinculada_em',
            )
        }),
        ('Portaria', {
            'fields': ('codigo_descarga', 'horario_chegada_real',)
        }),
        ('Eventos do Pátio (v0.8)', {
            'fields': (
                'horario_entrada_patio',
                'horario_inicio_descarga',
                'horario_finalizacao',
            ),
        }),
        ('Auditoria', {
            'fields': ('criado_em',),
            'classes': ('collapse',),
        }),
    )

    def status_colorido(self, obj):
        cores = {
            'PRE': '#f39c12',  # Amarelo/Laranja
            'CON': '#3498db',  # Azul
            'PAT': '#e65100',  # Laranja Escuro
            'DES': '#6a1b9a',  # Roxo
            'FIN': '#27ae60',  # Verde
            'ATR': '#e74c3c',  # Vermelho
        }
        labels = {
            'PRE': 'Pré-agendado',
            'CON': 'Confirmado',
            'PAT': 'Em pátio',
            'DES': 'Em descarga',
            'FIN': 'Finalizado',
            'ATR': 'Atrasado (NF-e)',
        }
        
        # Acessa a property status_dinamico que retorna o dicionário com o code
        sd_data = obj.status_dinamico
        code = sd_data['code']
        cor = cores.get(code, '#333333')
        label = labels.get(code, sd_data['label'])
        
        return format_html(
            '<span style="color:{}; font-weight:600">{}</span>',
            cor, label
        )
    status_colorido.short_description = 'Status'

    def alerta_prazo_nfe(self, obj):
        if obj.nfe_validada:
            return format_html('<span style="color:#2e7d32">✔ Vinculada</span>')

        prazo = obj.prazo_vinculo_nfe()
        if not prazo:
            return '—'

        restante = prazo - timezone.now()

        if restante.total_seconds() < 0:
            return format_html(
                '<span style="color:#b71c1c; font-weight:600">✘ Expirado</span>'
            )
        elif restante < timedelta(hours=6):
            horas = int(restante.total_seconds() // 3600)
            mins  = int((restante.total_seconds() % 3600) // 60)
            return format_html(
                '<span style="color:#e65100; font-weight:600">⚠ {}h{}min</span>',
                horas, mins
            )
        else:
            return format_html(
                '<span style="color:#888">Prazo: {}</span>',
                prazo.strftime('%d/%m %H:%M')
            )
    alerta_prazo_nfe.short_description = 'NF-e'

@admin.register(LogAgendamento)
class LogAgendamentoAdmin(admin.ModelAdmin):
    list_display    = ['agendamento', 'status_anterior', 'status_novo', 'data', 'usuario']
    list_filter     = ['status_novo']
    readonly_fields = ['agendamento', 'status_anterior', 'status_novo', 'data', 'usuario']


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display  = ['razao_social', 'cnpj', 'ativo', 'criado_em']
    list_filter   = ['ativo']
    search_fields = ['razao_social', 'cnpj']


@admin.register(SlotFixo)
class SlotFixoAdmin(admin.ModelAdmin):
    list_display  = ['get_dia_display', 'hora', 'tipo', 'ativo']
    list_filter   = ['dia_semana', 'tipo', 'ativo']
    ordering      = ['dia_semana', 'hora']

    def get_dia_display(self, obj):
        return obj.get_dia_semana_display()
    get_dia_display.short_description = 'Dia'


@admin.register(PedidoCliente)
class PedidoClienteAdmin(admin.ModelAdmin):
    list_display  = ['numero_pedido_cliente', 'cliente', 'agendamento', 'tipo_atendimento', 'criado_em', 'criado_por']
    list_filter   = ['tipo_atendimento', 'cliente']
    search_fields = ['numero_pedido_cliente', 'cliente__razao_social']
    readonly_fields = ['criado_em', 'criado_por']