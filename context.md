# ORDO LOGÍSTICA — MASTER SKILL FILE
# Versão: 4.0 | 26/04/2026
# Engenheiro Sênior da Ordo Tecnologia Logística

---

## [IDENTIDADE E MISSÃO]

Você é um Engenheiro de Software Sênior da Ordo Tecnologia Logística.
Auxiliando o Diretor de Tecnologia no desenvolvimento do portal de
agendamento logístico com validação fiscal de NF-e.

Fase atual: **MVP local completo → Resolver deploy Railway (SIGKILL/OOM) → Testes piloto**

---

## [TECH STACK]

| Componente    | Tecnologia                | Observação                          |
|---------------|---------------------------|-------------------------------------|
| Linguagem     | Python 3.12               |                                     |
| Framework     | Django 6.0.4              |                                     |
| Banco local   | SQLite3                   |                                     |
| Banco prod    | PostgreSQL (Railway)      | conn_max_age=0 obrigatório          |
| Frontend      | HTML5 + CSS3 + Vanilla JS | Templates Django                    |
| Deploy        | Railway (plano pago)      | jubilant-vitality-production        |
| GitHub        | albertorosa10-spec/ordo-logistica | branch main, CI/CD ativo  |
| Ambiente dev  | WSL Ubuntu / porta 8080   |                                     |
| Claude Code   | Sonnet 4.6                | Uma tarefa por prompt               |

---

## [ESTADO ATUAL — MVP COMPLETO LOCALMENTE]

### ✅ Implementado e funcionando local

**Backend**
- Models: EmpresaOperadora, Doca, Fornecedor, Agendamento, AgendamentoDoca, LogAgendamento, NFeArquivo
- NFeArquivo: suporte a múltiplos XMLs por agendamento (até 100)
- Migrations 0001..0006 aplicadas
- Grupos Django: gestor_patio, analista_fiscal, portaria (criados via criar_grupos)
- Context processor: is_gestor_patio, is_analista_fiscal, is_portaria
- E-mail automático: console backend (dev) / Gmail SMTP (prod)

**Dashboard Gestor** (`/dashboard/`)
- HTML STANDALONE — não herda base.html
- Filtro por período: dia, semana, mês
- KPIs, tabela de agendamentos, estado das docas
- Cores: verde claro (livre), verde escuro (pré-agendada), vermelho (inativa)
- Sidebar: apenas Dashboard Pátio + Consulta Portaria

**Portal da Indústria** (`/industria/`)
- Login CNPJ + senha
- Dashboard, novo agendamento, upload múltiplos XMLs
- Detalhe agendamento, perfil, páginas por status
- Logout via POST com CSRF

**Análise Fiscal** (`/fiscal/`)
- Fila de AGUARDANDO_FISCAL
- Triagem individual: card por NFeArquivo
- Decisão por XML: aprovar ou rejeitar com motivo obrigatório
- Aprovação parcial: XMLs rejeitados deletados, aprovados mantidos
- Se todos aprovados → CONFIRMADO + código 4 dígitos
- Se algum rejeitado → PRE_AGENDADO + motivo no log

**Segregação de Acessos**
- gestor_patio: /dashboard/ + /portaria/
- analista_fiscal: /fiscal/ + /fiscal/agendamento/<pk>/
- portaria: /portaria/
- 403.html para acesso negado

**GitHub + Railway**
- Repositório: https://github.com/albertorosa10-spec/ordo-logistica
- Deploy: https://jubilant-vitality-production.up.railway.app
- CI/CD configurado (push → deploy)
- railway.toml: 1 worker, 2 threads, timeout 120

### 🔴 Problema Atual — Railway SIGKILL

```
[ERROR] Worker (pid:5) was sent SIGKILL! Perhaps out of memory?
```

Causa: workers Gunicorn consumindo mais RAM do que o alocado.
Tentativa atual: --workers 1 --threads 2 (commit c01a009)
Status: aguardando validação do novo deploy.

---

## [CICLO DE STATUS]

```
PRE_AGENDADO
    ↓ upload XML(s) + e-mail automático
AGUARDANDO_FISCAL
    ↓ analista aprova todos os XMLs em /fiscal/agendamento/<pk>/
CONFIRMADO + código 4 dígitos gerado
    ↓ gestor check-in com código
EM_PATIO → EM_DESCARGA → FINALIZADO

Rejeição parcial: XMLs rejeitados deletados → PRE_AGENDADO
Rejeição total: PRE_AGENDADO + motivo no LogAgendamento
```

---

## [REGRAS CRÍTICAS]

- dashboard_gestor.html: HTML STANDALONE, paths hardcoded, sem {% url %}
- Antigravity NÃO editar templates (traduz tags Django para português)
- DATABASE_URL: sempre postgres.railway.internal (não metro.proxy)
- E-mail: sem EMAIL_HOST_USER → console; com → Gmail SMTP
- Claude Code: Sonnet 4.6, uma tarefa por prompt, /clear entre tarefas

---

## [DEPLOY RAILWAY]

```toml
[deploy]
startCommand = "python manage.py migrate && python manage.py criar_admin && python manage.py criar_grupos && gunicorn setup.wsgi --log-file - --workers 1 --threads 2 --timeout 120 --bind 0.0.0.0:$PORT"
healthcheckPath = "/"
healthcheckTimeout = 300
restartPolicyType = "ON_FAILURE"
```

Variáveis obrigatórias:
- DATABASE_URL → postgres.railway.internal/...
- DJANGO_SUPERUSER_USERNAME/PASSWORD/EMAIL
- EMAIL_HOST_USER + EMAIL_HOST_PASSWORD (senha app Gmail 16 dígitos)

---

## [PRÓXIMOS PASSOS]

1. 🔴 Resolver SIGKILL Railway — verificar RAM alocada no serviço, tentar --preload flag
2. ⏳ Configurar e-mail Gmail no Railway (variáveis EMAIL_HOST_USER/PASSWORD)
3. ⏳ Testar fluxo completo em produção
4. ⏳ Cadastrar fornecedores piloto no admin de produção
5. ⏳ Testes com indústrias piloto

---

## [BUGS RESOLVIDOS]

- ✅ Linha tabela invisível dashboard gestor (cor herdada body)
- ✅ dashboard_gestor.html migrado para HTML standalone
- ✅ Logout indústria via POST CSRF
- ✅ Botão Aprovar → /fiscal/agendamento/<pk>/
- ✅ Cores docas por status
- ✅ Filtro de data/semana/mês no dashboard
- ✅ Upload múltiplos XMLs (até 100)
- ✅ Triagem fiscal por XML individual
- ✅ Segregação de acessos por grupo Django
- ✅ GitHub + Railway CI/CD configurados
