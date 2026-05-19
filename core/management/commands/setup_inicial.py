from django.core.management.base import BaseCommand
from django.core.management import call_command


class Command(BaseCommand):
    help = 'Roda criar_grade_fixa + gerar_agendamentos_fixos (30 dias)'

    def handle(self, *args, **options):
        self.stdout.write('🔧 Criando grade fixa...')
        call_command('criar_grade_fixa')
        self.stdout.write('📅 Gerando agendamentos fixos (30 dias)...')
        call_command('gerar_agendamentos_fixos', dias=30)
        self.stdout.write('✅ Setup inicial concluído.')
