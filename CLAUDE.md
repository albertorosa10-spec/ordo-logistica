# ZAKAZ — CLAUDE.md
# Versão: 4.0 | 26/04/2026
# Lido automaticamente pelo Claude Code a cada sessão

## PROJETO
Portal de agendamento logístico com validação fiscal de NF-e.
Empresa: AG Simões Direta Distribuição — Rio de Janeiro.
Dev: Alberto Rosa (Analista de Inteligência Tributária → Tax Tech)

## STACK
- Python 3.12.3 / Django 6.0.4
- SQLite3 local / PostgreSQL Railway (produção)
- HTML5 + CSS3 + Vanilla JS (templates Django)
- Deploy: Railway — nunca Vercel
- Ambiente: WSL Ubuntu / localhost:8080
- GitHub: https://github.com/albertorosa10-spec/ordo-logistica
- Railway: https://jubilant-vitality-production.up.railway.app
- Claude Code: Sonnet 4.6 — uma tarefa por prompt, /clear entre tarefas

## ESTRUTURA
```
agendamento_logistico/
├── CLAUDE.md
├── context.md
├── PLANO_TECNICO.md
├── Procfile
├── railway.toml        ← 1 worker, 2 threads, timeout 120
├── runtime.txt
├── requirements.txt
├── manage.py
├── setup/
│   ├── settings.py     ← híbrido SQLite/PostgreSQL + e-mail Gmail + context_processors
│   ├── urls.py
│   └── wsgi.py
└── core/
    ├── models.py       ← Agendamento, NFeArquivo (aprovado BooleanField null=True)
    ├── views.py        ← fiscal_dashboard, fiscal_aprovar, segregação por grupo
    ├── forms.py        ← MultipleFileField para upload múltiplo XML
    ├── admin.py
    ├── integrations.py
    ├── urls.py
    ├── context_processors.py  ← is_gestor_patio, is_analista_fiscal, is_portaria
    ├── management/commands/
    │   ├── criar_admin.py
    │   └── criar_grupos.py    ← gestor_patio, analista_fiscal, portaria
    └── templates/
        ├── base.html          ← sidebar condicional por grupo
        ├── 403.html
        ├── dashboard_gestor.html  ← HTML STANDALONE (não extends base.html)
        ├── portaria/consulta.html
        ├── fiscal/
        │   ├── dashboard.html
        │   └── aprovar.html   ← card por NFeArquivo, decisão individual
        └── industria/
            ├── dashboard.html
            ├── novo_agendamento.html
            ├── upload_nfe.html        ← múltiplos XMLs (até 100)
            ├── detalhe_agendamento.html
            ├── perfil.html
            └── agendamentos_status.html
```

## URLS DO SISTEMA
```
/admin/                          → Django Admin (superuser)
/dashboard/                      → Dashboard Gestor (grupo gestor_patio)
/fiscal/                         → Pré-entrada Fiscal (grupo analista_fiscal)
/fiscal/agendamento/<pk>/        → Triagem individual NF-e
/industria/dashboard/            → Portal Indústria
/industria/agendamento/<id>/     → Detalhe agendamento
/industria/perfil/               → Perfil + logout
/industria/agendamentos/?status= → Listagem por status
/portaria/                       → Consulta portaria
```

## GRUPOS E ACESSOS
```
gestor_patio    → /dashboard/ + /portaria/
analista_fiscal → /fiscal/ + /fiscal/agendamento/<pk>/
portaria        → /portaria/
superuser       → tudo
indústria       → /industria/* + /portaria/
```

## CICLO DE STATUS
```
PRE_AGENDADO → (upload XML) → AGUARDANDO_FISCAL
AGUARDANDO_FISCAL → (fiscal aprova) → CONFIRMADO
CONFIRMADO → (botão Entrada no Pátio) → EM_PATIO
EM_PATIO → EM_DESCARGA → FINALIZADO
Rejeição: volta PRE_AGENDADO + motivo no LogAgendamento
```

## MODELOS IMPORTANTES
- NFeArquivo: agendamento FK, chave, arquivo, aprovado (null=pending, True=ok, delete=rejected)
- Agendamento.chave_nfe: max_length=4500 (múltiplas chaves separadas por vírgula)
- Migrations aplicadas: 0001..0006

## REGRAS CRÍTICAS
- dashboard_gestor.html é HTML STANDALONE — não usa {% extends %} nem {% url %}
- Paths hardcoded: /fiscal/agendamento/{{ ag.pk }}/
- Antigravity NÃO editar templates (traduz tags Django para português)
- E-mail: sem EMAIL_HOST_USER → console backend; com → Gmail SMTP

## RAILWAY
- URL: jubilant-vitality-production.up.railway.app
- GitHub: albertorosa10-spec/ordo-logistica (branch main)
- CI/CD: push → deploy automático (verificar webhook)
- DATABASE_URL: postgres.railway.internal (interno)
- railway.toml: migrate + criar_admin + criar_grupos + gunicorn 1 worker 2 threads
- PROBLEMA ATUAL: SIGKILL (OOM) no deploy — investigar alocação de RAM no serviço

## VARIÁVEIS RAILWAY NECESSÁRIAS
```
DATABASE_URL                → postgres.railway.internal/...
DJANGO_SUPERUSER_USERNAME   → alberto
DJANGO_SUPERUSER_PASSWORD   → (ver no Railway Variables)
DJANGO_SUPERUSER_EMAIL      → alberto_rosa10@icloud.com
EMAIL_HOST_USER             → (Gmail de envio)
EMAIL_HOST_PASSWORD         → (senha de app 16 dígitos)
```

## PRÓXIMOS PASSOS
1. 🔴 Resolver SIGKILL no Railway (OOM) — verificar RAM alocada, tentar --workers 1 --threads 2
2. ⏳ Configurar variáveis de e-mail no Railway
3. ⏳ Testar fluxo completo em produção
4. ⏳ Testes com indústrias piloto

## REGRAS DO AGENTE
- Sonnet 4.6 — não trocar para Opus
- Uma tarefa por prompt
- /clear entre tarefas distintas
- Diagnóstico antes de agir
- Mudanças cirúrgicas
- Nunca sugerir Vercel
- python manage.py check após mudanças em models/views
