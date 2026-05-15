# ==========================================
# CORE/VIEWS.PY
# Zakaz — v0.8.1
# Fluxo: Triagem Fiscal Manual + Bypass Winthor
# ==========================================

import json
from datetime import timedelta, datetime

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET

from .models import Agendamento, Fornecedor, EmpresaOperadora, Doca, LogAgendamento, NFeArquivo, SHADOW_BUFFER


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
        inicio             = form.cleaned_data['inicio']
        docas_selecionadas = form.cleaned_data['docas']
        tipo_carga         = form.cleaned_data['tipo_carga']
        qtd_itens          = form.cleaned_data['qtd_itens']

        # --- Verificação de conflito de doca ---
        # Replica a fórmula de calcular_duracao() + buffer para obter o fim estimado
        _MULT = {'PAL': 0.80, 'BAT': 1.50, 'FRA': 1.20}
        duracao_min = int((30 + qtd_itens) * _MULT.get(tipo_carga, 1.0))
        fim_novo    = inicio + timedelta(minutes=duracao_min + SHADOW_BUFFER)

        # Status que representam ocupação real da doca
        _STATUS_OCUPA = [
            'PRE_AGENDADO', 'AGUARDANDO_FISCAL',
            'CONFIRMADO', 'EM_PATIO', 'EM_DESCARGA',
        ]
        conflito_qs = Agendamento.objects.filter(
            docas__in=docas_selecionadas,
            fim_estimado__isnull=False,
            fim_estimado__gt=inicio,   # existente termina depois que o novo começa
            inicio__lt=fim_novo,       # existente começa antes que o novo termine
            status__in=_STATUS_OCUPA,
        ).select_related('fornecedor').prefetch_related('docas')

        if conflito_qs.exists():
            ag_conf  = conflito_qs.first()
            docas_em_conflito = [
                d.codigo for d in ag_conf.docas.all()
                if d in list(docas_selecionadas)
            ]
            doca_str = ', '.join(docas_em_conflito) if docas_em_conflito else 'selecionada'
            form.add_error(
                None,
                f'Conflito de horário na doca {doca_str}: agendamento #{ag_conf.pk} '
                f'já ocupa este horário ({ag_conf.inicio:%d/%m/%Y às %H:%M} – '
                f'{ag_conf.fim_estimado:%H:%M}). '
                f'Escolha outra doca ou um horário diferente.'
            )
        else:
            agendamento = form.save(commit=False)
            agendamento.fornecedor = fornecedor
            agendamento.inicio     = inicio
            agendamento.save()
            form.save_m2m()
            messages.success(request, "✅ Agendamento criado! Vincule a NF-e para confirmar.")
            return redirect('dashboard_industria')

    return render(request, 'industria/novo_agendamento.html', {
        'form':         form,
        'fornecedor':   fornecedor,
        'docas_ativas': Doca.objects.filter(ativa=True).order_by('codigo'),
        'permite_multi': fornecedor.permite_multi_doca,
    })

# ==========================================
# VÍNCULO FISCAL (XML) - LOGICA DE TRIAGEM
# ==========================================

@login_required
def upload_nfe(request, agendamento_id):
    """Vínculo de NF-e com Triagem Fiscal Manual em caso de erro no ERP."""
    fornecedor = get_object_or_404(Fornecedor, user=request.user)
    agendamento = get_object_or_404(Agendamento, pk=agendamento_id, fornecedor=fornecedor)

    if agendamento.status_dinamico['code'] not in ['PRE', 'FIS']:
        messages.error(request, "Este agendamento já não permite alteração fiscal.")
        return redirect('dashboard_industria')

    form = UploadNFeXmlForm(request.POST or None, request.FILES or None)
    resumo_nfe = None
    erro_validacao = None

    if request.method == 'POST' and form.is_valid():
        empresa  = EmpresaOperadora.objects.filter(ativa=True).first()
        cnpj_dest = empresa.cnpj if empresa else ""
        arquivos  = form.cleaned_data['arquivo_nfe']

        # Valida cada arquivo e extrai chave
        erros        = []
        arquivos_ok  = []  # list of (arquivo, chave)
        for arquivo in arquivos:
            chave, valido, mensagem = validar_nfe_xml(arquivo, cnpj_dest)
            if not valido:
                erros.append(f'"{arquivo.name}": {mensagem}')
            else:
                arquivo.seek(0)
                arquivos_ok.append((arquivo, chave))

        if erros:
            erro_validacao = " | ".join(erros)
        else:
            # Lê todo o conteúdo em memória antes de qualquer save
            # (saves do FileField consomem o buffer da InMemoryUploadedFile)
            dados = []
            for arquivo, chave in arquivos_ok:
                arquivo.seek(0)
                dados.append({
                    'nome':     arquivo.name.split('/')[-1],
                    'conteudo': arquivo.read(),
                    'chave':    chave,
                })

            # Persiste um NFeArquivo por arquivo
            chaves = []
            for d in dados:
                nfe_obj = NFeArquivo(agendamento=agendamento, chave=d['chave'])
                nfe_obj.arquivo.save(d['nome'], ContentFile(d['conteudo']), save=True)
                chaves.append(d['chave'])

            # Atualiza Agendamento (arquivo_xml recebe o primeiro arquivo para compat com fiscal_aprovar)
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
    """Dashboard do Gestor com KPIs, alertas e status das docas."""
    if not _tem_acesso(request.user, 'gestor_patio'):
        return render(request, '403.html', status=403)
    
    data_str = request.GET.get('data', timezone.now().date().isoformat())
    try:
        data_filtro = datetime.strptime(data_str, '%Y-%m-%d').date()
    except ValueError:
        data_filtro = timezone.now().date()
        data_str = data_filtro.isoformat()

    periodo = request.GET.get('periodo', 'dia')
    if periodo not in ('dia', 'semana', 'mes'):
        periodo = 'dia'

    if periodo == 'semana':
        agendamentos = Agendamento.objects.filter(
            inicio__date__gte=data_filtro,
            inicio__date__lt=data_filtro + timedelta(days=7),
        ).order_by('inicio')
    elif periodo == 'mes':
        agendamentos = Agendamento.objects.filter(
            inicio__month=data_filtro.month,
            inicio__year=data_filtro.year,
        ).order_by('inicio')
    else:
        agendamentos = Agendamento.objects.filter(inicio__date=data_filtro).order_by('inicio')

    _MESES_PT = ['Janeiro','Fevereiro','Março','Abril','Maio','Junho',
                 'Julho','Agosto','Setembro','Outubro','Novembro','Dezembro']
    if periodo == 'semana':
        titulo_periodo = f"Semana de {data_filtro.strftime('%d/%m')}"
    elif periodo == 'mes':
        titulo_periodo = f"{_MESES_PT[data_filtro.month - 1]}/{data_filtro.year}"
    else:
        titulo_periodo = data_filtro.strftime('%d/%m/%Y')
    
    # KPIs
    total = agendamentos.count()
    pre_agendados = agendamentos.filter(status='PRE_AGENDADO').count()
    confirmados = agendamentos.filter(status='CONFIRMADO').count()
    em_patio = agendamentos.filter(status='EM_PATIO').count()
    em_descarga = agendamentos.filter(status='EM_DESCARGA').count()
    em_operacao = em_patio + em_descarga
    finalizados = agendamentos.filter(status='FINALIZADO').count()
    noshow = agendamentos.filter(status='NO_SHOW').count()
    
    # Alertas de prazo (NF-e não validada com descarga próxima)
    alertas_prazo = []
    agora = timezone.now()
    # Filtramos agendamentos que ainda não validaram NF-e e estão em status inicial ou análise
    for ag in agendamentos.filter(status__in=['PRE_AGENDADO', 'AGUARDANDO_FISCAL'], nfe_validada=False):
        prazo = ag.prazo_vinculo_nfe()
        if prazo:
            restante_ms = (prazo - agora).total_seconds()
            minutos = int(restante_ms / 60)
            if minutos < 360: # Alerta se faltar menos de 6 horas
                alertas_prazo.append({
                    'ag': ag,
                    'minutos': minutos,
                    'urgente': minutos < 60
                })

    # Docas Status (para a sidebar) — todas as docas, ativas ou não
    todas_docas = Doca.objects.all().order_by('codigo')
    docas_status = []
    for doca in todas_docas:
        if doca.ativa:
            ag_ativo = agendamentos.filter(docas=doca, status__in=['EM_PATIO', 'EM_DESCARGA']).first()
            ag_prox = agendamentos.filter(
                docas=doca,
                status__in=['PRE_AGENDADO', 'AGUARDANDO_FISCAL', 'CONFIRMADO'],
                inicio__gt=agora,
            ).first()
            total_ag_doca = agendamentos.filter(docas=doca).count()
        else:
            ag_ativo = None
            ag_prox = None
            total_ag_doca = 0
        # Ocupação: percentual do dia útil (11 horas operacionais)
        ocup_pct = min(100, (total_ag_doca * 60 / 660) * 100)
        docas_status.append({
            'doca': doca,
            'ag_ativo': ag_ativo,
            'ag_prox': ag_prox,
            'total_dia': total_ag_doca,
            'ocup_pct': ocup_pct,
        })

    contexto = {
        'agendamentos': agendamentos,
        'data_filtro': data_str,
        'data_exibicao': data_filtro.strftime('%d/%m/%Y'),
        'periodo': periodo,
        'titulo_periodo': titulo_periodo,
        'total': total,
        'pre_agendados': pre_agendados,
        'confirmados': confirmados,
        'em_operacao': em_operacao,
        'em_patio': em_patio,
        'em_descarga': em_descarga,
        'finalizados': finalizados,
        'noshow': noshow,
        'alertas_prazo': alertas_prazo,
        'docas_status': docas_status,
        'agora': agora,
        'docas': todas_docas,
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

    return redirect(f"/dashboard/?data={request.POST.get('data_filtro', '')}")

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

    return redirect('/dashboard/')


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
    if not _tem_acesso(request.user, 'analista_fiscal'):
        return render(request, '403.html', status=403)

    agora = timezone.now()
    trinta_dias = agora - timedelta(days=30)

    # ── A) Fila de aprovação ─────────────────────────────────────────────────
    aguardando_qs = (
        Agendamento.objects
        .filter(status='AGUARDANDO_FISCAL')
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

@login_required(login_url='/staff/login/')
def fiscal_aprovar(request, pk):
    """Triagem fiscal individual por NFeArquivo."""
    if not _tem_acesso(request.user, 'analista_fiscal'):
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

    return render(request, 'fiscal/aprovar.html', {
        'agendamento': agendamento,
        'nfe_list':    _build_nfe_list(),
        'agora':       timezone.now(),
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