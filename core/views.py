# ==========================================
# CORE/VIEWS.PY
# Zakaz — v0.8.1
# Fluxo: Triagem Fiscal Manual + Bypass Winthor
# ==========================================

import json
import logging
from datetime import timedelta, datetime

logger = logging.getLogger(__name__)

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET

from .models import Agendamento, Fornecedor, EmpresaOperadora, Doca, LogAgendamento, NFeArquivo, Cliente, PedidoCliente, SlotFixo, SHADOW_BUFFER


def _e_staff(user):
    """True se superuser, is_staff, ou membro de algum grupo interno."""
    return user.is_superuser or user.is_staff or user.groups.filter(
        name__in=['gestor_patio', 'analista_fiscal', 'portaria']
    ).exists()


def _tem_acesso(user, grupo):
    """Retorna True para superusuários ou membros do grupo informado."""
    return user.is_superuser or user.groups.filter(name=grupo).exists()
from .forms import (
    AutoCadastroFornecedorForm,
    CadastroFornecedorForm,
    LoginIndustriaForm,
    NovoAgendamentoForm,
    UploadNFeXmlForm,
    VinculoPedidoClienteForm,
)
from .integrations import (
    consultar_cnpj_brasilapi,
    validar_nfe_xml,
    extrair_resumo_nfe,
    consultar_nota_winthor,
)

# ==========================================
# HOME & AUTH
# ==========================================

def home(request):
    """Landing page pública."""
    if request.user.is_authenticated:
        if _tem_acesso(request.user, 'gestor_patio'):
            return redirect('dashboard')
        if _tem_acesso(request.user, 'analista_fiscal'):
            return redirect('fiscal_dashboard')
        if _tem_acesso(request.user, 'portaria'):
            return redirect('consulta')
        return redirect('dashboard_industria')
    return render(request, 'home.html')

def login_industria(request):
    """Login customizado via CNPJ."""
    if request.user.is_authenticated:
        return redirect('dashboard_industria')

    form = LoginIndustriaForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.cleaned_data['user']
        login(request, user)
        
        cnpj = form.cleaned_data['cnpj']
        try:
            fornecedor = Fornecedor.objects.get(cnpj=cnpj)
            if fornecedor.user is None:
                fornecedor.user = user
                fornecedor.save(update_fields=['user'])
        except Fornecedor.DoesNotExist:
            pass

        return redirect(request.GET.get('next', 'dashboard_industria'))

    return render(request, 'login.html', {'form': form})

def logout_view(request):
    if request.method == 'POST':
        is_staff = request.user.is_authenticated and (
            request.user.is_superuser or
            request.user.groups.filter(
                name__in=['gestor_patio', 'analista_fiscal', 'portaria']
            ).exists()
        )
        logout(request)
        return redirect('/staff/login/' if is_staff else 'home')
    return redirect('home')

def _staff_home_url(user, next_url=None):
    """
    Retorna a URL de destino pós-login para usuários staff.
    Prioridade: parâmetro ?next= → dashboard do grupo → home.
    """
    if next_url:
        return next_url
    if user.is_superuser or user.groups.filter(name='gestor_patio').exists():
        return 'dashboard'
    if user.groups.filter(name='analista_fiscal').exists():
        return 'fiscal_dashboard'
    if user.groups.filter(name='portaria').exists():
        return 'consulta'
    return 'dashboard'


def staff_login(request):
    """Login dedicado para colaboradores staff (gestor, fiscal, portaria)."""
    if request.user.is_authenticated:
        return redirect(_staff_home_url(request.user, request.GET.get('next')))

    error = None
    username = ''

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)

        if user is None:
            error = "Usuário ou senha incorretos."
        elif not _e_staff(user):
            error = "Acesso restrito a colaboradores."
        else:
            login(request, user)
            return redirect(_staff_home_url(user, request.GET.get('next')))

    return render(request, 'staff_login.html', {
        'error':    error,
        'username': username,
    })

# ==========================================
# ONBOARDING & API
# ==========================================

def cadastro_industria(request):
    """Portal de Onboarding."""
    if request.user.is_authenticated:
        return redirect('dashboard_industria')

    form = CadastroFornecedorForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        cnpj = form.cleaned_data['cnpj']
        email = form.cleaned_data['email']
        senha = form.cleaned_data['senha']
        
        from django.contrib.auth.models import User
        user = User.objects.create_user(username=cnpj, email=email, password=senha)

        try:
            fornecedor = Fornecedor.objects.get(cnpj=cnpj)
            fornecedor.user = user
            fornecedor.email_contato = email
            fornecedor.save()
        except Fornecedor.DoesNotExist:
            pass

        messages.success(request, f"✅ Cadastro realizado! Use o CNPJ {cnpj} para acessar.")
        return redirect('login_industria')

    return render(request, 'onboarding/cadastro.html', {'form': form})


def industria_cadastro(request):
    """Autocadastro self-service: cria Fornecedor + User e loga automaticamente."""
    if request.user.is_authenticated:
        return redirect('dashboard_industria')

    form = AutoCadastroFornecedorForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        from django.contrib.auth.models import User as AuthUser
        cnpj        = form.cleaned_data['cnpj']
        razao_social = form.cleaned_data['razao_social']
        email       = form.cleaned_data['email']
        senha       = form.cleaned_data['senha']

        user = AuthUser.objects.create_user(username=cnpj, email=email, password=senha)
        Fornecedor.objects.create(
            user=user,
            cnpj=cnpj,
            razao_social=razao_social,
            email_contato=email,
            bloqueado=False,
        )
        login(request, user)
        messages.success(request, f"Bem-vindo(a), {razao_social}! Seu portal está pronto.")
        return redirect('dashboard_industria')

    return render(request, 'industria/cadastro.html', {'form': form})


@require_GET
def api_consulta_cnpj(request, cnpj):
    dados = consultar_cnpj_brasilapi(cnpj)
    if dados:
        return JsonResponse(dados)
    return JsonResponse({'erro': 'CNPJ não encontrado.'}, status=404)


@require_GET
@login_required
def ajax_slots_disponiveis(request):
    """Retorna slots livres para a data e tipo de operação informados."""
    data_str = request.GET.get('data', '')
    tipo_op  = request.GET.get('tipo', 'DIRETA').upper()

    from datetime import datetime as dt_cls
    try:
        data = dt_cls.strptime(data_str, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'slots': [], 'erro': 'Data inválida.'}, status=400)

    dow = data.weekday()
    if dow >= 5:
        return JsonResponse({'slots': []})

    # Tipo de slot válido para o tipo de operação solicitado
    tipo_slot = 'DIRETA' if tipo_op == 'DIRETA' else 'CROSS'

    slots_base = list(
        SlotFixo.objects.filter(dia_semana=dow, tipo=tipo_slot, ativo=True)
        .values_list('hora', flat=True)
    )

    if not slots_base:
        # Sem grade definida: usa regras originais
        if tipo_op == 'DIRETA':
            slots_base = [7, 9, 11, 13, 15]
        else:
            slots_base = [8, 10, 12, 14, 16]

    # Remove horas já ocupadas (compara horas no fuso local)
    _STATUS_OCUPA = ['PRE_AGENDADO', 'AGUARDANDO_FISCAL', 'CONFIRMADO', 'EM_PATIO', 'EM_DESCARGA']
    from datetime import datetime as _dt
    inicio_dia = timezone.make_aware(_dt(data.year, data.month, data.day, 0, 0))
    fim_dia    = inicio_dia + timedelta(days=1)
    ocupadas = {
        timezone.localtime(ag.inicio).hour
        for ag in Agendamento.objects.filter(
            inicio__gte=inicio_dia, inicio__lt=fim_dia,
            tipo_operacao=tipo_op, status__in=_STATUS_OCUPA,
        ).only('inicio')
    }

    disponíveis = sorted(h for h in slots_base if h not in ocupadas)
    return JsonResponse({'slots': [f'{h:02d}:00' for h in disponíveis]})


@require_GET
@login_required
def ajax_lacunas_dia(request):
    """
    Retorna todas as lacunas da grade para a data e tipo solicitados,
    com status (livre/ocupado/meu) — sem expor informações de terceiros.
    """
    data_str = request.GET.get('data', '')
    tipo_op  = request.GET.get('tipo', 'DIRETA').upper()

    from datetime import datetime as dt_cls
    try:
        data = dt_cls.strptime(data_str, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'lacunas': [], 'erro': 'Data inválida.'}, status=400)

    DIAS_NOMES = ['Segunda-feira', 'Terça-feira', 'Quarta-feira',
                  'Quinta-feira', 'Sexta-feira', 'Sábado', 'Domingo']
    dow = data.weekday()
    if dow >= 5:
        return JsonResponse({
            'lacunas': [],
            'dia_semana': DIAS_NOMES[dow],
            'aviso': 'Não há agendamentos aos finais de semana.',
        })

    tipo_slot = 'DIRETA' if tipo_op == 'DIRETA' else 'CROSS'

    horas_base = sorted(
        SlotFixo.objects.filter(dia_semana=dow, tipo=tipo_slot, ativo=True)
        .values_list('hora', flat=True)
    )
    if not horas_base:
        horas_base = [7, 9, 11, 13, 15] if tipo_op == 'DIRETA' else [8, 10, 12, 14, 16]

    # Mapeia agendamentos ativos do dia/tipo por hora local
    _STATUS_OCUPA = ['PRE_AGENDADO', 'AGUARDANDO_FISCAL', 'CONFIRMADO', 'EM_PATIO', 'EM_DESCARGA']
    from datetime import datetime as _dt
    inicio_dia = timezone.make_aware(_dt(data.year, data.month, data.day, 0, 0))
    fim_dia    = inicio_dia + timedelta(days=1)
    ags_do_dia = Agendamento.objects.filter(
        inicio__gte=inicio_dia, inicio__lt=fim_dia,
        tipo_operacao=tipo_op, status__in=_STATUS_OCUPA,
    ).select_related('fornecedor')
    ags_por_hora = {timezone.localtime(ag.inicio).hour: ag for ag in ags_do_dia}

    # Fornecedor logado (para identificar "meu")
    fornecedor_user = Fornecedor.objects.filter(user=request.user).first()
    fornecedor_id = fornecedor_user.id if fornecedor_user else None

    lacunas = []
    for idx, hora in enumerate(horas_base, start=1):
        ag = ags_por_hora.get(hora)
        if ag is None:
            lacunas.append({'numero': idx, 'hora': hora, 'status': 'livre'})
        elif fornecedor_id and ag.fornecedor_id == fornecedor_id:
            lacunas.append({
                'numero': idx, 'hora': hora, 'status': 'meu',
                'po': 'A definir' if ag.numero_pedido == 'CROSS-SEM-PO' else ag.numero_pedido,
                'ag_id': ag.id,
                'status_label': ag.get_status_display(),
            })
        else:
            lacunas.append({'numero': idx, 'hora': hora, 'status': 'ocupado'})

    return JsonResponse({
        'data':       data_str,
        'tipo':       tipo_op,
        'dia_semana': DIAS_NOMES[dow],
        'lacunas':    lacunas,
    })

# ==========================================
# PORTAL DA INDÚSTRIA
# ==========================================

@login_required
def dashboard_industria(request):
    """Painel do Fornecedor logado."""
    fornecedor = get_object_or_404(Fornecedor, user=request.user)
    agora = timezone.now()

    todos = Agendamento.objects.filter(fornecedor=fornecedor)
    agendamentos = todos.exclude(
        status__in=['FINALIZADO', 'CANCELADO', 'NO_SHOW']
    ).order_by('inicio')

    kpis = {
        'pre_agendados': todos.filter(status__in=['PRE_AGENDADO', 'AGUARDANDO_FISCAL']).count(),
        'confirmados':   todos.filter(status='CONFIRMADO').count(),
        'em_patio':      todos.filter(status__in=['EM_PATIO', 'EM_DESCARGA']).count(),
        'finalizados':   todos.filter(status='FINALIZADO').count(),
    }

    alertas_nfe = [
        ag for ag in agendamentos.filter(status='PRE_AGENDADO', nfe_validada=False)
        if (p := ag.prazo_vinculo_nfe()) and (p - agora).total_seconds() < 21600
    ]

    historico = todos.filter(
        status__in=['FINALIZADO', 'CANCELADO', 'NO_SHOW'],
        inicio__gte=agora - timedelta(days=30),
    ).order_by('-inicio')

    return render(request, 'industria/dashboard.html', {
        'fornecedor':  fornecedor,
        'agendamentos': agendamentos,
        'agora':       agora,
        'kpis':        kpis,
        'alertas_nfe': alertas_nfe,
        'historico':   historico,
    })

@login_required
def novo_agendamento(request):
    """Criação de agendamento."""
    fornecedor = get_object_or_404(Fornecedor, user=request.user)
    
    if fornecedor.bloqueado:
        messages.error(request, f"Acesso bloqueado: {fornecedor.motivo_bloqueio}")
        return redirect('dashboard_industria')

    form = NovoAgendamentoForm(request.POST or None, fornecedor=fornecedor)
    if request.method == 'POST' and form.is_valid():
        inicio      = form.cleaned_data['inicio']
        tipo_op     = form.cleaned_data.get('tipo_operacao', 'DIRETA')

        # --- Verificação de conflito por horário × tipo de operação ---
        _STATUS_OCUPA = [
            'PRE_AGENDADO', 'AGUARDANDO_FISCAL',
            'CONFIRMADO', 'EM_PATIO', 'EM_DESCARGA',
        ]
        conflito_qs = Agendamento.objects.filter(
            inicio=inicio,
            tipo_operacao=tipo_op,
            status__in=_STATUS_OCUPA,
        )
        if conflito_qs.exists():
            ag_conf = conflito_qs.first()
            tipo_label = 'Direta' if tipo_op == 'DIRETA' else 'Crossdocking'
            form.add_error(
                None,
                f'Já existe um agendamento {tipo_label} neste horário '
                f'({ag_conf.inicio:%d/%m/%Y às %H:%M}, #{ag_conf.pk}). '
                'Escolha outro horário.'
            )
        else:
            agendamento            = form.save(commit=False)
            agendamento.fornecedor = fornecedor
            agendamento.inicio     = inicio

            if tipo_op == 'CROSS':
                agendamento.nfe_validada = True   # CROSS pula triagem fiscal
            agendamento.save()

            if tipo_op == 'CROSS':
                messages.success(
                    request,
                    f"✅ Agendamento Crossdocking confirmado! Código: {agendamento.codigo_descarga}"
                )
            else:
                messages.success(request, "✅ Agendamento criado! Vincule a NF-e para confirmar.")
            return redirect('dashboard_industria')

    return render(request, 'industria/novo_agendamento.html', {
        'form':       form,
        'fornecedor': fornecedor,
    })

# ==========================================
# VÍNCULO FISCAL (XML) - LOGICA DE TRIAGEM
# ==========================================

@login_required
def upload_nfe(request, agendamento_id):
    """Vínculo de NF-e com Triagem Fiscal Manual em caso de erro no ERP."""
    fornecedor  = get_object_or_404(Fornecedor, user=request.user)
    agendamento = get_object_or_404(Agendamento, pk=agendamento_id, fornecedor=fornecedor)

    is_cross = agendamento.tipo_operacao == 'CROSS'

    # CROSS já está CONFIRMADO — upload de XML é opcional, mas permitido
    # DIRETA só aceita upload nos estados PRE/FIS
    if not is_cross and agendamento.status_dinamico['code'] not in ['PRE', 'FIS']:
        messages.error(request, "Este agendamento já não permite alteração fiscal.")
        return redirect('dashboard_industria')

    form = UploadNFeXmlForm(request.POST or None, request.FILES or None)
    resumo_nfe = None
    erro_validacao = None

    if request.method == 'POST' and form.is_valid():
        arquivos = form.cleaned_data['arquivo_nfe']

        if is_cross:
            # ── CROSS: processa lote misto PDF + XML ──────────────────────────
            empresa   = EmpresaOperadora.objects.filter(ativa=True).first()
            cnpj_dest = empresa.cnpj if empresa else ""

            salvos      = 0
            erros_cross = []
            chaves_novas = []

            for arquivo in arquivos:
                nome_lower = arquivo.name.lower()

                if nome_lower.endswith('.pdf'):
                    arquivo.seek(0)
                    conteudo = arquivo.read()
                    nfe_obj = NFeArquivo(
                        agendamento=agendamento, tipo_arquivo='PDF', chave='', aprovado=True
                    )
                    nfe_obj.arquivo.save(arquivo.name.split('/')[-1], ContentFile(conteudo), save=True)
                    salvos += 1

                elif nome_lower.endswith('.xml'):
                    chave, valido, mensagem = validar_nfe_xml(arquivo, cnpj_dest)
                    if not valido:
                        logger.warning('CROSS XML inválido — %s | %s', arquivo.name, mensagem)
                        erros_cross.append(f"{arquivo.name}: {mensagem}")
                    else:
                        arquivo.seek(0)
                        conteudo = arquivo.read()
                        nfe_obj = NFeArquivo(
                            agendamento=agendamento, tipo_arquivo='XML', chave=chave, aprovado=True
                        )
                        nfe_obj.arquivo.save(arquivo.name.split('/')[-1], ContentFile(conteudo), save=True)
                        chaves_novas.append(chave)
                        salvos += 1

            if salvos == 0:
                erro_validacao = " | ".join(erros_cross) or "Nenhum arquivo foi processado."
            else:
                if chaves_novas:
                    existentes = [c for c in (agendamento.chave_nfe or '').split(',') if c.strip()]
                    agendamento.chave_nfe = ",".join(existentes + chaves_novas)
                agendamento.nfe_validada = True
                agendamento.save()

                msg = f"{salvos} documento(s) vinculado(s) ao agendamento."
                if erros_cross:
                    msg += f" Atenção: {len(erros_cross)} arquivo(s) com erro não foram salvos."
                    messages.warning(request, msg)
                else:
                    messages.success(request, msg)
                return redirect('dashboard_industria')

        else:
            # ── DIRETA: todos os XMLs devem ser válidos → AGUARDANDO_FISCAL ──
            empresa   = EmpresaOperadora.objects.filter(ativa=True).first()
            cnpj_dest = empresa.cnpj if empresa else ""

            erros       = []
            arquivos_ok = []
            for arquivo in arquivos:
                chave, valido, mensagem = validar_nfe_xml(arquivo, cnpj_dest)
                if not valido:
                    logger.warning('NF-e inválida — arquivo: %s | motivo: %s', arquivo.name, mensagem)
                    if 'CNPJ do destinatário' in mensagem:
                        erros.append(
                            '❌ NF-e inválida: o destinatário da nota não corresponde à '
                            'AG Simões Direta Distribuição. Verifique se a nota foi emitida '
                            'corretamente contra o nosso CNPJ e tente novamente.'
                        )
                    else:
                        erros.append(mensagem)
                else:
                    arquivo.seek(0)
                    arquivos_ok.append((arquivo, chave))

            if erros:
                erro_validacao = " | ".join(erros)
            else:
                dados = []
                for arquivo, chave in arquivos_ok:
                    arquivo.seek(0)
                    dados.append({
                        'nome':     arquivo.name.split('/')[-1],
                        'conteudo': arquivo.read(),
                        'chave':    chave,
                    })

                chaves = []
                for d in dados:
                    nfe_obj = NFeArquivo(agendamento=agendamento, chave=d['chave'])
                    nfe_obj.arquivo.save(d['nome'], ContentFile(d['conteudo']), save=True)
                    chaves.append(d['chave'])

                primeiro = dados[0]
                agendamento.arquivo_xml.save(
                    primeiro['nome'], ContentFile(primeiro['conteudo']), save=False
                )
                agendamento.chave_nfe = ",".join(chaves)
                agendamento.status    = 'AGUARDANDO_FISCAL'
                agendamento.save()

                messages.warning(
                    request,
                    f"⚠️ {len(dados)} NF-e(s) recebida(s). Seu agendamento entrou em 'Pré-entrada Fiscal'. "
                    "Aguarde a liberação do nosso setor interno para confirmar sua entrada."
                )
                return redirect('dashboard_industria')

    return render(request, 'industria/upload_nfe.html', {
        'agendamento': agendamento,
        'form': form,
        'resumo_nfe': resumo_nfe,
        'erro_validacao': erro_validacao,
        'prazo': agendamento.prazo_vinculo_nfe(),
    })

# ==========================================
# PORTAL DA INDÚSTRIA — NOVAS PÁGINAS
# ==========================================

@login_required
def detalhe_agendamento(request, agendamento_id):
    """Detalhe de um agendamento da indústria."""
    fornecedor = get_object_or_404(Fornecedor, user=request.user)
    agendamento = get_object_or_404(Agendamento, pk=agendamento_id, fornecedor=fornecedor)

    log_rejeicao   = None
    motivo_rejeicao = None
    if agendamento.status == 'PRE_AGENDADO':
        log = (
            agendamento.logs
            .filter(status_novo='PRE_AGENDADO', usuario__icontains='Rejeitados:')
            .order_by('-data')
            .first()
        )
        if log:
            log_rejeicao = log
            partes = log.usuario.split(' — Rejeitados: ', 1)
            motivo_rejeicao = partes[1] if len(partes) == 2 else log.usuario

    return render(request, 'industria/detalhe_agendamento.html', {
        'agendamento':    agendamento,
        'fornecedor':     fornecedor,
        'agora':          timezone.now(),
        'log_rejeicao':   log_rejeicao,
        'motivo_rejeicao': motivo_rejeicao,
    })

@login_required
def cancelar_agendamento_industria(request, agendamento_id):
    """Cancela um pré-agendamento para que a indústria possa criar novo."""
    fornecedor = get_object_or_404(Fornecedor, user=request.user)
    agendamento = get_object_or_404(Agendamento, pk=agendamento_id, fornecedor=fornecedor)
    if request.method == 'POST' and agendamento.status == 'PRE_AGENDADO':
        agendamento.status = 'CANCELADO'
        agendamento.save()
        messages.success(request, f"Agendamento #{agendamento.pk} cancelado. Você pode criar um novo.")
        return redirect('novo_agendamento')
    return redirect('industria_detalhe', agendamento_id=agendamento_id)

@login_required
def perfil_industria(request):
    """Perfil do fornecedor em modo leitura."""
    fornecedor = get_object_or_404(Fornecedor, user=request.user)
    return render(request, 'industria/perfil.html', {'fornecedor': fornecedor})

@login_required
def lista_agendamentos_status(request):
    """Lista de agendamentos filtrada por status."""
    fornecedor = get_object_or_404(Fornecedor, user=request.user)
    status = request.GET.get('status', 'PRE_AGENDADO')

    STATUS_META = {
        'PRE_AGENDADO': {'label': 'Pré-agendados',       'filtro': ['PRE_AGENDADO', 'AGUARDANDO_FISCAL']},
        'CONFIRMADO':   {'label': 'Confirmados',          'filtro': ['CONFIRMADO']},
        'EM_PATIO':     {'label': 'Em Pátio / Descarga',  'filtro': ['EM_PATIO', 'EM_DESCARGA']},
        'FINALIZADO':   {'label': 'Finalizados',          'filtro': ['FINALIZADO']},
    }
    meta = STATUS_META.get(status, STATUS_META['PRE_AGENDADO'])

    agendamentos = Agendamento.objects.filter(
        fornecedor=fornecedor,
        status__in=meta['filtro'],
    ).order_by('-inicio')

    return render(request, 'industria/lista_agendamentos.html', {
        'agendamentos':  agendamentos,
        'fornecedor':    fornecedor,
        'status_filtro': status,
        'status_label':  meta['label'],
        'statuses': [
            ('PRE_AGENDADO', 'Pré-agendados'),
            ('CONFIRMADO',   'Confirmados'),
            ('EM_PATIO',     'Em Pátio / Descarga'),
            ('FINALIZADO',   'Finalizados'),
        ],
    })

# ==========================================
# GESTÃO DE PÁTIO & FISCAL (STAFF)
# ==========================================

@login_required(login_url='/staff/login/')
def dashboard_logistica(request):
    """Dashboard do Gestor — calendário operacional (dia / semana / mês)."""
    if not _tem_acesso(request.user, 'gestor_patio'):
        return render(request, '403.html', status=403)

    import calendar as cal_module
    from datetime import date as date_type

    data_str = request.GET.get('data', timezone.now().date().isoformat())
    try:
        data_filtro = datetime.strptime(data_str, '%Y-%m-%d').date()
    except ValueError:
        data_filtro = timezone.now().date()
        data_str = data_filtro.isoformat()

    periodo = request.GET.get('periodo', 'dia')
    if periodo not in ('dia', 'semana', 'mes'):
        periodo = 'dia'

    fornecedor_id = request.GET.get('fornecedor', '')
    fornecedores  = Fornecedor.objects.all().order_by('razao_social')

    qs = Agendamento.objects.select_related('fornecedor').all()
    if fornecedor_id:
        try:
            qs = qs.filter(fornecedor_id=int(fornecedor_id))
        except (ValueError, TypeError):
            fornecedor_id = ''

    if periodo == 'semana':
        agendamentos = qs.filter(
            inicio__date__gte=data_filtro,
            inicio__date__lt=data_filtro + timedelta(days=7),
        ).order_by('inicio')
    elif periodo == 'mes':
        agendamentos = qs.filter(
            inicio__month=data_filtro.month,
            inicio__year=data_filtro.year,
        ).order_by('inicio')
    else:
        agendamentos = qs.filter(inicio__date=data_filtro).order_by('inicio')

    _MESES_PT = ['Janeiro','Fevereiro','Março','Abril','Maio','Junho',
                 'Julho','Agosto','Setembro','Outubro','Novembro','Dezembro']
    if periodo == 'semana':
        titulo_periodo = f"Semana de {data_filtro.strftime('%d/%m')}"
    elif periodo == 'mes':
        titulo_periodo = f"{_MESES_PT[data_filtro.month - 1]}/{data_filtro.year}"
    else:
        titulo_periodo = data_filtro.strftime('%d/%m/%Y')

    # KPIs
    total        = agendamentos.count()
    pre_agendados = agendamentos.filter(status__in=['PRE_AGENDADO', 'AGUARDANDO_FISCAL']).count()
    confirmados  = agendamentos.filter(status='CONFIRMADO').count()
    em_patio     = agendamentos.filter(status='EM_PATIO').count()
    em_descarga  = agendamentos.filter(status='EM_DESCARGA').count()
    em_operacao  = em_patio + em_descarga
    finalizados  = agendamentos.filter(status='FINALIZADO').count()
    noshow       = agendamentos.filter(status='NO_SHOW').count()

    # Alertas de prazo NF-e crítico (< 6 h)
    alertas_prazo = []
    agora = timezone.now()
    for ag in agendamentos.filter(status__in=['PRE_AGENDADO', 'AGUARDANDO_FISCAL'], nfe_validada=False):
        prazo = ag.prazo_vinculo_nfe()
        if prazo:
            minutos = int((prazo - agora).total_seconds() / 60)
            if minutos < 360:
                alertas_prazo.append({'ag': ag, 'minutos': minutos, 'urgente': minutos < 60})

    # ── Estruturas de calendário ──────────────────────────────────────
    HORAS_OP = [7, 8, 9, 10, 11, 12, 13, 14, 15, 16]
    hoje     = timezone.now().date()

    # DIA — lista de slots por hora, enriquecida com SlotFixo
    slots_hora = []
    if periodo == 'dia':
        ags_list = list(agendamentos)
        dow = data_filtro.weekday()
        slots_fixos_map = {}
        if dow < 5:
            for sf in SlotFixo.objects.filter(dia_semana=dow, ativo=True):
                slots_fixos_map[sf.hora] = sf

        # Estende HORAS_OP para incluir horas extras da grade (ex: 17h, 18h na Terça/Quinta)
        horas_grade = set(HORAS_OP) | set(slots_fixos_map.keys())
        for hora in sorted(horas_grade):
            slot_fixo = slots_fixos_map.get(hora)
            ags_na_hora = [ag for ag in ags_list if ag.inicio.hour == hora]
            slots_hora.append({
                'hora':        hora,
                'agendamentos': ags_na_hora,
                'slot_fixo':   slot_fixo,
            })

    # SEMANA — 7 dias × horas
    dias_semana = []
    if periodo == 'semana':
        dias = [data_filtro + timedelta(days=i) for i in range(7)]
        ags_por_dia = {}
        for ag in agendamentos:
            ags_por_dia.setdefault(ag.inicio.date(), []).append(ag)
        for dia in dias:
            ags_do_dia = ags_por_dia.get(dia, [])
            dias_semana.append({
                'data':    dia,
                'is_hoje': dia == hoje,
                'slots': [
                    {'hora': h, 'agendamentos': [ag for ag in ags_do_dia if ag.inicio.hour == h]}
                    for h in HORAS_OP
                ],
            })

    # MÊS — semanas do mês (cal_module.monthcalendar: seg=0, dom=6)
    semanas_mes = []
    if periodo == 'mes':
        ags_por_dia_mes = {}
        for ag in agendamentos:
            ags_por_dia_mes.setdefault(ag.inicio.date(), []).append(ag)
        for week in cal_module.monthcalendar(data_filtro.year, data_filtro.month):
            semana = []
            for day_num in week:
                if day_num == 0:
                    semana.append({'data': None, 'agendamentos': [], 'is_hoje': False, 'fora_mes': True})
                else:
                    d = date_type(data_filtro.year, data_filtro.month, day_num)
                    semana.append({
                        'data':        d,
                        'agendamentos': ags_por_dia_mes.get(d, []),
                        'is_hoje':     d == hoje,
                        'fora_mes':    False,
                    })
            semanas_mes.append(semana)

    contexto = {
        'agendamentos':   agendamentos,
        'data_filtro':    data_str,
        'data_exibicao':  data_filtro.strftime('%d/%m/%Y'),
        'periodo':        periodo,
        'titulo_periodo': titulo_periodo,
        'total':          total,
        'pre_agendados':  pre_agendados,
        'confirmados':    confirmados,
        'em_operacao':    em_operacao,
        'em_patio':       em_patio,
        'em_descarga':    em_descarga,
        'finalizados':    finalizados,
        'noshow':         noshow,
        'alertas_prazo':  alertas_prazo,
        'agora':          agora,
        'hoje':           hoje,
        'fornecedores':   fornecedores,
        'fornecedor_id':  fornecedor_id,
        'slots_hora':     slots_hora,
        'dias_semana':    dias_semana,
        'semanas_mes':    semanas_mes,
    }
    return render(request, 'dashboard_gestor.html', contexto)

@login_required(login_url='/staff/login/')
def gestor_aprovar_fiscal(request, agendamento_id):
    """Aprovação manual de NF-e que falhou na validação automática."""
    if not _tem_acesso(request.user, 'gestor_patio'):
        return render(request, '403.html', status=403)
    agendamento = get_object_or_404(Agendamento, pk=agendamento_id)
    
    if request.method == 'POST':
        # Força a validação manual
        agendamento.nfe_validada = True
        agendamento.status = 'CONFIRMADO'
        agendamento.nfe_vinculada_em = timezone.now()
        agendamento.save()
        
        messages.success(request, f"✅ Agendamento #{agendamento.pk} aprovado manualmente pelo fiscal.")
        # TODO: Adicionar trigger de e-mail para a indústria aqui

    return redirect('dashboard')

@login_required(login_url='/staff/login/')
def gestor_checkin(request, agendamento_id):
    if not _tem_acesso(request.user, 'gestor_patio'):
        return render(request, '403.html', status=403)
    agendamento = get_object_or_404(Agendamento, pk=agendamento_id)

    if request.method == 'POST':
        if agendamento.status == 'CONFIRMADO':
            agora = timezone.now()
            agendamento.horario_entrada_patio = agora
            agendamento.horario_chegada_real = agora
            agendamento.status = 'EM_PATIO'
            agendamento.save()
            messages.success(request, f"✅ Entrada no Pátio registrada para #{agendamento.pk}!")
        else:
            messages.error(request, "Agendamento não está com status CONFIRMADO.")

    data   = request.POST.get('data_filtro', '')
    periodo = request.POST.get('periodo', 'dia')
    return redirect(f"/dashboard/?data={data}&periodo={periodo}")

@login_required(login_url='/staff/login/')
def gestor_status(request, agendamento_id):
    if not _tem_acesso(request.user, 'gestor_patio'):
        return render(request, '403.html', status=403)
    agendamento = get_object_or_404(Agendamento, pk=agendamento_id)
    
    if request.method == 'POST':
        acao = request.POST.get('novo_status')
        if acao == 'EM_DESCARGA':
            agendamento.status = 'EM_DESCARGA'
            agendamento.horario_inicio_descarga = timezone.now()
            agendamento.save()
            LogAgendamento.objects.create(
                agendamento=agendamento,
                usuario=request.user,
                status_anterior='EM_PATIO',
                status_novo='EM_DESCARGA',
            )
            messages.success(request, f"✅ Status atualizado: EM_DESCARGA")
        elif acao == 'FINALIZADO':
            agendamento.status = 'FINALIZADO'
            agendamento.horario_finalizacao = timezone.now()
            agendamento.save()
            LogAgendamento.objects.create(
                agendamento=agendamento,
                usuario=request.user,
                status_anterior='EM_DESCARGA',
                status_novo='FINALIZADO',
            )
            messages.success(request, f"✅ Status atualizado: FINALIZADO")

    data    = request.POST.get('data_filtro', '')
    periodo = request.POST.get('periodo', 'dia')
    return redirect(f"/dashboard/?data={data}&periodo={periodo}")


@login_required(login_url='/staff/login/')
def gestor_detalhe(request, pk):
    if not _tem_acesso(request.user, 'gestor_patio'):
        return render(request, '403.html', status=403)
    agendamento = get_object_or_404(Agendamento, pk=pk)
    logs = agendamento.logs.all().order_by('data')
    nfes = agendamento.nfe_arquivos.all()

    duracao_total = None
    duracao_descarga = None
    if agendamento.horario_finalizacao and agendamento.horario_entrada_patio:
        delta = agendamento.horario_finalizacao - agendamento.horario_entrada_patio
        mins = int(delta.total_seconds() / 60)
        duracao_total = f"{mins // 60}h {mins % 60:02d}min"
    if agendamento.horario_finalizacao and agendamento.horario_inicio_descarga:
        delta = agendamento.horario_finalizacao - agendamento.horario_inicio_descarga
        mins = int(delta.total_seconds() / 60)
        duracao_descarga = f"{mins // 60}h {mins % 60:02d}min"

    _rank = {
        'PRE_AGENDADO': 0, 'AGUARDANDO_FISCAL': 1, 'CONFIRMADO': 2,
        'EM_PATIO': 3, 'EM_DESCARGA': 4, 'FINALIZADO': 5,
    }
    status_rank = _rank.get(agendamento.status, 0)

    return render(request, 'gestor_detalhe.html', {
        'agendamento': agendamento,
        'logs': logs,
        'nfes': nfes,
        'duracao_total': duracao_total,
        'duracao_descarga': duracao_descarga,
        'status_rank': status_rank,
    })


# ==========================================
# PORTAL FISCAL (STAFF)
# ==========================================

@login_required(login_url='/staff/login/')
def fiscal_dashboard(request):
    """Dashboard completo do analista fiscal: fila de aprovação + histórico de triagens."""
    if not request.user.groups.filter(name='analista_fiscal').exists():
        return render(request, '403.html', status=403)

    agora = timezone.now()
    trinta_dias = agora - timedelta(days=30)

    # ── A) Fila de aprovação — apenas agendamentos DIRETA (CROSS não passa pelo fiscal) ──
    aguardando_qs = (
        Agendamento.objects
        .filter(status='AGUARDANDO_FISCAL', tipo_operacao='DIRETA')
        .select_related('fornecedor')
        .prefetch_related('docas', 'logs')
        .order_by('inicio')
    )
    aguardando = []
    for ag in aguardando_qs:
        logs_entrada = [l for l in ag.logs.all() if l.status_novo == 'AGUARDANDO_FISCAL']
        log_entrada = max(logs_entrada, key=lambda l: l.data) if logs_entrada else None
        aguardando_desde = log_entrada.data if log_entrada else None
        urgente = bool(aguardando_desde and (agora - aguardando_desde).total_seconds() > 7200)
        aguardando.append({
            'ag': ag,
            'aguardando_desde': aguardando_desde,
            'urgente': urgente,
        })

    # ── B) Histórico de triagens (últimos 30 dias) ───────────────────────────
    historico_base = (
        LogAgendamento.objects
        .filter(
            status_anterior='AGUARDANDO_FISCAL',
            status_novo__in=['CONFIRMADO', 'PRE_AGENDADO'],
            data__gte=trinta_dias,
        )
        .select_related('agendamento', 'agendamento__fornecedor')
        .order_by('-data')
    )

    total_triado = historico_base.count()
    n_aprovados  = historico_base.filter(status_novo='CONFIRMADO').count()
    n_rejeitados = historico_base.filter(status_novo='PRE_AGENDADO').count()

    # Tempo médio de resposta: busca os logs de entrada em AGUARDANDO_FISCAL em lote
    tempo_medio_str = None
    if total_triado:
        ag_ids = list(historico_base.values_list('agendamento_id', flat=True))
        entradas_map = {}
        for log in (
            LogAgendamento.objects
            .filter(agendamento_id__in=ag_ids, status_novo='AGUARDANDO_FISCAL')
            .order_by('agendamento_id', '-data')
        ):
            if log.agendamento_id not in entradas_map:
                entradas_map[log.agendamento_id] = log.data
        tempos = []
        for log in historico_base:
            entrada_dt = entradas_map.get(log.agendamento_id)
            if entrada_dt and log.data > entrada_dt:
                tempos.append((log.data - entrada_dt).total_seconds())
        if tempos:
            media_s = sum(tempos) / len(tempos)
            h = int(media_s // 3600)
            m = int((media_s % 3600) // 60)
            tempo_medio_str = f"{h}h{m:02d}min" if h else f"{m}min"

    # Filtro por decisão
    filtro_decisao = request.GET.get('decisao', 'todos')
    if filtro_decisao == 'aprovados':
        historico_filtrado = historico_base.filter(status_novo='CONFIRMADO')
    elif filtro_decisao == 'rejeitados':
        historico_filtrado = historico_base.filter(status_novo='PRE_AGENDADO')
    else:
        filtro_decisao = 'todos'
        historico_filtrado = historico_base

    # Pré-processa usuario para separar analista / motivo
    historico = []
    for log in historico_filtrado:
        if ' — Rejeitados: ' in (log.usuario or ''):
            analista, motivo = log.usuario.split(' — Rejeitados: ', 1)
        else:
            analista, motivo = (log.usuario or ''), ''
        historico.append({
            'log':      log,
            'analista': analista,
            'motivo':   motivo,
            'aprovado': log.status_novo == 'CONFIRMADO',
        })

    return render(request, 'fiscal/dashboard.html', {
        'aguardando':      aguardando,
        'total':           len(aguardando),
        'agora':           agora,
        'historico':       historico,
        'filtro_decisao':  filtro_decisao,
        'kpis': {
            'total_triado': total_triado,
            'aprovados':    n_aprovados,
            'rejeitados':   n_rejeitados,
            'tempo_medio':  tempo_medio_str,
        },
    })

# ==========================================
# PORTAL DO CLIENTE
# ==========================================

def cliente_login(request):
    """Login do cliente final via CNPJ + senha."""
    if request.user.is_authenticated and hasattr(request.user, 'cliente'):
        return redirect('cliente_dashboard')

    error = None
    cnpj_val = ''

    if request.method == 'POST':
        cnpj_raw = request.POST.get('cnpj', '')
        password = request.POST.get('password', '')
        cnpj_val = cnpj_raw

        cnpj_digits = ''.join(filter(str.isdigit, cnpj_raw))

        try:
            cliente = Cliente.objects.get(cnpj=cnpj_digits, ativo=True)
        except Cliente.DoesNotExist:
            error = "CNPJ não cadastrado ou inativo."
            cliente = None

        if cliente and cliente.user:
            user = authenticate(request, username=cliente.user.username, password=password)
            if user is not None:
                login(request, user)
                return redirect('cliente_dashboard')
            else:
                error = "Senha incorreta."
        elif cliente and not cliente.user:
            error = "Conta de acesso não configurada. Contacte a AG Simões."

    return render(request, 'cliente/login.html', {'error': error, 'cnpj_val': cnpj_val})


@login_required(login_url='/cliente/login/')
def cliente_dashboard(request):
    """Dashboard do cliente final."""
    if not hasattr(request.user, 'cliente'):
        return render(request, '403.html', status=403)

    cliente = request.user.cliente
    agora   = timezone.now()
    trinta_dias_atras = agora - timedelta(days=30)

    pedidos_qs = (
        PedidoCliente.objects
        .filter(cliente=cliente)
        .select_related('agendamento__fornecedor')
        .order_by('-criado_em')
    )

    pendentes  = []
    entregues  = []

    for p in pedidos_qs:
        ag = p.agendamento
        if ag and ag.status == 'FINALIZADO':
            entregues.append({'pedido': p, 'ag': ag})
        else:
            pendentes.append({'pedido': p, 'ag': ag})

    total_ativos  = len(pendentes)
    entregues_mes = sum(
        1 for e in entregues
        if e['ag'].horario_finalizacao and e['ag'].horario_finalizacao >= trinta_dias_atras
    )

    return render(request, 'cliente/dashboard.html', {
        'cliente':       cliente,
        'pendentes':     pendentes,
        'entregues':     entregues[:30],
        'total_ativos':  total_ativos,
        'entregues_mes': entregues_mes,
        'agora':         agora,
    })


@login_required(login_url='/cliente/login/')
def cliente_detalhe_pedido(request, pk):
    """Detalhe de um pedido do cliente, com timeline pública."""
    if not hasattr(request.user, 'cliente'):
        return render(request, '403.html', status=403)

    cliente = request.user.cliente
    pedido = get_object_or_404(
        PedidoCliente.objects.select_related('agendamento__fornecedor', 'cliente'),
        pk=pk,
    )

    if pedido.cliente_id != cliente.id:
        return render(request, '403.html', status=403)

    ag = pedido.agendamento
    status_liberado = bool(
        ag and ag.status in ['CONFIRMADO', 'EM_PATIO', 'EM_DESCARGA', 'FINALIZADO']
    )

    return render(request, 'cliente/detalhe_pedido.html', {
        'pedido':           pedido,
        'agendamento':      ag,
        'status_liberado':  status_liberado,
        'cliente':          cliente,
    })


def fiscal_aprovar(request, pk):
    """Triagem fiscal individual por NFeArquivo."""
    if not request.user.groups.filter(name='analista_fiscal').exists():
        return render(request, '403.html', status=403)
    agendamento = get_object_or_404(Agendamento, pk=pk, status='AGUARDANDO_FISCAL')

    def _build_nfe_list():
        result = []
        for nfe in agendamento.nfe_arquivos.all():
            resumo = None
            try:
                with nfe.arquivo.open('rb') as f:
                    resumo = extrair_resumo_nfe(f)
            except Exception:
                pass
            result.append({'nfe': nfe, 'resumo': resumo})
        return result

    # ── Vínculo de Pedido do Cliente Final ────────────────────────────────
    if request.method == 'POST' and request.POST.get('action') == 'vincular_pedido':
        vinculo_form = VinculoPedidoClienteForm(request.POST)
        if vinculo_form.is_valid():
            cd = vinculo_form.cleaned_data
            pedido, _criado = PedidoCliente.objects.update_or_create(
                agendamento=agendamento,
                defaults={
                    'cliente':               cd['cliente'],
                    'numero_pedido_cliente': cd['numero_pedido_cliente'],
                    'tipo_atendimento':      cd['tipo_atendimento'],
                    'observacao':            cd['observacao'],
                    'criado_por':            request.user,
                },
            )
            messages.success(
                request,
                f"Pedido {pedido.numero_pedido_cliente} do {pedido.cliente.razao_social} vinculado."
            )
            return redirect('fiscal_aprovar', pk=agendamento.pk)
        # form inválido → cai no render abaixo com erros do form
        pedido_existente = PedidoCliente.objects.filter(agendamento=agendamento).first()
        return render(request, 'fiscal/aprovar.html', {
            'agendamento':      agendamento,
            'nfe_list':         _build_nfe_list(),
            'agora':            timezone.now(),
            'vinculo_form':     vinculo_form,
            'pedido_existente': pedido_existente,
            'abrir_vinculo':    True,
        })

    if request.method == 'POST':
        nfe_arquivos = list(agendamento.nfe_arquivos.all())

        # Coleta e valida as decisões antes de gravar qualquer coisa
        erros    = []
        decisoes = {}
        for nfe in nfe_arquivos:
            decisao = request.POST.get(f'decisao_{nfe.pk}', '').strip()
            motivo  = request.POST.get(f'motivo_{nfe.pk}', '').strip()
            if decisao not in ('aprovar', 'rejeitar'):
                erros.append(f"NF-e …{nfe.chave[-6:]}: selecione Aprovar ou Rejeitar.")
            elif decisao == 'rejeitar' and not motivo:
                erros.append(f"NF-e …{nfe.chave[-6:]}: informe o motivo da rejeição.")
            else:
                decisoes[nfe.pk] = {'decisao': decisao, 'motivo': motivo}

        if erros:
            for e in erros:
                messages.error(request, e)
            # cai no render abaixo
        else:
            status_anterior   = agendamento.status
            chaves_aprovadas  = []
            motivos_rejeicao  = []

            for nfe in nfe_arquivos:
                d = decisoes[nfe.pk]
                if d['decisao'] == 'aprovar':
                    nfe.aprovado = True
                    nfe.save()
                    chaves_aprovadas.append(nfe.chave)
                else:
                    motivos_rejeicao.append(f"{nfe.chave[-6:]}: {d['motivo']}")
                    nfe.arquivo.delete(save=False)
                    nfe.delete()

            algum_rejeitado = bool(motivos_rejeicao)

            if algum_rejeitado:
                agendamento.status       = 'PRE_AGENDADO'
                agendamento.nfe_validada = False
                agendamento.chave_nfe    = ",".join(chaves_aprovadas) if chaves_aprovadas else None
                agendamento.save()
                LogAgendamento.objects.create(
                    agendamento=agendamento,
                    status_anterior=status_anterior,
                    status_novo='PRE_AGENDADO',
                    usuario=f"{request.user.username} — Rejeitados: {'; '.join(motivos_rejeicao)}",
                )
                messages.warning(
                    request,
                    f"⚠️ {len(motivos_rejeicao)} NF-e(s) rejeitada(s). "
                    f"Agendamento #{pk} devolvido para a indústria reenviar."
                )
            else:
                agendamento.nfe_validada     = True
                agendamento.nfe_vinculada_em = timezone.now()
                agendamento.status           = 'CONFIRMADO'
                agendamento.chave_nfe        = ",".join(chaves_aprovadas)
                agendamento.save()  # save() gera codigo_descarga automaticamente
                LogAgendamento.objects.create(
                    agendamento=agendamento,
                    status_anterior=status_anterior,
                    status_novo='CONFIRMADO',
                    usuario=request.user.username,
                )
                messages.success(
                    request,
                    f"✅ Todas as NF-es aprovadas. Agendamento #{pk} CONFIRMADO. "
                    f"Código: {agendamento.codigo_descarga}"
                )
            return redirect('fiscal_dashboard')

    pedido_existente = PedidoCliente.objects.filter(agendamento=agendamento).first()
    return render(request, 'fiscal/aprovar.html', {
        'agendamento':      agendamento,
        'nfe_list':         _build_nfe_list(),
        'agora':            timezone.now(),
        'vinculo_form':     VinculoPedidoClienteForm(),
        'pedido_existente': pedido_existente,
        'abrir_vinculo':    False,
    })


@login_required(login_url='/staff/login/')
def consulta_portaria(request):
    if not _tem_acesso(request.user, 'portaria'):
        return render(request, '403.html', status=403)
    chave  = request.GET.get('chave',  '').strip()
    pedido = request.GET.get('pedido', '').strip()
    agendamento = None
    if chave:
        agendamento = Agendamento.objects.filter(chave_nfe__icontains=chave).first()
    elif pedido:
        agendamento = (
            Agendamento.objects
            .filter(numero_pedido__iexact=pedido)
            .order_by('-inicio')
            .first()
        )
    pode_entrar = agendamento is not None and agendamento.status == 'CONFIRMADO'
    return render(request, 'portaria/consulta.html', {
        'agendamento': agendamento,
        'buscou':      bool(chave or pedido),
        'pode_entrar': pode_entrar,
    })