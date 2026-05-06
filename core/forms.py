# ==========================================
# CORE/FORMS.PY
# Zakaz — Plataforma de Agendamento
# Versão: 0.6.0
# ==========================================

from django import forms
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError
from .models import Fornecedor, Agendamento


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
        label="Arquivos XML da NF-e",
        help_text="Selecione um ou mais arquivos .xml (máx. 5 MB cada, até 100 arquivos)",
        required=False,
        widget=MultipleFileInput(attrs={
            'class': 'upload-file-input',
            'accept': '.xml,text/xml,application/xml',
            'id': 'id_arquivo_nfe',
        })
    )

    def clean_arquivo_nfe(self):
        arquivos = self.cleaned_data.get('arquivo_nfe') or []
        if not arquivos:
            raise ValidationError("Selecione pelo menos um arquivo XML.")
        if len(arquivos) > 100:
            raise ValidationError("Limite de 100 arquivos por envio.")
        for arquivo in arquivos:
            if not arquivo.name.lower().endswith('.xml'):
                raise ValidationError(f'"{arquivo.name}": apenas arquivos .xml são aceitos.')
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
        return arquivos



# ==========================================
# FORM: NOVO AGENDAMENTO
# ==========================================

# Slots de hora disponíveis: 07h às 17h, de hora em hora
SLOTS_HORA = [(f"{h:02d}:00", f"{h:02d}:00") for h in range(7, 18)]


class NovoAgendamentoForm(forms.ModelForm):
    """
    Formulário de pré-agendamento (v0.8).
    O campo `inicio` é dividido em `data` + `hora_slot` para UX controlada.
    Os dois campos são combinados no clean() e salvos como DateTimeField.
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
        label='Horário',
        choices=SLOTS_HORA,
        widget=forms.Select(attrs={
            'class': 'na-hora-select',
            'id': 'id_hora_slot',
        }),
    )

    class Meta:
        model  = Agendamento
        fields = ['numero_pedido', 'tipo_carga', 'qtd_itens', 'docas']
        # 'inicio' NÃO está em fields — é montado pelo clean()
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
            # Docas: widget padrão ocultado — o template usa botões Toggle
            'docas': forms.CheckboxSelectMultiple(attrs={
                'class': 'na-docas-hidden',
            }),
        }
        labels = {
            'numero_pedido': 'Número do Pedido de Compra (PO)',
            'tipo_carga':    'Tipo de Carga',
            'qtd_itens':     'Quantidade de Itens / Caixas',
            'docas':         'Doca(s) Solicitada(s)',
        }
        error_messages = {
            'numero_pedido': {'required': 'Informe o número do pedido.'},
            'tipo_carga':    {'required': 'Selecione o tipo de carga.'},
            'qtd_itens':     {'required': 'Informe a quantidade de itens.'},
            'docas':         {'required': 'Selecione pelo menos uma doca.'},
        }

    def __init__(self, *args, **kwargs):
        self.fornecedor = kwargs.pop('fornecedor', None)
        super().__init__(*args, **kwargs)

        from .models import Doca
        # Filtrar apenas docas ativas
        self.fields['docas'].queryset = Doca.objects.filter(ativa=True).order_by('codigo')

        # Restrição de single-doca
        if self.fornecedor and not self.fornecedor.permite_multi_doca:
            self.fields['docas'].label    = 'Doca Solicitada'
            self.fields['docas'].help_text = '⚠ Seu perfil permite apenas 1 doca por agendamento.'

    def clean(self):
        from django.utils import timezone
        from datetime import datetime, timedelta

        cleaned = super().clean()
        data     = cleaned.get('data')
        hora_str = cleaned.get('hora_slot', '07:00')

        # ----- Montar o datetime completo -----
        if data and hora_str:
            hora, minuto = map(int, hora_str.split(':'))
            # Usar timezone aware se USE_TZ=True
            try:
                inicio = timezone.make_aware(
                    datetime(data.year, data.month, data.day, hora, minuto)
                )
            except Exception:
                raise forms.ValidationError('Data ou horário inválido.')

            # ----- Validar: não permitir agendamentos no passado -----
            if inicio <= timezone.now():
                raise forms.ValidationError(
                    'O horário de agendamento deve ser no futuro.'
                )

            cleaned['inicio'] = inicio

        # ----- Validar multi-doca -----
        docas = cleaned.get('docas')
        if docas and self.fornecedor and not self.fornecedor.permite_multi_doca:
            if len(docas) > 1:
                raise forms.ValidationError(
                    'Seu perfil permite apenas 1 doca por agendamento.'
                )

        return cleaned