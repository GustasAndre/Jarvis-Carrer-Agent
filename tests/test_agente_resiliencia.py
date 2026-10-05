"""Testa a lógica de resiliência de agente.py: retry transitório, fallback de
modelo, o corte de segurança por idempotência e o caminho de falha total.

Nenhum teste aqui faz uma chamada de rede de verdade: o cliente Gemini é
substituído por um dublê controlável (ver tests/fakes.py), então o que está
sob teste é só a lógica de `Jarvis.responder`, não o SDK do Google.
"""
import pytest
from google.genai import errors

import agente
import config
from tests.fakes import ClienteFalso, RespostaFalsa


@pytest.fixture(autouse=True)
def limpar_execucoes():
    """_execucoes é estado de módulo (compartilhado por todas as instâncias de
    Jarvis). Isso é testado explicitamente em test_idempotencia, mas para os
    outros testes ele precisa começar e terminar limpo, senão um teste
    vaza estado pro próximo.
    """
    agente._execucoes.clear()
    yield
    agente._execucoes.clear()


def _erro_sobrecarga():
    raise errors.APIError(503, {"message": "model overloaded"})


def construir_jarvis(monkeypatch, filas_por_modelo):
    """Cria um Jarvis com o cliente Gemini trocado por um dublê.

    filas_por_modelo: dict {nome_do_modelo: [comportamento, ...]}, na ordem
    em que serão consumidos por send_message.
    """
    cliente_falso = ClienteFalso(filas_por_modelo)
    monkeypatch.setattr(agente, "cliente", lambda: cliente_falso)
    jarvis = agente.Jarvis()
    return jarvis, cliente_falso


def test_sucesso_na_primeira_tentativa_nao_troca_de_modelo(monkeypatch):
    jarvis, cliente_falso = construir_jarvis(monkeypatch, {
        config.MODELO: [lambda: RespostaFalsa("tudo certo")],
        config.MODELO_RESERVA: [],
    })

    resposta = jarvis.responder(texto="oi")

    assert resposta == "tudo certo"
    # Só o chat criado no __init__; nenhuma troca de modelo aconteceu.
    assert cliente_falso.modelos_criados == [config.MODELO]


def test_fallback_para_modelo_reserva_quando_erro_transitorio(monkeypatch):
    jarvis, cliente_falso = construir_jarvis(monkeypatch, {
        config.MODELO: [_erro_sobrecarga],
        config.MODELO_RESERVA: [lambda: RespostaFalsa("respondido pela reserva")],
    })

    resposta = jarvis.responder(texto="oi")

    assert resposta == "respondido pela reserva"
    # __init__ (principal) -> troca pra reserva -> volta pro principal após sucesso
    assert cliente_falso.modelos_criados == [config.MODELO, config.MODELO_RESERVA, config.MODELO]
    assert jarvis._modelo_atual == config.MODELO


def test_modelos_indisponiveis_quando_todos_falham_sem_efeito_colateral(monkeypatch):
    jarvis, cliente_falso = construir_jarvis(monkeypatch, {
        config.MODELO: [_erro_sobrecarga],
        config.MODELO_RESERVA: [_erro_sobrecarga],
    })

    with pytest.raises(agente.ModelosIndisponiveis):
        jarvis.responder(texto="oi")

    # Nada foi executado com efeito colateral, então nenhuma AcoesSemResposta.
    assert agente._execucoes == []


def test_erro_nao_transitorio_propaga_sem_tentar_modelo_reserva(monkeypatch):
    def erro_definitivo():
        raise errors.APIError(400, {"message": "requisição inválida"})

    jarvis, cliente_falso = construir_jarvis(monkeypatch, {
        config.MODELO: [erro_definitivo],
        config.MODELO_RESERVA: [lambda: RespostaFalsa("nunca deveria chegar aqui")],
    })

    with pytest.raises(errors.APIError):
        jarvis.responder(texto="oi")

    # 400 não é transitório: não faz sentido tentar de novo com outro modelo.
    assert cliente_falso.modelos_criados == [config.MODELO]


def test_idempotencia_nao_tenta_fallback_depois_de_ferramenta_com_efeito(monkeypatch):
    """Este é o comportamento de segurança mais importante do agente: se uma
    ferramenta com efeito colateral (ex: registrar_dia) já rodou e DEPOIS o
    modelo cai, o Jarvis não pode tentar de novo com outro modelo, porque
    isso arriscaria executar a mesma ação duas vezes.
    """
    execucao_simulada = ("registrar_dia", {"data": "2026-01-01"}, {"ok": True})

    def rodou_ferramenta_e_depois_caiu():
        agente._execucoes.append(execucao_simulada)
        raise errors.APIError(503, {"message": "model overloaded"})

    jarvis, cliente_falso = construir_jarvis(monkeypatch, {
        config.MODELO: [rodou_ferramenta_e_depois_caiu],
        config.MODELO_RESERVA: [lambda: RespostaFalsa("não deveria ser chamado")],
    })

    with pytest.raises(agente.AcoesSemResposta) as exc_info:
        jarvis.responder(texto="registra 10 convites de hoje")

    assert exc_info.value.execucoes == [execucao_simulada]
    # O modelo reserva nunca deveria ter sido tentado.
    assert cliente_falso.modelos_criados == [config.MODELO]
    # A nota de aviso pro próximo turno menciona a ação já executada.
    assert "registrar_dia" in jarvis._notas[0]
