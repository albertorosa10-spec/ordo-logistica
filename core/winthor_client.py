# ==========================================
# CORE/WINTHOR_CLIENT.PY
# Zakaz — Integração Read-Only com WinThor (Oracle/TOTVS)
# Fase 2 — estrutura preparada, implementação pós-reunião com Diretor
# ==========================================

import logging

logger = logging.getLogger(__name__)


class WinthorClient:
    """
    Cliente read-only para consultas ao ERP WinThor (Oracle/TOTVS).

    Fase 2: métodos estruturados, implementação pendente após
    alinhamento com o Diretor e acesso ao ambiente Oracle.
    """

    def get_pedido_compra(self, numero_po: str) -> dict:
        """
        Consulta pedido de compra pelo número da PO.

        Query futura:
            SELECT NUMPED, CODFOR, DTPEDIDO, VLTOTAL
            FROM PCPEDI
            WHERE NUMPED = :numero_po

        Retorno esperado:
            dict com chaves: numped, codfor, dtpedido, vltotal
        """
        raise NotImplementedError(
            "WinthorClient.get_pedido_compra() ainda não implementado. "
            "Aguardando acesso ao ambiente Oracle/WinThor (Fase 2)."
        )

    def get_fornecedor(self, cnpj: str) -> dict:
        """
        Consulta fornecedor pelo CNPJ.

        Query futura:
            SELECT CODFORNEC, NOMEFORNEC, CGC, EMAIL
            FROM PCFORNEC
            WHERE CGC = :cnpj

        Retorno esperado:
            dict com chaves: codfornec, nomefornec, cgc, email
        """
        raise NotImplementedError(
            "WinthorClient.get_fornecedor() ainda não implementado. "
            "Aguardando acesso ao ambiente Oracle/WinThor (Fase 2)."
        )

    def get_produtos_pedido(self, numero_po: str) -> list:
        """
        Lista produtos vinculados a um pedido de compra.

        Query futura:
            SELECT CODPROD, DESCRICAO, QT, PVENDA
            FROM PCPEDI i JOIN PCPRODUT p ON i.CODPROD = p.CODPROD
            WHERE NUMPED = :numero_po

        Retorno esperado:
            lista de dicts com chaves: codprod, descricao, qt, pvenda
        """
        raise NotImplementedError(
            "WinthorClient.get_produtos_pedido() ainda não implementado. "
            "Aguardando acesso ao ambiente Oracle/WinThor (Fase 2)."
        )

    def get_nfe_by_po(self, numero_po: str) -> dict:
        """
        Consulta NF-e vinculada a um pedido no WinThor.

        Query futura:
            SELECT CHAVENFE, NUMNOTA, SERIE, DTEMISSAO
            FROM PCNFENT
            WHERE NUMPED = :numero_po

        Retorno esperado:
            dict com chaves: chavenfe, numnota, serie, dtemissao
        """
        raise NotImplementedError(
            "WinthorClient.get_nfe_by_po() ainda não implementado. "
            "Aguardando acesso ao ambiente Oracle/WinThor (Fase 2)."
        )


def validar_conexao_oracle() -> bool:
    """
    Verifica se a conexão Oracle/WinThor está configurada.

    Chamada no startup do Django para alertar quando a integração
    não estiver ativa. Retorna False enquanto a Fase 2 não for
    implementada.
    """
    logger.warning("WinThor: conexão Oracle não configurada")
    return False
