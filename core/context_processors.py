def perfis_usuario(request):
    if not request.user.is_authenticated:
        return {}
    grupos = frozenset(request.user.groups.values_list('name', flat=True))
    sup = request.user.is_superuser
    return {
        'is_gestor_patio':    sup or 'gestor_patio' in grupos,
        'is_analista_fiscal': sup or 'analista_fiscal' in grupos,
        'is_portaria':        sup or 'portaria' in grupos,
    }
