# ==========================================
# CORE/MODELS.PY
# Zakaz — Plataforma de Agendamento
# Versão: 0.8.1 — Inclusão do Status de Triagem Fiscal
# ==========================================

import random
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.contrib.auth.models import User
from datetime import timedelta

# ==========================================
# CONSTANTES GLOBAIS
# ==========================================

SHADOW_BUFFER           = 15   # minutos de buffer entre agendamentos
PRAZO_VINCULO_NFE_HORAS = 24   # horas antes da descarga para vincular NF-e


class EmpresaOperadora(models.Model):
    cnpj          = models.CharField('CNPJ', max_length=14, unique=True)
    razao_social  = models.CharField('Razão Social', max_length=200)
    nome_fantasia = models.CharField('Nome Fantasia', max_length=200, blank=True)
    ativa         = models.BooleanField('Ativa', default=True)

    def __str__(self):
        return f"{self.razao_social} ({self.cnpj})"

    class Meta:
        verbose_name        = 'Empresa Operadora'
        verbose_name_plural = 'Empresas Operadoras'


class Doca(models.Model):
    TIPOS_VEICULO = [
        ('VUC', 'VUC'),
        ('TOC', 'Toco'),
        ('TRU', 'Truck'),
        ('CAR', 'Carreta'),
        ('BIT', 'Bitrem'),
    ]

    codigo                 = models.CharField('Código', max_length=10, unique=True)
    tipo_maximo            = models.CharField('Veículo Máximo', max_length=3, choices=TIPOS_VEICULO)
    temperatura_controlada = models.BooleanField('Câmara Fria?', default=False)
    ativa                  = models.BooleanField('Ativa', default=True)

    def __str__(self):
        return f"{self.codigo} ({self.tipo_maximo})"

    class Meta:
        verbose_name        = 'Doca'
        verbose_name_plural = 'Docas'


class Fornecedor(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='fornecedor_perfil',
        verbose_name='Usuário de Acesso'
    )
    cnpj               = models.CharField('CNPJ', max_length=14, unique=True)
    razao_social       = models.CharField('Razão Social', max_length=200)
    email_contato      = models.EmailField('E-mail de Contato', blank=True)
    score_pontualidade = models.FloatField('Score (0-100)', default=100.0)
    bloqueado          = models.BooleanField('Bloqueio Fiscal', default=False)
    motivo_bloqueio    = models.TextField('Motivo do Bloqueio', blank=True)
    permite_multi_doca = models.BooleanField('Permite Multi-Doca?', default=False)
    agenda_fixa        = models.BooleanField('Grade Fixa?', default=False)
    cor_marca          = models.CharField('Cor da Marca', max_length=7, blank=True, default='')

    def __str__(self):
        return f"{self.razao_social} ({self.cnpj})"

    class Meta:
        verbose_name        = 'Fornecedor'
        verbose_name_plural = 'Fornecedores'


class Agendamento(models.Model):
    STATUS_CHOICES = [
        ('PRE_AGENDADO',      'Pré-agendado'),
        ('AGUARDANDO_FISCAL', 'Pré-entrada Fiscal'), # Triagem manual
        ('CONFIRMADO',        'Confirmado'),
        ('EM_PATIO',          'Em pátio'),
        ('EM_DESCARGA',       'Em descarga'),
        ('FINALIZADO',        'Finalizado'),
        ('CANCELADO',         'Cancelado'),
        ('NO_SHOW',           'No-show'),
    ]

    TIPO_CARGA = [
        ('PAL', 'Paletizada'),
        ('BAT', 'Batida'),
        ('FRA', 'Fracionada'),
    ]

    TIPO_OPERACAO_CHOICES = [
        ('DIRETA', 'Direta Distribuidora'),
        ('CROSS',  'Crossdocking'),
    ]

    fornecedor = models.ForeignKey(Fornecedor, on_delete=models.PROTECT, null=True, blank=True)
    docas      = models.ManyToManyField(Doca, through='AgendamentoDoca', verbose_name='Docas', blank=True)

    numero_pedido  = models.CharField('Nº Pedido de Compra', max_length=20)
    inicio         = models.DateTimeField('Horário de Início')
    fim_estimado   = models.DateTimeField('Fim Estimado', null=True, blank=True)
    tipo_carga     = models.CharField('Tipo de Carga', max_length=3, choices=TIPO_CARGA, default='PAL')
    qtd_itens      = models.IntegerField('Qtd. Itens/Caixas', default=1)
    tipo_operacao  = models.CharField(
        'Tipo de Operação', max_length=10,
        choices=TIPO_OPERACAO_CHOICES, default='DIRETA'
    )
    status         = models.CharField('Status', max_length=20, choices=STATUS_CHOICES, default='PRE_AGENDADO')
    criado_em     = models.DateTimeField('Criado em', auto_now_add=True)

    chave_nfe        = models.CharField('Chave NF-e', max_length=4500, null=True, blank=True)
    arquivo_xml      = models.FileField('XML da NF-e', upload_to='xmls/%Y/%m/', null=True, blank=True)
    nfe_validada     = models.BooleanField('NF-e Validada?', default=False)
    nfe_vinculada_em = models.DateTimeField('NF-e Vinculada em', null=True, blank=True)

    codigo_descarga      = models.CharField('Código de Descarga', max_length=4, null=True, blank=True)
    horario_chegada_real = models.DateTimeField('Chegada Real', null=True, blank=True)

    horario_entrada_patio   = models.DateTimeField('Entrada no Pátio', null=True, blank=True)
    horario_inicio_descarga = models.DateTimeField('Início da Descarga', null=True, blank=True)
    horario_finalizacao     = models.DateTimeField('Finalização', null=True, blank=True)

    def calcular_duracao(self):
        base, mu = 30, 1
        multiplicadores = {'PAL': 0.80, 'BAT': 1.50, 'FRA': 1.20}
        duracao = (base + (self.qtd_itens * mu)) * multiplicadores.get(self.tipo_carga, 1.0)
        return int(duracao)

    @property
    def status_dinamico(self):
        """
        Retorna dicionário com hierarquia de precedência v0.8.1.
        """
        # 1. Overrides explícitos (Terminais e Triagem Fiscal)
        if self.status == 'CANCELADO':
            return {'code': 'ATR', 'label': 'Cancelado'}
        if self.status == 'NO_SHOW':
            return {'code': 'ATR', 'label': 'No-show'}
        if self.status == 'AGUARDANDO_FISCAL':
            return {'code': 'FIS', 'label': 'Pré-entrada Fiscal'}
        
        # 2. Dedução por timestamps operacional
        if self.horario_finalizacao:
            return {'code': 'FIN', 'label': 'Finalizado'}
        if self.horario_inicio_descarga:
            return {'code': 'DES', 'label': 'Em descarga'}
        if self.horario_entrada_patio:
            return {'code': 'PAT', 'label': 'Em pátio'}
        if self.nfe_validada:
            return {'code': 'CON', 'label': 'Confirmado'}
        if self.prazo_expirado():
            return {'code': 'ATR', 'label': 'Atrasado (NF-e)'}
            
        return {'code': 'PRE', 'label': 'Pré-agendado'}

    def get_status_display(self):
        return self.status_dinamico['label']

    def prazo_vinculo_nfe(self):
        return self.inicio - timedelta(hours=PRAZO_VINCULO_NFE_HORAS) if self.inicio else None

    def prazo_expirado(self):
        prazo = self.prazo_vinculo_nfe()
        return not self.nfe_validada and timezone.now() > prazo if prazo else False

    def verificar_conflito(self):
        duracao = self.calcular_duracao()
        novo_inicio = self.inicio
        novo_fim = self.inicio + timedelta(minutes=duracao + SHADOW_BUFFER)
        for doca in self.docas.all():
            conflitos = Agendamento.objects.filter(
                docas=doca,
                status__in=['PRE_AGENDADO', 'CONFIRMADO', 'EM_PATIO', 'EM_DESCARGA'],
            ).exclude(pk=self.pk)
            for ag in conflitos:
                if not ag.fim_estimado: continue
                fim_com_buffer = ag.fim_estimado + timedelta(minutes=SHADOW_BUFFER)
                if novo_inicio < fim_com_buffer and novo_fim > ag.inicio:
                    raise ValidationError(f"Conflito na doca {doca.codigo} com agendamento #{ag.pk}.")

    def vincular_nfe(self, chave_nfe, arquivo_xml=None):
        from .integrations import consultar_nota_winthor
        if self.prazo_expirado(): raise ValidationError("Prazo expirado.")
        
        # Se falhar no Winthor, não levanta erro, apenas muda status para análise
        if not consultar_nota_winthor(chave_nfe):
            self.status = 'AGUARDANDO_FISCAL'
            self.nfe_validada = False
        else:
            self.nfe_validada = True
            self.nfe_vinculada_em = timezone.now()
        
        self.chave_nfe = chave_nfe
        if arquivo_xml: self.arquivo_xml = arquivo_xml
        self.save()

    def fazer_checkin(self, codigo_informado):
        if self.status_dinamico['code'] != 'CON': raise ValidationError("Não confirmado.")
        if str(codigo_informado).strip() != self.codigo_descarga: raise ValidationError("Código inválido.")
        agora = timezone.now()
        self.horario_entrada_patio = self.horario_chegada_real = agora
        self.save()

    def clean(self):
        if self.fornecedor and self.fornecedor.bloqueado: raise ValidationError("Fornecedor bloqueado.")
        if self.inicio:
            fim = self.inicio + timedelta(minutes=self.calcular_duracao())
            if fim.hour >= 18: raise ValidationError("Ultrapassa 18h.")
        if self.pk: self.verificar_conflito()

    def save(self, *args, **kwargs):
        sd = self.status_dinamico['code']
        mapa_status = {
            'PRE': 'PRE_AGENDADO', 
            'FIS': 'AGUARDANDO_FISCAL', 
            'CON': 'CONFIRMADO', 
            'PAT': 'EM_PATIO', 
            'DES': 'EM_DESCARGA', 
            'FIN': 'FINALIZADO'
        }
        if sd in mapa_status: self.status = mapa_status[sd]

        if self.inicio:
            self.fim_estimado = self.inicio + timedelta(minutes=self.calcular_duracao())
        if self.status == 'CONFIRMADO' and not self.codigo_descarga:
            self.codigo_descarga = str(random.randint(1000, 9999))
        super().save(*args, **kwargs)

    def __str__(self):
        if self.chave_nfe:
            ultima = self.chave_nfe.split(',')[-1].strip()[-6:]
        else:
            ultima = 'sem NF-e'
        return f"PO:{self.numero_pedido} | {self.inicio:%d/%m %H:%M} | {self.status_dinamico['label']} | {ultima}"

    class Meta:
        ordering, verbose_name, verbose_name_plural = ['inicio'], 'Agendamento', 'Agendamentos'


class NFeArquivo(models.Model):
    TIPO_ARQUIVO_CHOICES = [('XML', 'XML'), ('PDF', 'PDF')]

    agendamento  = models.ForeignKey(
        Agendamento, on_delete=models.CASCADE, related_name='nfe_arquivos'
    )
    tipo_arquivo = models.CharField('Tipo', max_length=3, choices=TIPO_ARQUIVO_CHOICES, default='XML')
    chave        = models.CharField('Chave NF-e', max_length=44, blank=True, default='')
    arquivo      = models.FileField('Arquivo', upload_to='xmls/%Y/%m/')
    aprovado     = models.BooleanField('Aprovado', null=True, default=None)  # None=pendente
    criado_em    = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        if self.tipo_arquivo == 'PDF':
            return f"PDF — Ag.#{self.agendamento_id}"
        return f"{self.chave[-6:] if self.chave else '?'} — Ag.#{self.agendamento_id}"

    class Meta:
        verbose_name        = 'Arquivo NF-e'
        verbose_name_plural = 'Arquivos NF-e'
        ordering            = ['criado_em']


class AgendamentoDoca(models.Model):
    agendamento = models.ForeignKey(Agendamento, on_delete=models.CASCADE)
    doca        = models.ForeignKey(Doca, on_delete=models.PROTECT)
    class Meta: unique_together = ('agendamento', 'doca')


class LogAgendamento(models.Model):
    agendamento = models.ForeignKey(Agendamento, on_delete=models.CASCADE, related_name='logs')
    status_anterior = models.CharField(max_length=50, null=True, blank=True)
    status_novo     = models.CharField(max_length=50)
    data            = models.DateTimeField(auto_now_add=True)
    usuario         = models.CharField(max_length=100, null=True, blank=True)


# ==========================================
# CLIENTE FINAL E VÍNCULO DE PEDIDO
# ==========================================

class Cliente(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='cliente',
        verbose_name='Usuário de Acesso'
    )
    razao_social  = models.CharField('Razão Social', max_length=200)
    cnpj          = models.CharField('CNPJ', max_length=14, blank=True)
    email_contato = models.EmailField('E-mail de Contato', blank=True)
    ativo         = models.BooleanField('Ativo', default=True)
    criado_em     = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'Cliente Final'
        verbose_name_plural = 'Clientes Finais'
        ordering            = ['razao_social']

    def __str__(self):
        return self.razao_social


class PedidoCliente(models.Model):
    ATENDIMENTO_CHOICES = [
        ('INTEGRAL', 'Integral'),
        ('PARCIAL',  'Parcial'),
    ]

    cliente               = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name='pedidos')
    numero_pedido_cliente = models.CharField('Nº do Pedido do Cliente', max_length=50)
    agendamento           = models.OneToOneField(
        Agendamento, on_delete=models.CASCADE,
        related_name='pedido_cliente', null=True, blank=True
    )
    tipo_atendimento      = models.CharField(
        'Tipo de Atendimento', max_length=10,
        choices=ATENDIMENTO_CHOICES, default='INTEGRAL'
    )
    observacao            = models.TextField('Observação', blank=True)
    criado_em             = models.DateTimeField(auto_now_add=True)
    criado_por            = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True
    )

    class Meta:
        verbose_name        = 'Pedido de Cliente'
        verbose_name_plural = 'Pedidos de Clientes'
        ordering            = ['-criado_em']

    def __str__(self):
        return f"{self.cliente} — Pedido {self.numero_pedido_cliente}"


# ==========================================
# GRADE FIXA DE AGENDAMENTOS
# ==========================================

class SlotFixo(models.Model):
    DIAS_CHOICES = [
        (0, 'Segunda'), (1, 'Terça'), (2, 'Quarta'),
        (3, 'Quinta'),  (4, 'Sexta'),
    ]
    TIPO_CHOICES = [
        ('HEINEKEN', 'Heineken'),
        ('PEPSICO',  'PepsiCo'),
        ('CROSS',    'Crossdocking'),
        ('DIRETA',   'AG Simões'),
    ]

    dia_semana = models.IntegerField('Dia da Semana', choices=DIAS_CHOICES)
    hora       = models.IntegerField('Hora')  # 7..18
    tipo       = models.CharField('Tipo', max_length=10, choices=TIPO_CHOICES)
    ativo      = models.BooleanField('Ativo', default=True)

    class Meta:
        unique_together = ['dia_semana', 'hora']
        ordering        = ['dia_semana', 'hora']
        verbose_name        = 'Slot Fixo'
        verbose_name_plural = 'Slots Fixos'

    def __str__(self):
        dias = dict(self.DIAS_CHOICES)
        return f"{dias.get(self.dia_semana, '?')} {self.hora:02d}:00 — {self.get_tipo_display()}"