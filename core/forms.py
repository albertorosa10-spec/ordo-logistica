# ==========================================
# CORE/FORMS.PY
# Zakaz — Plataforma de Agendamento
# Versão: 0.6.0
# ==========================================

from django import forms
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError
from .models import Fornecedor, Agendamento, Cliente


# ==========================================
# WIDGET / FIELD: MÚLTIPLOS ARQUIVOS
# ==========================================

class MultipleFileInput(forms.FileInput):
    """FileInput que renderiza com multiple=True e retorna lista de arquivos.

    Django 6 bloqueia multiple=True em __init__, então injetamos via build_attrs.
    """
    def __init__(self, attrs=None):
        super().__init__(attrs=attrs)  # sem multiple aqui

    def build_attrs(self, base_attrs, extra_attrs=None):
        attrs = super().build_attrs(base_attrs, extra_attrs)
        attrs['multiple'] = True
        return attrs

    def value_from_datadict(self, data, files, name):
        return files.getlist(name)


class MultipleFileField(forms.FileField):
    """FileField que aceita e valida múltiplos arquivos."""
    widget = MultipleFileInput

    def clean(self, data, initial=None):
        single = super().clean
        if isinstance(data, (list, tuple)):
            return [single(f, initial) for f in data if f]
        return [single(data, initial)] if data else []


# ==========================================
# FORM: CADASTRO DE FORNECEDOR (ONBOARDING)
# ==========================================

class CadastroFornecedorForm(forms.Form):
    cnpj            = forms.CharField(
        max_length=14,
        label="CNPJ da Indústria",
        help_text="Apenas números (14 dígitos)",
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': '00000000000000',
            'maxlength': '14',
            'id': 'id_cnpj',
        })
    )
    razao_social    = forms.CharField(
        max_length=200,
        label="Razão Social",
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Preenchido automaticamente via CNPJ',
            'id': 'id_razao_social',
            'readonly': 'readonly',
        })
    )
    email           = forms.EmailField(
        label="E-mail Corporativo",
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'contato@empresa.com.br',
        })
    )
    senha           = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Mínimo 8 caracteres'}),
        label="Defina sua Senha",
        min_length=8,
    )
    confirmar_senha = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Repita a senha'}),
        label="Confirme a Senha",
    )

    def clean_cnpj(self):
        cnpj = self.cleaned_data.get('cnpj', '').strip()
        # Remove formatação, caso o usuário tenha digitado com pontuação
        import re
        cnpj = re.sub(r'\D', '', cnpj)

        if len(cnpj) != 14:
            raise ValidationError("CNPJ deve ter 14 dígitos numéricos.")

        if not Fornecedor.objects.filter(cnpj=cnpj).exists():
            raise ValidationError(
                "Este CNPJ ainda não foi autorizado pela Zakaz. "
                "Entre em contato com seu gestor de fornecedores."
            )

        if User.objects.filter(username=cnpj).exists():
            raise ValidationError(
                "Já existe uma conta ativa para este CNPJ. "
                "Use a opção de login ou recupere sua senha."
            )
        return cnpj

    def clean(self):
        cleaned_data = super().clean()
        senha = cleaned_data.get("senha")
        confirmar = cleaned_data.get("confirmar_senha")
        if senha and confirmar and senha != confirmar:
            raise ValidationError("As senhas não coincidem.")
        return cleaned_data


# ==========================================
# FORM: AUTOCADASTRO DE FORNECEDOR (self-service)
# ==========================================

class AutoCadastroFornecedorForm(forms.Form):
    razao_social = forms.CharField(
        max_length=200,
        label="Razão Social",
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': 'Nome da sua empresa',
        })
    )
    cnpj = forms.CharField(
        max_length=14,
        label="CNPJ",
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': '00000000000000',
            'maxlength': '14',
            'id': 'id_cnpj_autocad',
        })
    )
    email = forms.EmailField(
        label="E-mail",
        widget=forms.EmailInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': 'contato@empresa.com.br',
        })
    )
    telefone = forms.CharField(
        max_length=20,
        label="Telefone",
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': '(21) 99999-9999',
        })
    )
    senha = forms.CharField(
        min_length=8,
        label="Senha",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': 'Mínimo 8 caracteres',
        })
    )
    confirmar_senha = forms.CharField(
        label="Confirmar Senha",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': 'Repita a senha',
        })
    )

    def clean_cnpj(self):
        import re
        cnpj = re.sub(r'\D', '', self.cleaned_data.get('cnpj', ''))
        if len(cnpj) != 14:
            raise ValidationError("CNPJ deve ter 14 dígitos numéricos.")
        if Fornecedor.objects.filter(cnpj=cnpj).exists():
            raise ValidationError("Já existe um cadastro para este CNPJ. Use a opção de login.")
        if User.objects.filter(username=cnpj).exists():
            raise ValidationError("Já existe uma conta para este CNPJ. Use a opção de login.")
        return cnpj

    def clean(self):
        cleaned_data = super().clean()
        senha = cleaned_data.get('senha')
        confirmar = cleaned_data.get('confirmar_senha')
        if senha and confirmar and senha != confirmar:
            raise ValidationError("As senhas não coincidem.")
        return cleaned_data


# ==========================================
# FORM: LOGIN DA INDÚSTRIA (com CNPJ)
# ==========================================

class LoginIndustriaForm(forms.Form):
    cnpj  = forms.CharField(
        max_length=14,
        label="CNPJ",
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': '00.000.000/0000-00',
            'autofocus': True,
            'id': 'id_cnpj_login',
        })
    )
    senha = forms.CharField(
        label="Senha",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': 'Sua senha de acesso',
        })
    )

    def clean(self):
        cleaned_data = super().clean()
        cnpj  = cleaned_data.get('cnpj', '')
        senha = cleaned_data.get('senha', '')

        import re
        cnpj_limpo = re.sub(r'\D', '', cnpj)
        cleaned_data['cnpj'] = cnpj_limpo

        if cnpj_limpo and senha:
            user = authenticate(username=cnpj_limpo, password=senha)
            if user is None:
                raise ValidationError(
                    "CNPJ ou senha incorretos. Verifique seus dados e tente novamente."
                )
            if not user.is_active:
                raise ValidationError(
                    "Esta conta está desativada. Entre em contato com a Zakaz."
                )
            cleaned_data['user'] = user
        return cleaned_data


# ==========================================
# FORM: UPLOAD DE XML DA NF-e
# ==========================================

class UploadNFeXmlForm(forms.Form):
    arquivo_nfe = MultipleFileField(
        label="Arquivos da NF-e",
        help_text="XML (.xml) até 5 MB · PDF (.pdf) até 20 MB · máx. 100 arquivos",
        required=False,
        widget=MultipleFileInput(attrs={
            'class': 'upload-file-input',
            'accept': '.xml,text/xml,application/xml,.pdf,application/pdf',
            'id': 'id_arquivo_nfe',
        })
    )

    def clean_arquivo_nfe(self):
        arquivos = self.cleaned_data.get('arquivo_nfe') or []
        if not arquivos:
            raise ValidationError("Selecione pelo menos um arquivo.")
        if len(arquivos) > 100:
            raise ValidationError("Limite de 100 arquivos por envio.")

        for arquivo in arquivos:
            nome = arquivo.name.lower()
            if nome.endswith('.pdf'):
                if arquivo.size > 20 * 1024 * 1024:
                    raise ValidationError(
                        f'"{arquivo.name}": PDF muito grande ({arquivo.size // 1024} KB). Limite: 20 MB.'
                    )
            elif nome.endswith('.xml'):
                if arquivo.size > 5 * 1024 * 1024:
                    raise ValidationError(
                        f'"{arquivo.name}": arquivo muito grande ({arquivo.size // 1024} KB). Limite: 5 MB.'
                    )
                try:
                    cabecalho = arquivo.read(512).decode('utf-8', errors='ignore')
                    arquivo.seek(0)
                    if 'portalfiscal.inf.br/nfe' not in cabecalho and 'nfeProc' not in cabecalho:
                        if '<' not in cabecalho:
                            raise ValidationError(f'"{arquivo.name}": não parece ser um XML válido de NF-e.')
                except ValidationError:
                    raise
                except Exception:
                    arquivo.seek(0)
            else:
                raise ValidationError(
                    f'"{arquivo.name}": apenas arquivos .xml ou .pdf são aceitos.'
                )
        return arquivos



# ==========================================
# FORM: NOVO AGENDAMENTO
# ==========================================

# Choices abrangentes 07-18; grade real vem do SlotFixo via AJAX
SLOTS_TODOS = [(f"{h:02d}:00", f"{h:02d}:00") for h in range(7, 19)]

# Fallback quando não há grade SlotFixo configurada
HORAS_DIRETA = {7, 9, 11, 13, 15}
HORAS_CROSS  = {8, 10, 12, 14, 16}


class NovoAgendamentoForm(forms.ModelForm):
    """
    Formulário de pré-agendamento (v0.9).
    Suporta dois tipos de operação: DIRETA (horários ímpares) e CROSS (horários pares).
    Docas removidas do fluxo de agendamento.
    """

    # ----- campos de data e hora (substituem o campo inicio) -----
    data = forms.DateField(
        label='Data do Agendamento',
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'na-date-input',
            'id': 'id_data',
        }),
    )
    hora_slot = forms.ChoiceField(
        label='Lacuna',
        choices=SLOTS_TODOS,  # grade real via AJAX; clean() valida contra SlotFixo
        widget=forms.HiddenInput(attrs={'id': 'id_hora_slot'}),
    )

    class Meta:
        model  = Agendamento
        fields = ['numero_pedido', 'tipo_carga', 'qtd_itens', 'tipo_operacao']
        widgets = {
            'numero_pedido': forms.TextInput(attrs={
                'class': 'na-input',
                'placeholder': 'Ex: PO-2024-0001',
                'id': 'id_numero_pedido',
                'autocomplete': 'off',
            }),
            'tipo_carga': forms.Select(attrs={
                'class': 'na-select',
                'id': 'id_tipo_carga',
            }),
            'qtd_itens': forms.NumberInput(attrs={
                'class': 'na-input',
                'min': 1,
                'max': 9999,
                'id': 'id_qtd_itens',
            }),
            'tipo_operacao': forms.HiddenInput(attrs={
                'id': 'id_tipo_operacao',
            }),
        }
        labels = {
            'numero_pedido': 'Número do Pedido de Compra (PO)',
            'tipo_carga':    'Tipo de Carga',
            'qtd_itens':     'Quantidade de Itens / Caixas',
        }
        error_messages = {
            'numero_pedido': {'required': 'Informe o número do pedido.'},
            'tipo_carga':    {'required': 'Selecione o tipo de carga.'},
            'qtd_itens':     {'required': 'Informe a quantidade de itens.'},
        }

    def __init__(self, *args, **kwargs):
        self.fornecedor = kwargs.pop('fornecedor', None)
        super().__init__(*args, **kwargs)
        # required validado no clean() — para CROSS o PO é opcional
        self.fields['numero_pedido'].required = False

    def clean(self):
        from django.utils import timezone
        from datetime import datetime

        cleaned   = super().clean()
        data      = cleaned.get('data')
        hora_str  = cleaned.get('hora_slot', '07:00')
        tipo_op   = cleaned.get('tipo_operacao', 'DIRETA')

        # ----- numero_pedido: obrigatório para DIRETA, opcional para CROSS -----
        numero_pedido = (cleaned.get('numero_pedido') or '').strip()
        if tipo_op == 'DIRETA' and not numero_pedido:
            self.add_error('numero_pedido', 'Informe o número do pedido.')
        elif tipo_op == 'CROSS' and not numero_pedido:
            cleaned['numero_pedido'] = 'CROSS-SEM-PO'

        # ----- Montar o datetime completo -----
        if data and hora_str:
            hora, minuto = map(int, hora_str.split(':'))
            try:
                inicio = timezone.make_aware(
                    datetime(data.year, data.month, data.day, hora, minuto)
                )
            except Exception:
                raise forms.ValidationError('Data ou horário inválido.')

            if inicio <= timezone.now():
                raise forms.ValidationError(
                    'O horário de agendamento deve ser no futuro.'
                )

            # ----- Validar horário × tipo de operação (grade fixa > fallback) -----
            dow = data.weekday()
            if dow < 5:
                from .models import SlotFixo
                tipo_slot = 'DIRETA' if tipo_op == 'DIRETA' else 'CROSS'
                grade_horas = set(
                    SlotFixo.objects.filter(dia_semana=dow, tipo=tipo_slot, ativo=True)
                    .values_list('hora', flat=True)
                )
                if grade_horas and hora not in grade_horas:
                    slots_str = ', '.join(f'{h:02d}:00' for h in sorted(grade_horas))
                    raise forms.ValidationError(
                        f'Horário indisponível. Slots {tipo_op}: {slots_str}.'
                    )
                elif not grade_horas:
                    # Fallback: regras originais
                    if tipo_op == 'DIRETA' and hora not in HORAS_DIRETA:
                        slots_str = ', '.join(f'{h:02d}:00' for h in sorted(HORAS_DIRETA))
                        raise forms.ValidationError(
                            f'Agendamentos Direta usam horários: {slots_str}.'
                        )
                    if tipo_op == 'CROSS' and hora not in HORAS_CROSS:
                        slots_str = ', '.join(f'{h:02d}:00' for h in sorted(HORAS_CROSS))
                        raise forms.ValidationError(
                            f'Agendamentos Crossdocking usam horários: {slots_str}.'
                        )

            cleaned['inicio'] = inicio

        return cleaned

# ==========================================
# VÍNCULO DE PEDIDO DO CLIENTE FINAL (FISCAL)
# ==========================================

class VinculoPedidoClienteForm(forms.Form):
    cliente = forms.ModelChoiceField(
        queryset=Cliente.objects.filter(ativo=True),
        label="Cliente Final",
        empty_label="Selecione o cliente..."
    )
    numero_pedido_cliente = forms.CharField(
        max_length=50,
        label="Nº do Pedido do Cliente"
    )
    tipo_atendimento = forms.ChoiceField(
        choices=[("INTEGRAL", "Integral"), ("PARCIAL", "Parcial")],
        label="Tipo de Atendimento",
        initial="INTEGRAL"
    )
    observacao = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 2}),
        required=False,
        label="Observação (opcional)"
    )

    def clean_numero_pedido_cliente(self):
        return self.cleaned_data["numero_pedido_cliente"].strip()

