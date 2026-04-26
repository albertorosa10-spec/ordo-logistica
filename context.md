# ORDO LOGÍSTICA — MASTER SKILL FILE
# Versão: 2.0 | Fase: Testes Locais + E-mail + GitHub
# Engenheiro Sênior da Ordo Tecnologia Logística

---

## [IDENTIDADE E MISSÃO]

Você é um Engenheiro de Software Sênior da Ordo Tecnologia Logística.
Está auxiliando o Diretor de Tecnologia no desenvolvimento e testes de um
portal de agendamento logístico com validação fiscal (NF-e).

Fase atual: **Testes locais → E-mail automático → GitHub → Deploy Railway**

---

## [TECH STACK]

| Componente   | Tecnologia                | Observação                          |
|--------------|---------------------------|-------------------------------------|
| Linguagem    | Python 3.12               |                                     |
| Framework    | Django 6.0.4              |                                     |
| Banco local  | SQLite3                   | Fase de testes                      |
| Banco prod   | PostgreSQL (Railway)      | conn_max_age=0 obrigatório          |
| Frontend     | HTML5 + CSS3 + Vanilla JS | Templates Django, sem framework JS  |
| Deploy       | Railway                   | Não Vercel — Django é server-side   |
| Versionamento| GitHub                    | Ainda não configurado               |
| Ambiente     | WSL Ubuntu / porta 8080   |                                     |

---

## [ESTRUTURA DO PROJETO]

```
agendamento_logistico/
├── CLAUDE.md               ← contexto para Claude Code
├── context.md              ← este arquivo (Antigravity)
├── Procfile
├── railway.toml
├── runtime.txt             ← python-3.12.3
├── requirements.txt
├── manage.py
├── setup/
│   ├── settings.py         ← híbrido SQLite/PostgreSQL
│   ├── urls.py
│   └── wsgi.py
└── core/
    ├── models.py           ← v0.8.1
    ├── views.py            ← v0.8.1
    ├── forms.py            ← v0.6.0
    ├── admin.py
    ├── integrations.py     ← parser XML NF-e + BrasilAPI
    ├── urls.py             ← v0.7.0
    ├── management/commands/criar_admin.py
    └── templates/
        ├── base.html
        ├── home.html
        ├── login.html
        ├── dashboard_gestor.html   ← versão simplificada (sem CSS complexo)
        ├── portaria/consulta.html
        ├── industria/dashboard.html
        ├── industria/novo_agendamento.html
        ├── industria/upload_nfe.html
        └── onboarding/cadastro.html
```

---

## [MODELOS DE DADOS]

```
EmpresaOperadora  → CNPJ da Direta (destinatário validado nas NF-es)
Doca              → recurso físico do pátio (D01..D05)
Fornecedor        → indústria parceira (vinculada a User Django)
Agendamento       → PO + NF-e + status + timestamps
AgendamentoDoca   → ManyToMany intermediária
LogAgendamento    → auditoria de mudanças de status
```

---

## [CICLO DE STATUS]

```
PRE_AGENDADO → (upload XML + e-mail) → AGUARDANDO_FISCAL
AGUARDANDO_FISCAL → (aprovação manual admin) → CONFIRMADO
CONFIRMADO → (check-in código) → EM_PATIO
EM_PATIO → (gestor inicia) → EM_DESCARGA
EM_DESCARGA → (gestor finaliza) → FINALIZADO

Exceções: CANCELADO / NO_SHOW
```

---

## [FLUXO MVP — CONFERÊNCIA MANUAL DE NF-e]

A validação da NF-e é **manual**. Não há aprovação automática por parser.

1. Indústria cria agendamento (PO + doca + horário)
2. Indústria faz upload do XML da NF-e
3. Sistema dispara e-mail automático:
   - Para: fiscal@diretadistribuidor.com.br
   - CC: xml1@diretadistribuidor.com.br
   - Assunto: `[PO: 123456] Alpargatas S.A. — XML NF-e`
   - Anexo: arquivo XML
4. Status muda para AGUARDANDO_FISCAL
5. Setor fiscal da Direta confere manualmente e aprova no admin
6. Status muda para CONFIRMADO + código de descarga gerado
7. Gestor faz check-in com código no dashboard
8. Gestor avança: EM_PATIO → EM_DESCARGA → FINALIZADO

---

## [REGRAS DE NEGÓCIO INEGOCIÁVEIS]

### Autenticação
- Fornecedor loga com CNPJ (14 dígitos) + senha
- `Fornecedor.bloqueado` deve ser False
- `Fornecedor.user` vinculado ao User Django

### Upload de NF-e
- Aceita qualquer XML — conferência é manual
- Dispara e-mail com XML anexo imediatamente após upload
- Status passa para AGUARDANDO_FISCAL automaticamente
- Aprovação feita pelo fiscal no Django Admin

### Docas
- Conflito bloqueado: mesma doca + horário sobreposto
- Shadow buffer: 15 minutos entre agendamentos
- Multi-doca: controlado por `Fornecedor.permite_multi_doca`

### Horário Operacional
- Slots: 07h às 17h, de hora em hora
- Agendamentos não podem terminar após 18h

---

## [E-MAIL — CONFIGURAÇÃO Gmail]

```python
# settings.py
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD')  # senha de app Gmail
DEFAULT_FROM_EMAIL = os.environ.get('EMAIL_HOST_USER')
```

Variáveis de ambiente necessárias:
- `EMAIL_HOST_USER` — conta Gmail de envio
- `EMAIL_HOST_PASSWORD` — senha de app de 16 dígitos (não a senha normal)

---

## [SEED DATA OBRIGATÓRIO]

Antes de qualquer teste, cadastrar via `/admin/`:

1. **EmpresaOperadora** — CNPJ da Direta, ativa=True
2. **Docas** — D01 (CAR), D02 (TRU), D03 (CAR câmara fria), D04 (CAR), D05 (BIT)
3. **Fornecedores** — CNPJ real, bloqueado=False
4. **Users** — username=CNPJ, vinculado ao Fornecedor

---

## [DIRETRIZES DO AGENTE]

### Obrigatório
- Diagnóstico antes de agir — ler o arquivo antes de editar
- Mudanças cirúrgicas — não reescrever arquivos inteiros
- Sempre ver traceback completo antes de propor solução
- Rodar `python manage.py check` após mudanças em models/views

### Proibido
- Sugerir Vercel para hospedar Django
- Sugerir AWS S3 para armazenamento local
- Reescrever templates inteiros quando só um trecho precisa mudar
- Traduzir tags Django para português ({% for %}, {% if %}, etc.)
- Usar agentes externos para edições simples de template

### Servidor local
```bash
source venv/bin/activate
python manage.py runserver 8080
```

---

## [DEPLOY RAILWAY]

```toml
# railway.toml
[deploy]
startCommand = "python manage.py migrate && python manage.py criar_admin && gunicorn setup.wsgi --log-file - --workers 2 --bind 0.0.0.0:$PORT"
healthcheckPath = "/"
healthcheckTimeout = 300
```

**Crítico:** `DATABASE_URL` deve apontar para `postgres.railway.internal` (hostname interno).
Usar `DATABASE_PUBLIC_URL` (metro.proxy.rlwy.net) causa TCP timeout.

---

## [PRÓXIMOS PASSOS]

1. ✅ Dashboard gestor simplificado (sem CSS complexo)
2. ⏳ E-mail automático no upload de NF-e (Gmail SMTP)
3. ⏳ Testar fluxo completo local
4. ⏳ GitHub: criar repo + .gitignore + commit inicial
5. ⏳ Railway: conectar ao GitHub para CI/CD automático
6. ⏳ Testes com indústrias piloto

---

## [BUGS CONHECIDOS]

- Logout da indústria não funciona (Django exige POST, botão usa GET)
- KPI "Pré-agendados" não conta AGUARDANDO_FISCAL
- `CSRF_TRUSTED_ORIGINS` não inclui porta 8080 (só afeta formulários locais)
