"""
Migração de dados: popula data_agendamento (e lacuna_numero quando possível)
para todos os Agendamentos existentes que tenham inicio preenchido.
"""
from django.db import migrations
from django.utils import timezone


def populate_data_agendamento(apps, schema_editor):
    Agendamento = apps.get_model('core', 'Agendamento')
    SlotFixo    = apps.get_model('core', 'SlotFixo')

    ags = list(Agendamento.objects.filter(data_agendamento__isnull=True, inicio__isnull=False))

    # Pré-carrega todos os SlotFixo em memória para evitar N+1
    slots_por_dow_tipo = {}
    for sf in SlotFixo.objects.filter(ativo=True).order_by('hora'):
        key = (sf.dia_semana, sf.tipo)
        slots_por_dow_tipo.setdefault(key, []).append(sf.hora)

    for ag in ags:
        local_inicio = timezone.localtime(ag.inicio)
        data_ag = local_inicio.date()
        hora_ag = local_inicio.hour
        ag.data_agendamento = data_ag

        # Tenta resolver lacuna_numero
        dow = data_ag.weekday()
        tipo_slot = 'DIRETA' if ag.tipo_operacao == 'DIRETA' else 'CROSS'
        horas = sorted(slots_por_dow_tipo.get((dow, tipo_slot), []))

        if not horas:
            # Fallback hardcoded
            horas = [7, 9, 11, 13, 15] if tipo_slot == 'DIRETA' else [8, 10, 12, 14, 16]

        if hora_ag in horas:
            ag.lacuna_numero = horas.index(hora_ag) + 1
        # Se não encontrou (ex: Heineken/PepsiCo), deixa lacuna_numero=None

    if ags:
        Agendamento.objects.bulk_update(ags, ['data_agendamento', 'lacuna_numero'], batch_size=200)


def reverse_populate(apps, schema_editor):
    Agendamento = apps.get_model('core', 'Agendamento')
    Agendamento.objects.update(data_agendamento=None, lacuna_numero=None)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0013_add_lacuna_numero'),
    ]

    operations = [
        migrations.RunPython(populate_data_agendamento, reverse_populate),
    ]
