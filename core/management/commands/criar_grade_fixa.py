from django.core.management.base import BaseCommand
from core.models import Fornecedor, SlotFixo

# Grade por dia da semana: {dia: [(hora, tipo), ...]}
GRADE = {
    # Segunda=0, Quarta=2, Sexta=4
    0: [(7,'HEINEKEN'),(8,'HEINEKEN'),(9,'HEINEKEN'),(10,'HEINEKEN'),
        (11,'PEPSICO'),
        (12,'CROSS'),(13,'CROSS'),(14,'CROSS'),
        (15,'DIRETA'),(16,'DIRETA')],
    2: [(7,'HEINEKEN'),(8,'HEINEKEN'),(9,'HEINEKEN'),(10,'HEINEKEN'),
        (11,'PEPSICO'),
        (12,'CROSS'),(13,'CROSS'),(14,'CROSS'),
        (15,'DIRETA'),(16,'DIRETA')],
    4: [(7,'HEINEKEN'),(8,'HEINEKEN'),(9,'HEINEKEN'),(10,'HEINEKEN'),
        (11,'PEPSICO'),
        (12,'CROSS'),(13,'CROSS'),(14,'CROSS'),
        (15,'DIRETA'),(16,'DIRETA')],
    # Terça=1, Quinta=3
    1: [(7,'DIRETA'),(8,'DIRETA'),(9,'DIRETA'),
        (10,'CROSS'),(11,'CROSS'),(12,'CROSS'),(13,'CROSS'),
        (14,'DIRETA'),(15,'DIRETA'),(16,'DIRETA'),(17,'DIRETA'),(18,'DIRETA')],
    3: [(7,'DIRETA'),(8,'DIRETA'),(9,'DIRETA'),
        (10,'CROSS'),(11,'CROSS'),(12,'CROSS'),(13,'CROSS'),
        (14,'DIRETA'),(15,'DIRETA'),(16,'DIRETA'),(17,'DIRETA'),(18,'DIRETA')],
}


class Command(BaseCommand):
    help = 'Cria fornecedores de grade fixa (Heineken, PepsiCo) e popula SlotFixo'

    def handle(self, *args, **options):
        # --- Fornecedores fixos ---
        heineken, criado = Fornecedor.objects.get_or_create(
            cnpj='00000000000001',
            defaults={
                'razao_social': 'Heineken Brasil',
                'agenda_fixa':  True,
                'cor_marca':    '#006B3F',
            }
        )
        if criado or not heineken.agenda_fixa:
            heineken.agenda_fixa = True
            heineken.cor_marca   = '#006B3F'
            heineken.save(update_fields=['agenda_fixa', 'cor_marca'])
            self.stdout.write(f"{'✅ Criado' if criado else '🔄 Atualizado'}: {heineken}")

        pepsico, criado = Fornecedor.objects.get_or_create(
            cnpj='00000000000002',
            defaults={
                'razao_social': 'PepsiCo Brasil',
                'agenda_fixa':  True,
                'cor_marca':    '#004B93',
            }
        )
        if criado or not pepsico.agenda_fixa:
            pepsico.agenda_fixa = True
            pepsico.cor_marca   = '#004B93'
            pepsico.save(update_fields=['agenda_fixa', 'cor_marca'])
            self.stdout.write(f"{'✅ Criado' if criado else '🔄 Atualizado'}: {pepsico}")

        # --- Slots fixos ---
        criados   = 0
        existentes = 0
        for dia, slots in GRADE.items():
            for hora, tipo in slots:
                _, novo = SlotFixo.objects.get_or_create(
                    dia_semana=dia,
                    hora=hora,
                    defaults={'tipo': tipo, 'ativo': True},
                )
                if novo:
                    criados += 1
                else:
                    existentes += 1

        self.stdout.write(
            f"✅ Grade fixa: {criados} slots criados, {existentes} já existiam."
        )
