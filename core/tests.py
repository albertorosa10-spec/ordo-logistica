# ==========================================
# CORE/TESTS.PY
# Zakaz — Testes de integração
# Versão: 0.7.0
#
# Cobre templates, views e fluxo de negócio.
# Execute com: python manage.py test core
# ==========================================

from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from .models import Agendamento, Doca, Fornecedor


class OrdoTestBase(TestCase):
    """
    Classe base com setUp comum a todos os grupos de testes.
    Cria usuário gestor (staff), usuário/fornecedor primário,
    usuário/fornecedor secundário, uma doca e quatro agendamentos.
    """

    def setUp(self):
        self.client = Client()

        # ------ Usuário gestor (equipe Zakaz / staff) ------
        self.staff_user = User.objects.create_user(
            username='gestor_ordo',
            email='gestor@ordo.com',
            password='Gest0r@123',
            is_staff=True,
        )

        # ------ Fornecedor 1 (usuário primário dos testes) ------
        self.forn_user = User.objects.create_user(
            username='12345678000195',
            email='industria@teste.com',
            password='Forn@123',
        )
        self.fornecedor = Fornecedor.objects.create(
            cnpj='12345678000195',
            razao_social='Indústria Teste LTDA',
            user=self.forn_user,
            score_pontualidade=85.0,
        )

        # ------ Fornecedor 2 (para testar isolamento de dados) ------
        self.forn_user2 = User.objects.create_user(
            username='98765432000100',
            email='outro@teste.com',
            password='Outro@123',
        )
        self.fornecedor2 = Fornecedor.objects.create(
            cnpj='98765432000100',
            razao_social='Outra Indústria LTDA',
            user=self.forn_user2,
        )

        # ------ Doca de teste ------
        self.doca = Doca.objects.create(
            codigo='D01',
            tipo_maximo='CAR',
            ativa=True,
        )

        # ------ Agendamento PRE_AGENDADO (prazo OK - início em 48h) ------
        # prazo_vinculo_nfe = início - 24h = 24h a partir de agora → ainda válido
        self.agendamento = Agendamento.objects.create(
            fornecedor=self.fornecedor,
            numero_pedido='PO123456',
            inicio=timezone.now() + timedelta(hours=48),
            tipo_carga='PAL',
            qtd_itens=10,
            status='PRE_AGENDADO',
        )
        self.agendamento.docas.add(self.doca)

        # ------ Agendamento PRE_AGENDADO com PRAZO EXPIRADO (início no passado) ------
        # prazo_vinculo_nfe = início - 24h → muito antes de agora
        self.agendamento_expirado = Agendamento.objects.create(
            fornecedor=self.fornecedor,
            numero_pedido='PO999888',
            inicio=timezone.now() - timedelta(hours=25),
            tipo_carga='BAT',
            qtd_itens=5,
            status='PRE_AGENDADO',
        )
        self.agendamento_expirado.docas.add(self.doca)

        # ------ Agendamento CONFIRMADO com código de descarga conhecido ------
        self.agendamento_confirmado = Agendamento.objects.create(
            fornecedor=self.fornecedor,
            numero_pedido='PO777666',
            inicio=timezone.now() + timedelta(hours=48),
            tipo_carga='PAL',
            qtd_itens=3,
            status='CONFIRMADO',
            # codigo_descarga passado diretamente para ser previsível nos testes
            codigo_descarga='4321',
            nfe_validada=True,
        )
        self.agendamento_confirmado.docas.add(self.doca)

        # ------ Agendamento do Fornecedor 2 (testa isolamento de dados) ------
        self.agendamento_outro = Agendamento.objects.create(
            fornecedor=self.fornecedor2,
            numero_pedido='PO555444',
            inicio=timezone.now() + timedelta(hours=48),
            tipo_carga='FRA',
            qtd_itens=2,
        )
        self.agendamento_outro.docas.add(self.doca)


# ============================================================
# TESTES: PÁGINAS PÚBLICAS
# ============================================================

class HomePageTests(OrdoTestBase):
    """GET / → 200 + conteúdo dos 3 cards de acesso."""

    def test_home_retorna_200(self):
        resp = self.client.get('/')
        self.assertEqual(resp.status_code, 200)

    def test_home_contem_card_industria(self):
        resp = self.client.get('/')
        self.assertContains(resp, 'Portal da Indústria')

    def test_home_contem_card_gestao(self):
        resp = self.client.get('/')
        self.assertContains(resp, 'Gestão Zakaz')

    def test_home_contem_card_portaria(self):
        resp = self.client.get('/')
        self.assertContains(resp, 'Consulta Portaria')


# ============================================================
# TESTES: PORTARIA
# ============================================================

class PortariaTests(OrdoTestBase):
    """
    Testa a consulta pública de portaria (GET e POST).
    """

    def test_portaria_get_retorna_200(self):
        """GET /portaria/ deve retornar 200 sem busca ativa."""
        resp = self.client.get('/portaria/')
        self.assertEqual(resp.status_code, 200)

    def test_portaria_post_pedido_inexistente_retorna_nao_encontrado(self):
        """POST com pedido que não existe deve exibir mensagem de não encontrado."""
        resp = self.client.post('/portaria/', {'pedido': 'PEDIDOINEXISTENTE'})
        self.assertEqual(resp.status_code, 200)
        # Verifica que o contexto não retornou agendamento e que buscou=True
        self.assertIsNone(resp.context['agendamento'])
        self.assertTrue(resp.context['buscou'])
        # Template deve mostrar mensagem de não encontrado
        self.assertContains(resp, 'NÃO ENCONTRADO')

    def test_portaria_post_pedido_existente_retorna_dados(self):
        """POST com número de pedido existente deve retornar os dados do agendamento."""
        resp = self.client.post('/portaria/', {'pedido': self.agendamento.numero_pedido})
        self.assertEqual(resp.status_code, 200)
        self.assertIsNotNone(resp.context['agendamento'])
        self.assertEqual(resp.context['agendamento'].pk, self.agendamento.pk)

    def test_portaria_post_pedido_existente_exibe_numero_pedido(self):
        """A resposta deve conter o número do pedido do agendamento encontrado."""
        resp = self.client.post('/portaria/', {'pedido': self.agendamento.numero_pedido})
        self.assertContains(resp, self.agendamento.numero_pedido)


# ============================================================
# TESTES: DASHBOARD DA INDÚSTRIA
# ============================================================

class DashboardIndustriaTests(OrdoTestBase):
    """
    Testa o dashboard exclusivo do fornecedor.
    Acessível via /industria/dashboard/ (alias de /portal/dashboard/).
    """

    def test_dashboard_industria_sem_login_redireciona(self):
        """Sem autenticação deve redirecionar para a tela de login."""
        resp = self.client.get('/industria/dashboard/')
        # Deve ser 302 redirect
        self.assertEqual(resp.status_code, 302)
        # URL de destino deve conter o LOGIN_URL configurado
        self.assertIn('/portal/login/', resp.url)

    def test_dashboard_industria_com_login_retorna_200(self):
        """Com fornecedor logado deve retornar HTTP 200."""
        self.client.login(username=self.forn_user.username, password='Forn@123')
        resp = self.client.get('/industria/dashboard/')
        self.assertEqual(resp.status_code, 200)

    def test_dashboard_industria_mostra_agendamento_do_proprio_fornecedor(self):
        """Deve exibir o número do pedido do fornecedor logado."""
        self.client.login(username=self.forn_user.username, password='Forn@123')
        resp = self.client.get('/industria/dashboard/')
        self.assertContains(resp, self.agendamento.numero_pedido)

    def test_dashboard_industria_nao_mostra_agendamento_de_outro_fornecedor(self):
        """
        Isolamento: o dashboard não deve mostrar agendamentos
        de outros fornecedores.
        """
        self.client.login(username=self.forn_user.username, password='Forn@123')
        resp = self.client.get('/industria/dashboard/')
        self.assertNotContains(resp, self.agendamento_outro.numero_pedido)


# ============================================================
# TESTES: DASHBOARD DO GESTOR
# ============================================================

class DashboardGestorTests(OrdoTestBase):
    """Testa o dashboard operacional da equipe Zakaz (/dashboard/)."""

    def test_dashboard_gestor_sem_login_redireciona(self):
        """Sem autenticação deve redirecionar para login."""
        resp = self.client.get('/dashboard/')
        self.assertEqual(resp.status_code, 302)

    def test_dashboard_gestor_com_staff_retorna_200(self):
        """Usuário staff deve acessar o dashboard sem restrições."""
        self.client.login(username=self.staff_user.username, password='Gest0r@123')
        resp = self.client.get('/dashboard/')
        self.assertEqual(resp.status_code, 200)

    def test_dashboard_gestor_com_fornecedor_redireciona(self):
        """
        Fornecedor (não-staff) tentando acessar o dashboard do gestor
        deve ser redirecionado para o dashboard da indústria.
        """
        self.client.login(username=self.forn_user.username, password='Forn@123')
        resp = self.client.get('/dashboard/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('portal/dashboard', resp.url)


# ============================================================
# TESTES: CHECK-IN DO GESTOR
# ============================================================

class CheckinGestorTests(OrdoTestBase):
    """
    Testa o fluxo de check-in via /gestor/checkin/<id>/.
    O agendamento `agendamento_confirmado` começa com status CONFIRMADO.
    """

    def test_checkin_com_codigo_correto_muda_status_para_em_patio(self):
        """POST com código válido deve mudar status para EM_PATIO."""
        self.client.login(username=self.staff_user.username, password='Gest0r@123')

        resp = self.client.post(
            f'/gestor/checkin/{self.agendamento_confirmado.pk}/',
            {'codigo_descarga': self.agendamento_confirmado.codigo_descarga},
        )

        # Deve redirecionar para o dashboard após o check-in
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/dashboard/', resp.url)

        # Status deve ter mudado para EM_PATIO
        self.agendamento_confirmado.refresh_from_db()
        self.assertEqual(self.agendamento_confirmado.status, 'EM_PATIO')

    def test_checkin_com_codigo_errado_nao_muda_status(self):
        """POST com código errado não deve alterar o status do agendamento."""
        self.client.login(username=self.staff_user.username, password='Gest0r@123')

        resp = self.client.post(
            f'/gestor/checkin/{self.agendamento_confirmado.pk}/',
            {'codigo_descarga': '0000'},   # código errado
        )

        # Deve redirecionar para o dashboard com mensagem de erro
        self.assertEqual(resp.status_code, 302)

        # Status deve permanecer CONFIRMADO
        self.agendamento_confirmado.refresh_from_db()
        self.assertEqual(self.agendamento_confirmado.status, 'CONFIRMADO')

    def test_checkin_sem_permissao_de_staff_redireciona(self):
        """Fornecedor tentando fazer check-in deve ser bloqueado."""
        self.client.login(username=self.forn_user.username, password='Forn@123')
        resp = self.client.post(
            f'/gestor/checkin/{self.agendamento_confirmado.pk}/',
            {'codigo_descarga': self.agendamento_confirmado.codigo_descarga},
        )
        self.assertEqual(resp.status_code, 302)
        # Status não deve mudar
        self.agendamento_confirmado.refresh_from_db()
        self.assertEqual(self.agendamento_confirmado.status, 'CONFIRMADO')


# ============================================================
# TESTES: VÍNCULO DE NF-e
# ============================================================

class VincularNFeTests(OrdoTestBase):
    """
    Testa o fluxo de vínculo de NF-e simplificado (/industria/nfe/<id>/).

    O mock do Winthor (integrations.py) aprova chaves terminadas em '123'.
    Chave de 44 dígitos válida para testes: '1' * 41 + '123'
    """

    CHAVE_VALIDA = '1' * 41 + '123'   # 44 dígitos, termina em '123'
    CHAVE_INVALIDA = '9' * 41 + '999' # 44 dígitos, NÃO termina em '123'

    def test_get_nfe_prazo_expirado_exibe_formulario_bloqueado(self):
        """
        GET na view de vínculo com prazo expirado deve renderizar
        o estado de formulário bloqueado (sem o botão de submit).
        """
        self.client.login(username=self.forn_user.username, password='Forn@123')
        resp = self.client.get(f'/industria/nfe/{self.agendamento_expirado.pk}/')

        self.assertEqual(resp.status_code, 200)
        # O contexto deve marcar prazo_expirado como True
        self.assertTrue(resp.context['prazo_expirado'])
        # O template deve conter a mensagem de prazo expirado
        self.assertContains(resp, 'Prazo Expirado')

    def test_get_nfe_prazo_valido_exibe_formulario_ativo(self):
        """GET com prazo válido deve mostrar o formulário de vínculo ativo."""
        self.client.login(username=self.forn_user.username, password='Forn@123')
        resp = self.client.get(f'/industria/nfe/{self.agendamento.pk}/')

        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.context['prazo_expirado'])

    def test_post_chave_valida_vincula_nfe_e_redireciona(self):
        """
        POST com chave de 44 dígitos terminada em '123' (aprovada pelo mock
        do Winthor) deve vincular a NF-e, mudar status para CONFIRMADO
        e redirecionar para o dashboard.
        """
        self.client.login(username=self.forn_user.username, password='Forn@123')

        resp = self.client.post(
            f'/industria/nfe/{self.agendamento.pk}/',
            {'chave_nfe': self.CHAVE_VALIDA},
        )

        # Deve redirecionar após vincular com sucesso
        self.assertEqual(resp.status_code, 302)
        self.assertIn('dashboard', resp.url)

        # NF-e deve estar validada e status deve ser CONFIRMADO
        self.agendamento.refresh_from_db()
        self.assertTrue(self.agendamento.nfe_validada)
        self.assertEqual(self.agendamento.status, 'CONFIRMADO')
        self.assertEqual(self.agendamento.chave_nfe, self.CHAVE_VALIDA)

    def test_post_chave_invalida_nao_vincula_nfe(self):
        """
        POST com chave não aprovada pelo mock do Winthor deve
        manter o status PRE_AGENDADO e renderizar a página com erro.
        """
        self.client.login(username=self.forn_user.username, password='Forn@123')

        resp = self.client.post(
            f'/industria/nfe/{self.agendamento.pk}/',
            {'chave_nfe': self.CHAVE_INVALIDA},
        )

        # Deve renderizar a mesma página (não redirecionar)
        self.assertEqual(resp.status_code, 200)

        # NF-e não deve ter sido vinculada
        self.agendamento.refresh_from_db()
        self.assertFalse(self.agendamento.nfe_validada)
        self.assertEqual(self.agendamento.status, 'PRE_AGENDADO')

    def test_post_nfe_com_prazo_expirado_nao_vincula(self):
        """POST em agendamento com prazo expirado não deve alterar o estado."""
        self.client.login(username=self.forn_user.username, password='Forn@123')

        resp = self.client.post(
            f'/industria/nfe/{self.agendamento_expirado.pk}/',
            {'chave_nfe': self.CHAVE_VALIDA},
        )

        # Deve renderizar a página (não redirecionar com sucesso)
        # ou redirecionar com mensagem de erro
        self.agendamento_expirado.refresh_from_db()
        self.assertFalse(self.agendamento_expirado.nfe_validada)

    def test_acesso_nfe_de_outro_fornecedor_retorna_404(self):
        """
        Fornecedor não deve conseguir acessar a NF-e de agendamento
        que não é dele (deve receber 404).
        """
        self.client.login(username=self.forn_user2.username, password='Outro@123')
        resp = self.client.get(f'/industria/nfe/{self.agendamento.pk}/')
        # get_object_or_404 garante 404 se o fornecedor não bater
        self.assertEqual(resp.status_code, 404)
