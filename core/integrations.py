# ==========================================
# CORE/INTEGRATIONS.PY
# Ordo Logística — Plataforma de Agendamento
# Versão: 0.6.0
#
# Integrações externas:
#   - BrasilAPI: consulta CNPJ na RFB
#   - Parser XML: valida NF-e (44 dígitos + CNPJ destinatário)
#   - Winthor (mock): consulta nota e pedido
# ==========================================

import re
import requests
import xml.etree.ElementTree as ET


# ==========================================
# BRASILAPI — CONSULTA CNPJ (RFB)
# ==========================================

def consultar_cnpj_brasilapi(cnpj: str) -> dict | None:
    """
    Consulta dados públicos do CNPJ diretamente na Receita Federal
    via BrasilAPI (gratuito, sem autenticação, sem limite restritivo).

    Retorna dict com:
        razao_social  : str
        nome_fantasia : str
        situacao      : str  (ex: 'ATIVA')
        uf            : str
        municipio     : str

    Retorna None em caso de CNPJ inválido ou erro de rede.

    API: https://brasilapi.com.br/api/cnpj/v1/{cnpj}
    """
    cnpj_limpo = re.sub(r'\D', '', cnpj)
    if len(cnpj_limpo) != 14:
        return None

    url = f"https://brasilapi.com.br/api/cnpj/v1/{cnpj_limpo}"
    try:
        resp = requests.get(url, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            return {
                'razao_social':  data.get('razao_social', '').strip(),
                'nome_fantasia': data.get('nome_fantasia', '').strip(),
                'situacao':      data.get('descricao_situacao_cadastral', ''),
                'uf':            data.get('uf', ''),
                'municipio':     data.get('municipio', ''),
            }
        # 404 = CNPJ não encontrado; outros = erro da API
        return None
    except requests.RequestException:
        return None


# ==========================================
# PARSER XML — VALIDAÇÃO DE NF-e
# ==========================================

# Namespace padrão NF-e (NFe 4.0)
_NS = {'nfe': 'http://www.portalfiscal.inf.br/nfe'}

def validar_nfe_xml(arquivo_xml, cnpj_destinatario_esperado: str) -> tuple[str | None, bool, str]:
    """
    Faz o parse do XML da NF-e e valida:
      1. Extrai a chave de 44 dígitos (atributo Id da tag infNFe)
      2. Verifica se o CNPJ do destinatário bate com cnpj_destinatario_esperado
         (digits 21-34 da chave, ou diretamente via tag <dest><CNPJ>)

    Parâmetros:
        arquivo_xml               : InMemoryUploadedFile (request.FILES)
        cnpj_destinatario_esperado: str com 14 dígitos numéricos

    Retorna tupla: (chave_44_digitos | None, valido: bool, mensagem: str)
    """
    cnpj_esperado_limpo = re.sub(r'\D', '', cnpj_destinatario_esperado)

    try:
        conteudo = arquivo_xml.read()
        arquivo_xml.seek(0)  # resetar ponteiro para uso posterior
        root = ET.fromstring(conteudo)
    except ET.ParseError as e:
        return None, False, f"XML malformado: {e}"

    # ----- Extrair chave de 44 dígitos -----
    # Tentativa 1: atributo Id da tag <infNFe Id="NFe{chave44}">
    inf_nfe = root.find('.//nfe:infNFe', _NS) or root.find('.//{http://www.portalfiscal.inf.br/nfe}infNFe')
    chave = None

    if inf_nfe is not None:
        id_attr = inf_nfe.get('Id', '')
        # Remove prefixo "NFe" se existir
        chave = re.sub(r'^NFe', '', id_attr)

    # Tentativa 2: tag <chNFe>
    if not chave or len(chave) != 44:
        ch_tag = root.find('.//nfe:chNFe', _NS) or root.find('.//{http://www.portalfiscal.inf.br/nfe}chNFe')
        if ch_tag is not None and ch_tag.text:
            chave = ch_tag.text.strip()

    if not chave or len(chave) != 44 or not chave.isdigit():
        return chave, False, (
            f"Chave NF-e inválida (encontrado: '{chave}'). "
            "A chave deve ter exatamente 44 dígitos numéricos."
        )

    # ----- Extrair CNPJ do destinatário -----
    # Método primário: tag <dest><CNPJ>
    cnpj_dest_tag = (
        root.find('.//nfe:dest/nfe:CNPJ', _NS)
        or root.find('.//{http://www.portalfiscal.inf.br/nfe}dest/{http://www.portalfiscal.inf.br/nfe}CNPJ')
    )
    cnpj_dest_xml = None
    if cnpj_dest_tag is not None and cnpj_dest_tag.text:
        cnpj_dest_xml = cnpj_dest_tag.text.strip()

    # Método fallback: extrair da própria chave (posições 6-19, base 0)
    # Estrutura chave 44: cUF(2) AAMM(4) CNPJ_emitente(14) mod(2) série(3) nNF(9) tpEmis(1) cNF(8) cDV(1)
    cnpj_emitente_chave = chave[6:20]

    # A Ordo valida o CNPJ do DESTINATÁRIO (quem recebe a mercadoria)
    if cnpj_dest_xml:
        cnpj_verificado = re.sub(r'\D', '', cnpj_dest_xml)
        fonte = "XML (<dest><CNPJ>)"
    else:
        # Fallback: usa emitente (comportamento conservador)
        cnpj_verificado = cnpj_emitente_chave
        fonte = "chave (CNPJ emitente, fallback)"

    if cnpj_verificado != cnpj_esperado_limpo:
        return chave, False, (
            f"CNPJ do destinatário na NF-e ({cnpj_verificado} via {fonte}) "
            f"não corresponde ao CNPJ da Empresa Operadora ({cnpj_esperado_limpo}). "
            "Verifique se a nota foi emitida corretamente contra a AG Simões."
        )

    return chave, True, "NF-e validada com sucesso."


def extrair_resumo_nfe(arquivo_xml) -> dict:
    """
    Extrai metadados de exibição da NF-e após validação bem-sucedida.

    Retorna dict com:
        chave         : str (44 dígitos)
        numero_nf     : str
        serie         : str
        valor_total   : str (formatado como moeda BRL)
        data_emissao  : str (dd/mm/YYYY HH:MM)
        cnpj_emit     : str
        razao_emit    : str
        cnpj_dest     : str
    """
    resultado = {
        'chave': None, 'numero_nf': '—', 'serie': '—',
        'valor_total': '—', 'data_emissao': '—',
        'cnpj_emit': '—', 'razao_emit': '—', 'cnpj_dest': '—',
    }
    try:
        conteudo = arquivo_xml.read()
        arquivo_xml.seek(0)
        root = ET.fromstring(conteudo)
    except ET.ParseError:
        return resultado

    def _find(xpath_nfe, xpath_raw):
        el = root.find(xpath_nfe, _NS) or root.find(xpath_raw)
        return el.text.strip() if el is not None and el.text else None

    # Chave 44
    inf_nfe = root.find('.//nfe:infNFe', _NS) or root.find('.//{http://www.portalfiscal.inf.br/nfe}infNFe')
    if inf_nfe is not None:
        resultado['chave'] = re.sub(r'^NFe', '', inf_nfe.get('Id', ''))

    # Número e série
    resultado['numero_nf'] = _find('.//nfe:ide/nfe:nNF', './/{http://www.portalfiscal.inf.br/nfe}nNF') or '—'
    resultado['serie']     = _find('.//nfe:ide/nfe:serie', './/{http://www.portalfiscal.inf.br/nfe}serie') or '—'

    # Data de emissão (NF-e 4.0 usa dhEmi; NF-e 3.x usa dEmi)
    data_raw = (
        _find('.//nfe:ide/nfe:dhEmi', './/{http://www.portalfiscal.inf.br/nfe}dhEmi') or
        _find('.//nfe:ide/nfe:dEmi',  './/{http://www.portalfiscal.inf.br/nfe}dEmi')
    )
    if data_raw:
        # Formatos possíveis: 2024-01-15T10:30:00-03:00 ou 2024-01-15
        try:
            from datetime import datetime
            fmt = '%Y-%m-%dT%H:%M:%S%z' if 'T' in data_raw else '%Y-%m-%d'
            dt = datetime.strptime(data_raw[:19], fmt if 'T' not in data_raw else '%Y-%m-%dT%H:%M:%S')
            resultado['data_emissao'] = dt.strftime('%d/%m/%Y %H:%M')
        except ValueError:
            resultado['data_emissao'] = data_raw[:10]

    # Valor total
    vnf = _find('.//nfe:total/nfe:ICMSTot/nfe:vNF', './/{http://www.portalfiscal.inf.br/nfe}vNF')
    if vnf:
        try:
            resultado['valor_total'] = f"R$ {float(vnf):,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        except ValueError:
            resultado['valor_total'] = vnf

    # Emitente
    resultado['cnpj_emit']  = _find('.//nfe:emit/nfe:CNPJ',  './/{http://www.portalfiscal.inf.br/nfe}emit/{http://www.portalfiscal.inf.br/nfe}CNPJ') or '—'
    resultado['razao_emit'] = (
        _find('.//nfe:emit/nfe:xNome', './/{http://www.portalfiscal.inf.br/nfe}xNome') or '—'
    )

    # Destinatário
    resultado['cnpj_dest']  = _find('.//nfe:dest/nfe:CNPJ', './/{http://www.portalfiscal.inf.br/nfe}dest/{http://www.portalfiscal.inf.br/nfe}CNPJ') or '—'

    return resultado



# ==========================================
# WINTHOR — MOCK (substituir em produção)
# ==========================================

def consultar_nota_winthor(chave_nfe):
    """
    Verifica se a NF-e existe e está liberada no Winthor.

    MOCK — Em produção substituir por:
    SELECT COUNT(*) FROM PCNFBASE
    WHERE CHAVENFE = :chave
    AND POSICAO = 'L'  -- 'L' = Liberada
    """
    if not chave_nfe:
        return False
    # Mock: chaves terminadas em '123' são válidas
    return chave_nfe.endswith('123')


def consultar_pedido_winthor(numero_pedido):
    """
    Verifica se o Pedido de Compra existe e está aberto no Winthor.

    MOCK — Em produção substituir por:
    SELECT COUNT(*) FROM PCPEDIDO
    WHERE NUMPED = :numero
    AND POSICAO NOT IN ('F', 'C')  -- F=Fechado, C=Cancelado
    """
    if not numero_pedido:
        return False
    # Mock: qualquer pedido com 6+ dígitos é válido
    return len(str(numero_pedido)) >= 6


def consultar_restricao_fornecedor(cnpj):
    """
    Verifica se o CNPJ possui restrição de recebimento no Winthor.

    MOCK — Em produção substituir por:
    SELECT BLOQUEIO FROM PCFORNEC
    WHERE CGC = :cnpj
    """
    if not cnpj:
        return True  # sem CNPJ = bloqueado por precaução
    # Mock: CNPJs terminados em '0000' estão bloqueados
    return cnpj.endswith('0000')
