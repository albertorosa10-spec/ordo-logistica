from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group


class Command(BaseCommand):
    help = 'Cria os grupos de perfil do sistema (gestor_patio, analista_fiscal, portaria)'

    def handle(self, *args, **options):
        for nome in ('gestor_patio', 'analista_fiscal', 'portaria'):
            _, criado = Group.objects.get_or_create(name=nome)
            if criado:
                self.stdout.write(self.style.SUCCESS(f'Grupo "{nome}" criado.'))
            else:
                self.stdout.write(f'Grupo "{nome}" já existe.')
