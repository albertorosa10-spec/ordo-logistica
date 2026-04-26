# ORDO LOGÍSTICA — CLAUDE.md
# Lido automaticamente pelo Claude Code a cada sessão

## PROJETO
Portal de agendamento logístico com validação fiscal de NF-e.
Empresa: AG Simões Direta Distribuição — Rio de Janeiro.
Dev: Alberto Rosa (Analista de Inteligência Tributária → Tax Tech)

## STACK
- Python 3.12.3 / Django 6.0.4
- SQLite3 local (testes) / PostgreSQL Railway (produção)
- HTML5 + CSS3 + Vanilla JS (templates Django)
- Deploy: Railway — não Vercel (Django é server-side)
- Ambiente: WSL Ubuntu / localhost:8080

## ESTRUTURA
```
agendamento_logistico/
├── CLAUDE.md           ← este arquivo
├── context.md          ← skill file para Antigravity
├── Procfile
├── railway.toml
├── runtime.txt         ← python-3.12.3
├── requirements.txt
├── manage.py
├── setup/
│   ├── settings.py     ← híbrido SQLite/PostgreSQL
│   ├── urls.py
│   └── wsgi.py
└── core/
    ├── models.py       ← v0.8.1
    ├── views.py        ← v0.8.1
    ├── forms.py        ← v0.6.0
    ├── admin.py
    ├── integrations.py ← parser XML NF-e + BrasilAPI
    ├── urls.py
    ├── management/commands/criar_admin.py
    └── templates/
        ├── base.html
        ├── home.html
        ├── login.html
        ├── dashboard_gestor.html   ← dashboard do gestor (simplificado)
        ├── portaria/consulta.html
        ├── industria/dashboard.html
        ├── industria/novo_agendamento.html
        ├── industria/upload_nfe.html
        └── onboarding/cadastro.html
```

## MODELOS PRINCIPAIS
- `EmpresaOperadora` — CNPJ da Direta (destinatário das NF-es)
- `Doca` — recurso físico do pátio
- `Fornecedor` — indústria parceira, vinculada a User Django
- `Agendamento` — PO + NF-e + status + timestamps
- `AgendamentoDoca` — ManyToMany intermediária
- `LogAgendamento` — auditoria de status

## CICLO DE STATUS
```
PRE_AGENDADO → CONFIRMADO → EM_PATIO → EM_DESCARGA → FINALIZADO
AGUARDANDO_FISCAL (triagem manual quando NF-e tem divergência)
CANCELADO / NO_SHOW
```

## REGRAS DE NEGÓCIO CRÍTICAS
- Fornecedor loga com CNPJ (14 dígitos) + senha
- Upload XML → e-mail automático para fiscal@diretadistribuidor.com.br
- Conferência da NF-e é MANUAL pelo setor fiscal (não automática)
- Prazo NF-e: 24h antes da descarga
- Mock Winthor: chaves terminando em `123` aprovadas
- Shadow buffer: 15min entre agendamentos
- Horário operacional: 07h-18h

## FLUXO MVP (simplificado)
1. Indústria agenda (PO + doca + horário)
2. Indústria faz upload do XML da NF-e
3. Sistema dispara e-mail para fiscal@ com XML anexo
4. Fiscal confere manualmente e aprova no admin
5. Gestor faz check-in com código de descarga
6. Gestor avança status: EM_PATIO → EM_DESCARGA → FINALIZADO

## SERVIDOR LOCAL
```bash
cd ~/agendamento_logistico
source venv/bin/activate
python manage.py runserver 8080
# Acessa: http://127.0.0.1:8080
```

## SEED DATA NECESSÁRIO (admin)
1. EmpresaOperadora — CNPJ da Direta
2. Docas — D01 a D05
3. Fornecedores — com Users vinculados (username = CNPJ)

## DEPLOY RAILWAY
- URL: jubilant-vitality-production.up.railway.app
- DATABASE_URL: postgres.railway.internal (interno, não público)
- conn_max_age=0 obrigatório para evitar timeout
- railway.toml define startCommand com migrate + criar_admin + gunicorn

## PRÓXIMOS PASSOS (em ordem)
1. Substituir dashboard_gestor.html pela versão simplificada
2. Implementar disparo de e-mail no upload de NF-e (Gmail SMTP)
3. Testar fluxo completo: agendamento → upload → e-mail → aprovação → check-in
4. Criar repositório GitHub + conectar ao Railway (CI/CD)
5. Testes com indústrias piloto

## REGRAS DO AGENTE
- Editar arquivos diretamente — não gerar para copiar/colar
- Mudanças cirúrgicas — não reescrever arquivos inteiros sem necessidade
- Diagnóstico antes de agir — ver o arquivo antes de editar
- Nunca sugerir Vercel para Django
- Sempre rodar `python manage.py check` após alterações em models/views
- Se der erro, ler o traceback completo antes de propor solução
