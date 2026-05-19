from datetime import date, timedelta, datetime
from django.core.management.base import BaseCommand
from django.utils import timezone
from core.models import Fornecedor, Agendamento, SlotFixo

TIPO_PARA_CNPJ = {
    'HEINEKEN': '00000000000001',
    'PEPSICO':  '00000000000002',
}


class Command(BaseCommand):
    help = 'Gera agendamentos fixos para Heineken e PepsiCo nos próximos N dias'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dias', type=int, default=30,
            help='Quantos dias à frente gerar (default: 30)'
        )

    def handle(self, *args, **options):
        dias   = options['dias']
        hoje   = timezone.now().date()
        criados = 0
        pulados = 0

        # Pré-carrega fornecedores fixos
        fornecedores = {}
        for tipo, cnpj in TIPO_PARA_CNPJ.items():
            try:
                fornecedores[tipo] = Fornecedor.objects.get(cnpj=cnpj, agenda_fixa=True)
            except Fornecedor.DoesNotExist:
                self.stdout.write(
                    self.style.WARNING(f"Fornecedor {tipo} não encontrado — rode criar_grade_fixa primeiro.")
                )
                return

        slots_fixos = SlotFixo.objects.filter(
            tipo__in=['HEINEKEN', 'PEPSICO'], ativo=True
        )

        for offset in range(dias):
            dia = hoje + timedelta(days=offset)
            dow = dia.weekday()  # 0=segunda..6=domingo
            if dow >= 5:  # pula sábado e domingo
                continue

            slots_do_dia = [s for s in slots_fixos if s.dia_semana == dow]
            for slot in slots_do_dia:
                fornecedor = fornecedores[slot.tipo]
                inicio_naive = datetime(dia.year, dia.month, dia.day, slot.hora, 0)
                inicio = timezone.make_aware(inicio_naive)

                # Evita duplicatas por fornecedor + horário exato
                existe = Agendamento.objects.filter(
                    fornecedor=fornecedor,
                    inicio=inicio,
                ).exclude(status='CANCELADO').exists()

                if existe:
                    pulados += 1
                    continue

                Agendamento.objects.create(
                    fornecedor      = fornecedor,
                    inicio          = inicio,
                    numero_pedido   = f'FIXO-{dia.strftime("%Y%m%d")}-{slot.hora:02d}',
                    tipo_operacao   = 'CROSS',
                    status          = 'CONFIRMADO',
                    nfe_validada    = True,
                    qtd_itens       = 0,
                    tipo_carga      = 'PAL',
                )
                criados += 1

        self.stdout.write(
            f"✅ Agendamentos fixos: {criados} criados, {pulados} já existiam."
        )
