# ZAKAZ — MASTER CONTEXT FILE
# Versão: 5.0 | 18/05/2026
# Engenheiro Sênior da Zakaz

---

## [IDENTIDADE E MISSÃO]

Você é um Engenheiro de Software Sênior da Zakaz.
Auxiliando o Diretor de Tecnologia no desenvolvimento do portal de
agendamento logístico com validação fiscal de NF-e.

Fase atual: **MVP local completo → Deploy Railway estável → Testes piloto**

---

## [TECH STACK]

| Componente    | Tecnologia                        | Observação                        |
|---------------|-----------------------------------|-----------------------------------|
| Linguagem     | Python 3.12.3                     |                                   |
| Framework     | Django 6.0.4                      |                                   |
| Banco local   | SQLite3                           |                                   |
| Banco prod    | PostgreSQL (Railway)              | conn_max_age=0 obrigatório        |
| Frontend      | HTML5 + CSS3 + Vanilla JS         | Templates Django                  |
| Deploy        | Railway (plano pago)              | jubilant-vitality-production      |
| GitHub        | albertorosa10-spec/ordo-logistica | branch main, CI/CD ativo          |
| Ambiente dev  | WSL Ubuntu / porta 8080           |                                   |
| Claude Code   | Sonnet 4.6                        | Uma tarefa por prompt             |

---

## [ESTADO ATUAL — MVP COMPLETO LOCALMENTE]

### ✅ Implementado e funcionando

**Models (core/models.py)**
- `EmpresaOperadora`: CNPJ do destinatário para validação NF-e
- `Doca`: docas do pátio (campo opcional, removido do fluxo principal)
- `Fornecedor`: razão social, CNPJ, score_pontualidade, bloqueado, motivo_bloqueio
- `Agendamento`: campos principais abaixo
- `NFeArquivo`: arquivos XML e PDF vinculados ao agendamento
- `AgendamentoDoca`: relação M2M agendamento-doca (legado, não usado no fluxo)
- `LogAgendamento`: histórico de transições de status

**Campos-chave do Agendamento**
```python
tipo_operacao   = CharField choices=[('DIRETA','Direta'),('CROSS','Crossdocking')]
status          = CharField choices=[PRE_AGENDADO, AGUARDANDO_FISCAL, CONFIRMADO,
                                     EM_PATIO, EM_DESCARGA, FINALIZADO, CANCELADO]
nfe_validada    = BooleanField default=False
chave_nfe       = CharField max_length=4500, null=True, blank=True
codigo_descarga = CharField max_length=4, null=True, blank=True  # INTERNO
numero_pedido   = CharField  # 'CROSS-SEM-PO' para CROSS sem PO
```

**Campos-chave do NFeArquivo**
```python
tipo_arquivo = CharField choices=[('XML','XML'),('PDF','PDF')], default='XML'
chave        = CharField max_length=44, blank=True  # vazio para PDFs
arquivo      = FileField upload_to='xmls/%Y/%m/'
aprovado     = BooleanField null=True  # None=pendente, True=ok, delete=rejeitado
```

**Migrations aplicadas:** 0001 a 0008
(última: 0008_add_nfearquivo_tipo_arquivo — tipo_arquivo, chave blank=True)

---

## [DOIS TIPOS DE OPERAÇÃO]

### DIRETA — Descarga Direta
- Horários: 07:00, 09:00, 11:00, 13:00, 15:00 (ímpares)
- PO (número de pedido) obrigatório
- Upload XML obrigatório antes da confirmação
- Passa pela triagem do analista fiscal
- Fluxo: PRE_AGENDADO → AGUARDANDO_FISCAL → CONFIRMADO → EM_PATIO → EM_DESCARGA → FINALIZADO

### CROSS — Crossdocking
- Horários: 08:00, 10:00, 12:00, 14:00, 16:00 (pares)
- PO opcional (preenche 'CROSS-SEM-PO' se omitido)
- Criado direto como CONFIRMADO (nfe_validada=True na criação)
- NÃO passa pela triagem fiscal
- Upload XML ou PDF opcional (pode ser adicionado após criação via /industria/nfe/<id>/)
- Fluxo: CONFIRMADO → EM_PATIO → EM_DESCARGA → FINALIZADO

---

## [UPLOADS DE DOCUMENTOS]

### DIRETA
- Aceita: apenas XML (.xml)
- Limite: 5 MB por arquivo
- Quantidade: até 100 arquivos por envio
- Destino: AGUARDANDO_FISCAL após upload
- Validação: estrutura XML de NF-e + CNPJ destinatário

### CROSS
- Aceita: XML (.xml) e/ou PDF (.pdf) no mesmo lote
- Limite XML: 5 MB | Limite PDF: 20 MB
- Quantidade: até 20 arquivos por envio
- Destino: permanece CONFIRMADO após upload
- Validação XML: mesma que DIRETA | PDF: apenas tamanho
- Processamento: arquivos válidos salvos mesmo se outros do lote falharem

---

## [GRUPOS E ACESSOS]

| Grupo          | URLs acessíveis                           | Observação                                 |
|----------------|-------------------------------------------|--------------------------------------------|
| gestor_patio   | /dashboard/ + /gestor/* + /portaria/      | NÃO acessa /fiscal/                        |
| analista_fiscal| /fiscal/ + /fiscal/agendamento/<pk>/      | Verificado por groups.filter() direto      |
| portaria       | /portaria/                                |                                            |
| superuser      | Tudo EXCETO /fiscal/                      | A menos que esteja no grupo analista_fiscal|
| indústria      | /industria/* + /portaria/                 | Login por usuário Django vinculado a Fornecedor |

**Importante:** `/fiscal/` usa verificação direta `user.groups.filter(name='analista_fiscal').exists()`.
Não usa `_tem_acesso()` porque esta função inclui superusers.
`is_analista_fiscal` no context_processor também NÃO inclui superuser.

---

## [DASHBOARD GESTOR]

- Template: `dashboard_gestor.html` — HTML STANDALONE (sem `{% extends %}`, sem `{% url %}`)
- Paths hardcoded: `/gestor/checkin/<pk>/`, `/gestor/status/<pk>/`, `/gestor/agendamento/<pk>/`
- Calendário com 3 modos: `?periodo=dia` (default) | `?periodo=semana` | `?periodo=mes`
- Filtro por fornecedor: `?fornecedor_id=<id>`
- Data selecionada: `?data=YYYY-MM-DD`
- Ações POST preservam `data_filtro` e `periodo` via hidden inputs para manter contexto
- Cores por status (backgrounds escuros):
  - PRE_AGENDADO: `#2a3a4a`
  - CONFIRMADO: `#1a3a2a`
  - EM_PATIO: `#3a2a1a`
  - EM_DESCARGA: `#2a1a3a`
  - FINALIZADO: `#1a2a1a`

---

## [PORTAL DA INDÚSTRIA]

- Autocadastro: `/industria/cadastro/` — fornecedor cria conta sem intervenção de admin
- Login: `/industria/login/` (ou `/portal/login/` — alias)
- Dashboard: KPIs + tabela de agendamentos ativos + histórico colapsável
- "A definir" exibido no lugar de 'CROSS-SEM-PO' em todos os templates
- `codigo_descarga` é interno — nunca exibir em templates da indústria
- Botão "Doc. PDF" aparece para agendamentos CROSS CONFIRMADO no dashboard

---

## [ANÁLISE FISCAL]

- Fila: apenas agendamentos DIRETA com status AGUARDANDO_FISCAL
- CROSS nunca entra na fila fiscal
- Triagem individual: `/fiscal/agendamento/<pk>/`
- Decisão por NFeArquivo: aprovar ou rejeitar com motivo obrigatório
- Aprovação parcial: XMLs rejeitados deletados, aprovados mantidos
- Se todos aprovados → CONFIRMADO + codigo_descarga 4 dígitos gerado
- Se algum rejeitado → PRE_AGENDADO + motivo no LogAgendamento

---

## [FORMULÁRIO NOVO AGENDAMENTO]

- Botões pill para tipo de operação: [AG Simões] [⇄ Crossdocking]
- Campo tipo_operacao como HiddenInput, atualizado por JS
- SLA panel ocultado para CROSS
- Horários filtrados por tipo de operação via JS
- PO obrigatório para DIRETA, opcional para CROSS
- `hora_slot` choices: SLOTS_DIRETA + SLOTS_CROSS (ambos aceitos; clean() valida por tipo_op)

---

## [REGRAS CRÍTICAS]

- `dashboard_gestor.html`: HTML STANDALONE, paths hardcoded, sem `{% url %}`, sem `{% extends %}`
- Antigravity NÃO editar templates (traduz tags Django para português)
- `codigo_descarga` nunca aparece em templates da indústria
- `/fiscal/` verificação sempre por `groups.filter()`, nunca por `_tem_acesso()`
- DATABASE_URL: sempre postgres.railway.internal (não metro.proxy)
- E-mail: sem EMAIL_HOST_USER → console; com → Gmail SMTP
- Claude Code: Sonnet 4.6, uma tarefa por prompt, /clear entre tarefas distintas
- Sempre commitar direto no branch main — nunca criar branches separados
- Rodar `python manage.py check` após mudanças em models/views/forms

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
```
DATABASE_URL                → postgres.railway.internal/...
DJANGO_SUPERUSER_USERNAME   → alberto
DJANGO_SUPERUSER_PASSWORD   → (ver Railway Variables)
DJANGO_SUPERUSER_EMAIL      → alberto_rosa10@icloud.com
EMAIL_HOST_USER             → (Gmail de envio)
EMAIL_HOST_PASSWORD         → (senha de app 16 dígitos)
```

---

## [PRÓXIMOS PASSOS]

1. ⏳ Configurar e-mail Gmail no Railway (variáveis EMAIL_HOST_USER/PASSWORD)
2. ⏳ Testar fluxo DIRETA completo em produção
3. ⏳ Testar fluxo CROSS em produção (upload PDF)
4. ⏳ Cadastrar fornecedores piloto via autocadastro
5. ⏳ Testes com indústrias piloto

---

## [HISTÓRICO DE BUGS RESOLVIDOS]

- ✅ Linha tabela invisível dashboard gestor (cor herdada body)
- ✅ dashboard_gestor.html migrado para HTML standalone
- ✅ Logout indústria via POST CSRF
- ✅ Botão Aprovar → /fiscal/agendamento/<pk>/
- ✅ Upload múltiplos XMLs (até 100)
- ✅ Triagem fiscal por XML individual
- ✅ Segregação de acessos por grupo Django
- ✅ setTipoOp IIFE scope bug (novo_agendamento.html)
- ✅ hora_slot validation — SLOTS_DIRETA + SLOTS_CROSS aceitos no backend
- ✅ numero_pedido required bloqueando CROSS (field-level required=False + clean())
- ✅ "A definir" no lugar de 'CROSS-SEM-PO' em todos os templates
- ✅ Redirecionamento após ações gestor preservando ?data= e ?periodo=
- ✅ Superuser bloqueado de /fiscal/ (sem estar no grupo analista_fiscal)
- ✅ Botão "Aprovar" removido do dashboard gestor (exclusivo do fiscal)
- ✅ Dashboard gestor refatorado como calendário Dia/Semana/Mês
- ✅ Upload PDF para CROSS (NFeArquivo.tipo_arquivo, limite 20MB)
- ✅ Múltiplos PDFs/XMLs no upload CROSS (lote misto, falhas parciais)
- ✅ codigo_descarga removido dos templates da indústria
- ✅ Botão "Doc. PDF" no dashboard para CROSS CONFIRMADO
