# ZAKAZ — CLAUDE.md
# Versão: 5.0 | 18/05/2026
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
ordo-logistica/
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
    ├── models.py       ← EmpresaOperadora, Doca, Fornecedor, Agendamento,
    │                      NFeArquivo, AgendamentoDoca, LogAgendamento
    ├── views.py        ← segregação por grupo; fiscal só por group check direto
    ├── forms.py        ← NovoAgendamentoForm, UploadNFeXmlForm, MultipleFileField
    ├── admin.py
    ├── integrations.py
    ├── urls.py
    ├── context_processors.py  ← is_gestor_patio, is_analista_fiscal, is_portaria
    ├── management/commands/
    │   ├── criar_admin.py
    │   └── criar_grupos.py    ← gestor_patio, analista_fiscal, portaria
    └── templates/
        ├── base.html
        ├── 403.html
        ├── dashboard_gestor.html      ← HTML STANDALONE (não extends base.html)
        ├── gestor_detalhe.html
        ├── portaria/consulta.html
        ├── fiscal/
        │   ├── dashboard.html
        │   └── aprovar.html
        └── industria/
            ├── dashboard.html
            ├── novo_agendamento.html
            ├── upload_nfe.html        ← XML e/ou PDF, lógica condicional por tipo_operacao
            ├── detalhe_agendamento.html
            ├── perfil.html
            ├── agendamentos_status.html
            └── cadastro.html          ← autocadastro de fornecedor
```

## URLS DO SISTEMA
```
/admin/                                  → Django Admin (superuser)
/cadastro/                               → Autocadastro rápido (redirect para /industria/cadastro/)
/industria/cadastro/                     → Autocadastro de fornecedor
/staff/login/                            → Login de colaboradores internos (gestor, fiscal, portaria)
/dashboard/                              → Dashboard Gestor — calendário Dia/Semana/Mês
/gestor/agendamento/<pk>/                → Detalhe do agendamento para gestor
/gestor/checkin/<pk>/                    → Entrada no Pátio (POST)
/gestor/status/<pk>/                     → Mudança de status (EM_DESCARGA, FINALIZADO) (POST)
/fiscal/                                 → Pré-entrada Fiscal (fila DIRETA)
/fiscal/agendamento/<pk>/                → Triagem individual NF-e (DIRETA)
/industria/login/                        → Login da indústria
/industria/dashboard/                    → Portal da Indústria
/industria/agendamento/novo/             → Novo agendamento (DIRETA ou CROSS)
/industria/nfe/<agendamento_id>/         → Upload XML/PDF
/industria/agendamento/<agendamento_id>/ → Detalhe agendamento (indústria)
/industria/agendamento/<id>/cancelar/    → Cancelar agendamento
/industria/perfil/                       → Perfil + logout
/industria/agendamentos/                 → Listagem por status (?status=)
/portaria/                               → Consulta portaria
/api/cnpj/<cnpj>/                        → Consulta CNPJ via API
```

## GRUPOS E ACESSOS
```
gestor_patio    → /dashboard/ + /gestor/* + /portaria/
                  NÃO acessa /fiscal/ (verificado por group check direto)
analista_fiscal → /fiscal/ + /fiscal/agendamento/<pk>/
                  Superuser bloqueado de /fiscal/ a menos que esteja no grupo
portaria        → /portaria/
superuser       → tudo EXCETO /fiscal/ (sem estar no grupo analista_fiscal)
indústria       → /industria/* + /portaria/
```

## DOIS FLUXOS DE STATUS

### DIRETA
```
PRE_AGENDADO → (upload XML obrigatório) → AGUARDANDO_FISCAL
AGUARDANDO_FISCAL → (analista fiscal aprova) → CONFIRMADO
CONFIRMADO → (check-in gestor) → EM_PATIO → EM_DESCARGA → FINALIZADO
Rejeição: volta PRE_AGENDADO + motivo no LogAgendamento
```

### CROSS (Crossdocking)
```
CONFIRMADO direto (nfe_validada=True na criação)
CONFIRMADO → (check-in gestor) → EM_PATIO → EM_DESCARGA → FINALIZADO
Upload XML/PDF é opcional, pode ser adicionado após a criação
```

## HORÁRIOS POR TIPO DE OPERAÇÃO
```
DIRETA: 07:00, 09:00, 11:00, 13:00, 15:00  (horários ímpares)
CROSS:  08:00, 10:00, 12:00, 14:00, 16:00  (horários pares)
```

## MODELOS IMPORTANTES

### Agendamento (campos-chave)
- `tipo_operacao`: 'DIRETA' (default) ou 'CROSS'
- `status`: PRE_AGENDADO / AGUARDANDO_FISCAL / CONFIRMADO / EM_PATIO / EM_DESCARGA / FINALIZADO / CANCELADO
- `nfe_validada`: BooleanField — True para CROSS na criação, True após aprovação fiscal para DIRETA
- `chave_nfe`: CharField max_length=4500 (múltiplas chaves separadas por vírgula)
- `codigo_descarga`: CharField 4 dígitos, gerado automaticamente ao CONFIRMADO (interno — não exibir para indústria)
- `numero_pedido`: 'CROSS-SEM-PO' quando CROSS sem PO informado

### NFeArquivo (campos-chave)
- `tipo_arquivo`: 'XML' (default) ou 'PDF'
- `chave`: CharField max_length=44, blank=True (PDFs não têm chave)
- `arquivo`: FileField upload_to='xmls/%Y/%m/'
- `aprovado`: BooleanField null=True (None=pendente, True=aprovado, delete=rejeitado)

### Migrations aplicadas
- 0001..0008 (última: 0008_add_nfearquivo_tipo_arquivo)

## UPLOADS DE DOCUMENTOS
```
DIRETA: apenas XML (.xml), obrigatório, até 5MB, múltiplos (até 100)
        → vai para AGUARDANDO_FISCAL após upload
CROSS:  XML (.xml) ou PDF (.pdf), opcional (pode ser adicionado após criação)
        XML: até 5MB | PDF: até 20MB | até 20 arquivos por lote
        → permanece CONFIRMADO após upload
```

## DASHBOARD GESTOR
- Calendário operacional com 3 modos: Dia / Semana / Mês
- Filtro por indústria (fornecedor) via dropdown
- Parâmetros GET: `?data=YYYY-MM-DD&periodo=dia|semana|mes`
- Ações preservam data/período via hidden inputs nos formulários POST
- Cores por status: PRE_AGENDADO=#2a3a4a, CONFIRMADO=#1a3a2a, EM_PATIO=#3a2a1a, EM_DESCARGA=#2a1a3a, FINALIZADO=#1a2a1a

## REGRAS CRÍTICAS
- `dashboard_gestor.html` é HTML STANDALONE — não usa {% extends %} nem {% url %}
- Paths hardcoded no gestor: /fiscal/agendamento/{{ ag.pk }}/, /gestor/checkin/<pk>/, etc.
- Antigravity NÃO editar templates (traduz tags Django para português)
- `codigo_descarga` é campo interno — nunca exibir em templates da indústria
- `analista_fiscal` verificado por `user.groups.filter(name='analista_fiscal').exists()` — não usar `_tem_acesso()`
- E-mail: sem EMAIL_HOST_USER → console backend; com → Gmail SMTP

## RAILWAY
- URL: jubilant-vitality-production.up.railway.app
- GitHub: albertorosa10-spec/ordo-logistica (branch main)
- CI/CD: push → deploy automático
- DATABASE_URL: postgres.railway.internal (interno)
- railway.toml: migrate + criar_admin + criar_grupos + gunicorn 1 worker 2 threads

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
1. ⏳ Configurar variáveis de e-mail no Railway
2. ⏳ Testar fluxo completo DIRETA em produção
3. ⏳ Testar fluxo CROSS em produção (upload PDF)
4. ⏳ Testes com indústrias piloto (autocadastro)

## REGRAS DO AGENTE
- Sonnet 4.6 — não trocar para Opus
- Uma tarefa por prompt
- /clear entre tarefas distintas
- Diagnóstico antes de agir
- Mudanças cirúrgicas
- Nunca sugerir Vercel
- python manage.py check após mudanças em models/views/forms
- Sempre commitar direto no branch main — nunca criar branches separados
