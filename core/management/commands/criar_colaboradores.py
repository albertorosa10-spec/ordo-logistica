from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group

COLABORADORES = [
    {
        "username":   "fiscal",
        "first_name": "Validação",
        "last_name":  "Fiscal",
        "email":      "alberto_rosa10@icloud.com",
        "senha":      "12345678",
        "grupo":      "analista_fiscal",
    },
    {
        "username":   "patio",
        "first_name": "Operador",
        "last_name":  "Pátio",
        "email":      "alberto_rosa10@icloud.com",
        "senha":      "12345678",
        "grupo":      "gestor_patio",
    },
    {
        "username":   "gerente",
        "first_name": "Gerente",
        "last_name":  "Operações",
        "email":      "alberto_rosa10@icloud.com",
        "senha":      "12345678",
        "grupo":      "gestor_patio",
    },
    {
        "username":   "portaria",
        "first_name": "Portaria",
        "last_name":  "Zakaz",
        "email":      "alberto_rosa10@icloud.com",
        "senha":      "12345678",
        "grupo":      "portaria",
    },
]


class Command(BaseCommand):
    help = 'Cria usuários colaboradores internos do ZAKAZ e os adiciona aos grupos corretos'

    def handle(self, *args, **options):
        criados = 0
        pulados = 0
        erros   = 0

        for c in COLABORADORES:
            try:
                if User.objects.filter(username=c['username']).exists():
                    self.stdout.write(f"  ⏭  Pulando  {c['username']:<12} — já existe")
                    pulados += 1
                    continue

                user = User.objects.create_user(
                    username   = c['username'],
                    first_name = c['first_name'],
                    last_name  = c['last_name'],
                    email      = c['email'],
                    password   = c['senha'],
                    is_staff   = True,
                )

                grupo, _ = Group.objects.get_or_create(name=c['grupo'])
                user.groups.add(grupo)

                self.stdout.write(
                    self.style.SUCCESS(
                        f"  ✅ Criado   {c['username']:<12} — grupo: {c['grupo']}"
                    )
                )
                criados += 1

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"  ❌ Erro     {c['username']:<12} — {e}")
                )
                erros += 1

        self.stdout.write('')
        self.stdout.write('─' * 50)
        self.stdout.write(f'  Total na lista : {len(COLABORADORES)}')
        self.stdout.write(self.style.SUCCESS(f'  Criados        : {criados}'))
        self.stdout.write(f'  Pulados        : {pulados}')
        if erros:
            self.stdout.write(self.style.ERROR(f'  Erros          : {erros}'))
        else:
            self.stdout.write(f'  Erros          : {erros}')
        self.stdout.write('─' * 50)
