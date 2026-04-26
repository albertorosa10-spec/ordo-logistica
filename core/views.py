# ==========================================
# CORE/VIEWS.PY
# Ordo Logística — v0.8.1
# Fluxo: Triagem Fiscal Manual + Bypass Winthor
# ==========================================

import json
from datetime import timedelta, datetime

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.mail import EmailMessage
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET

from .models import Agendamento, Fornecedor, EmpresaOperadora, Doca, LogAgendamento, NFeArquivo


def _tem_acesso(user, grupo):
    """Retorna True para superusuários ou membros do grupo informado."""
    return user.is_superuser or user.groups.filter(name=grupo).exists()
from .forms import (
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
        logout(request)
        messages.success(request, "Sessão encerrada com sucesso.")
    return redirect('home')

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
        agendamento = form.save(commit=False)
        agendamento.fornecedor = fornecedor
        agendamento.inicio = form.cleaned_data['inicio']
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

            # E-mail único com todos os XMLs como anexo
            try:
                n     = len(dados)
                plurar = 's' if n > 1 else ''
                corpo = (
                    f"{n} NF-e{plurar} recebida{plurar} para triagem manual.\n\n"
                    f"Agendamento : #{agendamento.pk}\n"
                    f"Fornecedor  : {agendamento.fornecedor.razao_social} ({agendamento.fornecedor.cnpj})\n"
                    f"PO          : {agendamento.numero_pedido}\n"
                    f"Descarga    : {agendamento.inicio.strftime('%d/%m/%Y %H:%M')}\n"
                    f"Chave(s)    : {', '.join(chaves)}\n\n"
                    f"Acesse o portal para aprovar ou rejeitar: /fiscal/agendamento/{agendamento.pk}/"
                )
                email_msg = EmailMessage(
                    subject=(
                        f"[PO: {agendamento.numero_pedido}] {agendamento.fornecedor.razao_social}"
                        f" — XML NF-e ({n} arquivo{plurar})"
                    ),
                    body=corpo,
                    to=['fiscal@diretadistribuidor.com.br'],
                    cc=['xml1@diretadistribuidor.com.br'],
                )
                for d in dados:
                    email_msg.attach(d['nome'], d['conteudo'], 'application/xml')
                email_msg.send(fail_silently=False)
            except Exception:
                pass  # Falha no e-mail não interrompe o fluxo

            messages.warning(
                request,
                f"⚠️ {len(dados)} NF-e(s) recebida(s). Seu agendamento entrou em 'Análise Fiscal'. "
                "Aguarde a liberação do nosso setor interno para obter seu código de descarga."
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
    return render(request, 'industria/detalhe_agendamento.html', {
        'agendamento': agendamento,
        'fornecedor':  fornecedor,
        'agora':       timezone.now(),
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

@login_required
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

    # Docas Status (para a sidebar)
    docas_ativas = Doca.objects.filter(ativa=True).order_by('codigo')
    docas_status = []
    for doca in docas_ativas:
        ag_ativo = agendamentos.filter(docas=doca, status__in=['EM_PATIO', 'EM_DESCARGA']).first()
        ag_prox = agendamentos.filter(
            docas=doca,
            status__in=['PRE_AGENDADO', 'AGUARDANDO_FISCAL', 'CONFIRMADO'],
            inicio__gt=agora,
        ).first()
        
        # Ocupação: percentual do dia útil (11 horas operacionais)
        total_ag_doca = agendamentos.filter(docas=doca).count()
        ocup_pct = min(100, (total_ag_doca * 60 / 660) * 100)
        
        docas_status.append({
            'doca': doca,
            'ag_ativo': ag_ativo,
            'ag_prox': ag_prox,
            'total_dia': total_ag_doca,
            'ocup_pct': ocup_pct
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
        'docas': docas_ativas,
    }
    
    return render(request, 'dashboard_gestor.html', contexto)

@login_required
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

@login_required
def gestor_checkin(request, agendamento_id):
    if not _tem_acesso(request.user, 'gestor_patio'):
        return render(request, '403.html', status=403)
    agendamento = get_object_or_404(Agendamento, pk=agendamento_id)
    
    if request.method == 'POST':
        codigo = request.POST.get('codigo_descarga')
        try:
            agendamento.fazer_checkin(codigo)
            messages.success(request, "✅ Check-in realizado!")
        except ValidationError as e:
            messages.error(request, e.message)
            
    return redirect(f"/dashboard/?data={request.POST.get('data_filtro', '')}")

@login_required
def gestor_status(request, agendamento_id):
    if not _tem_acesso(request.user, 'gestor_patio'):
        return render(request, '403.html', status=403)
    agendamento = get_object_or_404(Agendamento, pk=agendamento_id)
    
    if request.method == 'POST':
        acao = request.POST.get('novo_status')
        try:
            if acao == 'EM_DESCARGA': agendamento.iniciar_descarga()
            elif acao == 'FINALIZADO': agendamento.finalizar_descarga()
            messages.success(request, f"✅ Status atualizado: {agendamento.status_dinamico['label']}")
        except ValidationError as e:
            messages.error(request, e.message)

    return redirect(f"/dashboard/?data={request.POST.get('data_filtro', '')}")

# ==========================================
# PORTAL FISCAL (STAFF)
# ==========================================

@login_required
def fiscal_dashboard(request):
    """Lista agendamentos aguardando triagem fiscal."""
    if not _tem_acesso(request.user, 'analista_fiscal'):
        return render(request, '403.html', status=403)
    aguardando = (
        Agendamento.objects
        .filter(status='AGUARDANDO_FISCAL')
        .select_related('fornecedor')
        .prefetch_related('docas')
        .order_by('inicio')
    )
    return render(request, 'fiscal/dashboard.html', {
        'aguardando': aguardando,
        'total':      aguardando.count(),
        'agora':      timezone.now(),
    })

@login_required
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


@login_required
def consulta_portaria(request):
    if not _tem_acesso(request.user, 'portaria'):
        return render(request, '403.html', status=403)
    chave = request.GET.get('chave', '').strip()
    agendamento = Agendamento.objects.filter(chave_nfe=chave).first() if chave else None
    return render(request, 'portaria/consulta.html', {'agendamento': agendamento, 'buscou': bool(chave)})