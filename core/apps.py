from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = 'core'

    def ready(self):
        # Gera agendamentos fixos para os próximos 7 dias no startup.
        # Usa thread para não bloquear o worker. Ignora silenciosamente qualquer erro.
        import threading

        def _gerar():
            try:
                from django.core.management import call_command
                call_command('gerar_agendamentos_fixos', dias=7)
            except Exception:
                pass

        t = threading.Thread(target=_gerar, daemon=True)
        t.start()
