"""Testa tools/contatos.py com a planilha mockada (sem rede, sem Google).

O alvo aqui é a lógica do CRM: validação de status, busca por nome,
concatenação de notas e filtros de consulta. O gspread é substituído por
um mock que imita a API do Worksheet (get_all_values, append_row, update).
"""
from datetime import date
from unittest.mock import MagicMock

import pytest

from tools import contatos


CABECALHO = list(contatos.CAMPOS)


def linha_contato(**kwargs):
    """Monta uma linha A:L preenchida com os CAMPOS + valores passados."""
    base = {c: "" for c in CABECALHO}
    base.update(kwargs)
    return [base[c] for c in CABECALHO]


@pytest.fixture
def planilha_mock(monkeypatch):
    """Substitui planilha.aba() por um Worksheet falso e controlável."""
    ws = MagicMock()
    ws.get_all_values.return_value = [
        CABECALHO,
        linha_contato(
            id="joao-silva", nome="João Silva", empresa="Acme",
            cargo="Data Scientist", status="aceito",
            data_convite="2026-10-01", data_aceitacao="2026-10-03",
            ultima_interacao="2026-10-05",
        ),
    ]
    monkeypatch.setattr("planilha.aba", lambda nome: ws)
    return ws


def test_adicionar_contato_grava_linha(planilha_mock):
    r = contatos.adicionar_contato("Maria Souza", empresa="Beta Corp")
    assert r["ok"] is True
    assert r["contato"]["id"] == "maria-souza"
    assert r["contato"]["status"] == "convidado"
    planilha_mock.append_row.assert_called_once()


def test_adicionar_contato_rejeita_status_invalido(planilha_mock):
    r = contatos.adicionar_contato("Maria", status="xyz")
    assert r["ok"] is False
    assert "Status inválido" in r["erro"]
    planilha_mock.append_row.assert_not_called()


def test_adicionar_contato_rejeita_nome_vazio(planilha_mock):
    r = contatos.adicionar_contato("   ")
    assert r["ok"] is False


def test_adicionar_contato_impede_duplicata(planilha_mock):
    r = contatos.adicionar_contato("João Silva")
    assert r["ok"] is False
    assert "Já existe" in r["erro"]


def test_atualizar_status_encontra_por_substring(planilha_mock):
    r = contatos.atualizar_status("joão", "conversando")
    assert r["ok"] is True
    assert r["contato"]["status"] == "conversando"


def test_atualizar_status_nao_encontrado(planilha_mock):
    r = contatos.atualizar_status("Ninguém", "aceito")
    assert r["ok"] is False
    assert "não encontrado" in r["erro"]


def test_atualizar_status_aceito_grava_data_se_vazia(planilha_mock):
    planilha_mock.get_all_values.return_value = [
        CABECALHO,
        linha_contato(id="pedro", nome="Pedro", status="convidado"),
    ]
    r = contatos.atualizar_status("Pedro", "aceito")
    assert r["ok"] is True
    assert r["contato"]["data_aceitacao"] == date.today().isoformat()


def test_registrar_interacao_anexa_nota_com_data(planilha_mock):
    r = contatos.registrar_interacao("João", "respondi à mensagem sobre MLOps")
    assert r["ok"] is True
    assert "respondi à mensagem sobre MLOps" in r["contato"]["notas"]
    assert r["contato"]["ultima_interacao"] == date.today().isoformat()


def test_registrar_interacao_rejeita_data_invalida(planilha_mock):
    r = contatos.registrar_interacao("João", "resumo", proximo_followup="31/12/2026")
    assert r["ok"] is False
    assert "inválida" in r["erro"]


def test_consultar_contatos_filtra_por_status(planilha_mock):
    r = contatos.consultar_contatos(status="aceito")
    assert r["ok"] is True
    assert r["total"] == 1
    assert r["contatos"][0]["nome"] == "João Silva"

    r = contatos.consultar_contatos(status="convidado")
    assert r["total"] == 0


def test_consultar_contatos_filtra_por_empresa(planilha_mock):
    r = contatos.consultar_contatos(empresa="acme")
    assert r["total"] == 1


def test_listar_followups_ignora_sem_data(planilha_mock):
    r = contatos.listar_followups_pendentes()
    assert r["ok"] is True
    assert r["total"] == 0


def test_listar_followups_traz_atrasados(planilha_mock):
    planilha_mock.get_all_values.return_value = [
        CABECALHO,
        linha_contato(id="a", nome="A", proximo_followup="2020-01-01"),
        linha_contato(id="b", nome="B", proximo_followup="2999-01-01"),
    ]
    r = contatos.listar_followups_pendentes()
    assert r["total"] == 1
    assert r["pendentes"][0]["nome"] == "A"