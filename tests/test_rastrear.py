"""Testa o decorator `_rastrear` isoladamente: ele decide o que conta como
'ação com efeito colateral já executada' para fins de idempotência.

Usamos nomes de função iguais aos reais (ex: registrar_dia) porque `_rastrear`
decide pelo `funcao.__name__`, comparando com o set COM_EFEITO.
"""
import pytest

import agente


@pytest.fixture(autouse=True)
def limpar_execucoes():
    agente._execucoes.clear()
    yield
    agente._execucoes.clear()


def test_registra_quando_ferramenta_com_efeito_tem_sucesso():
    def registrar_dia(**kwargs):
        return {"ok": True, "data": kwargs["data"]}

    envolvida = agente._rastrear(registrar_dia)
    resultado = envolvida(data="2026-01-01")

    assert resultado == {"ok": True, "data": "2026-01-01"}
    assert agente._execucoes == [("registrar_dia", {"data": "2026-01-01"}, resultado)]


def test_nao_registra_quando_ferramenta_com_efeito_retorna_erro():
    def registrar_dia(**kwargs):
        return {"ok": False, "erro": "data inválida"}

    envolvida = agente._rastrear(registrar_dia)
    envolvida(data="data-invalida")

    assert agente._execucoes == []


def test_nao_registra_ferramenta_sem_efeito_colateral_mesmo_com_sucesso():
    def consultar_dia(**kwargs):
        return {"ok": True, "registrado": {}}

    envolvida = agente._rastrear(consultar_dia)
    envolvida(data="2026-01-01")

    assert agente._execucoes == []


def test_preserva_nome_e_docstring_da_funcao_original():
    def registrar_dia(**kwargs):
        """Docstring real, lida pelo Gemini para function calling."""
        return {"ok": True}

    envolvida = agente._rastrear(registrar_dia)

    # functools.wraps precisa preservar isso, ou o Gemini perde a descrição
    # da ferramenta e o schema de function calling quebra.
    assert envolvida.__name__ == "registrar_dia"
    assert envolvida.__doc__ == "Docstring real, lida pelo Gemini para function calling."
