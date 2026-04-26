from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
import os

class Command(BaseCommand):
    help = 'Cria superusuário via variáveis de ambiente'

    def handle(self, *args, **kwargs):
        username = os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin')
        email    = os.environ.get('DJANGO_SUPERUSER_EMAIL', 'admin@ordo.com.br')
        password = os.environ.get('DJANGO_SUPERUSER_PASSWORD', '')

        if not password:
            self.stdout.write('DJANGO_SUPERUSER_PASSWORD não definida. Pulando.')
            return

        if User.objects.filter(username=username).exists():
            self.stdout.write(f'Usuário {username} já existe. Pulando.')
            return

        User.objects.create_superuser(
            username=username,
            email=email,
            password=password
        )
        self.stdout.write(f'✅ Superusuário {username} criado.')
