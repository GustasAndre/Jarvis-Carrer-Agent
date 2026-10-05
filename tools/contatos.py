"""Ferramentas de CRM de contatos do LinkedIn.

As docstrings são lidas pelo Gemini para decidir quando e como chamar cada
função: elas fazem parte do comportamento do agente, não só da documentação.

Layout da aba "Contatos": cabeçalho na linha 1, dados a partir da linha 2,
colunas A:L na ordem de CAMPOS.
"""
import unicodedata
from datetime import date, timedelta
from typing import Optional

import config
import planilha

ABA_CONTATOS = "Contatos"
PRIMEIRA_LINHA_CONTATOS = 2

# Ordem das colunas A:L da aba Contatos
CAMPOS = [
    "id", "nome", "empresa", "cargo", "url_perfil",
    "status", "data_convite", "data_aceitacao",
    "ultima_interacao", "proximo_followup", "origem", "notas",
]

STATUS_VALIDOS = ("convidado", "aceito", "conversando", "followup_pendente", "arquivado")
ORIGENS_VALIDAS = ("busca", "indicacao", "evento", "comentario")


def _slug(nome: str) -> str:
    """Gera um id ASCII-safe a partir do nome: 'João Silva' -> 'joao-silva'."""
    sem_acento = (
        unicodedata.normalize("NFKD", nome)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    return "-".join(sem_acento.strip().lower().split())


def _ler_todos() -> list[dict]:
    """Lê a aba Contatos inteira e devolve uma lista de dicionários, um por linha."""
    valores = planilha.aba(ABA_CONTATOS).get_all_values()
    if len(valores) < 2:
        return []
    cabecalho = valores[0]
    return [
        dict(zip(cabecalho, linha + [""] * (len(cabecalho) - len(linha))))
        for linha in valores[1:]
    ]


def _linha_de(nome: str) -> tuple[Optional[int], Optional[dict]]:
    """Devolve (número_da_linha, contato) do primeiro cujo nome contém `nome`.

    Casa por substring case-insensitive para tolerar "João" achar "João Silva".
    """
    alvo = (nome or "").strip().lower()
    if not alvo:
        return None, None
    contatos = _ler_todos()
    for i, c in enumerate(contatos):
        if alvo in (c.get("nome") or "").lower():
            return PRIMEIRA_LINHA_CONTATOS + i, c
    return None, None


def _escrever_celula(linha: int, campo: str, valor) -> None:
    coluna = chr(ord("A") + CAMPOS.index(campo))
    planilha.escrever(ABA_CONTATOS, f"{coluna}{linha}", [valor])


def _hoje_iso() -> str:
    return config.hoje().isoformat()


def adicionar_contato(
    nome: str,
    empresa: Optional[str] = None,
    cargo: Optional[str] = None,
    url_perfil: Optional[str] = None,
    status: str = "convidado",
    origem: Optional[str] = None,
    notas: Optional[str] = None,
) -> dict:
    """Adiciona um novo contato ao CRM do LinkedIn.

    Use quando o Gustavo mencionar alguém que convidou, conheceu, recebeu
    indicação ou quer acompanhar. Informe SOMENTE os campos que ele citou;
    nunca estime empresa, cargo ou URL. Se ele não disser o nome, pergunte antes.

    Args:
        nome: Nome completo do contato, como ele mencionou.
        empresa: Empresa onde a pessoa trabalha, se mencionada.
        cargo: Cargo atual da pessoa, se mencionado.
        url_perfil: URL do perfil no LinkedIn, se fornecida.
        status: Estado no funil. Um de: convidado (padrão, quando ele enviou
            ou vai enviar o convite), aceito (o convite já foi aceito),
            conversando (há conversa em andamento), followup_pendente (precisa
            retomar), arquivado (fora do radar).
        origem: Como o contato foi encontrado. Um de: busca, indicacao,
            evento, comentario.
        notas: Nota livre curta (interesses, contexto, empresa antiga etc.).

    Returns:
        Dicionário com {"ok": True, "contato": {...}} ou {"ok": False, "erro": "..."}.
    """
    nome = (nome or "").strip()
    if not nome:
        return {"ok": False, "erro": "Nome do contato é obrigatório."}
    if status not in STATUS_VALIDOS:
        return {"ok": False, "erro": f"Status inválido: {status}. Use um de: {', '.join(STATUS_VALIDOS)}."}
    if origem and origem not in ORIGENS_VALIDAS:
        return {"ok": False, "erro": f"Origem inválida: {origem}. Use uma de: {', '.join(ORIGENS_VALIDAS)}."}

    contatos = _ler_todos()
    novo_id = _slug(nome)
    if any((c.get("id") or "") == novo_id for c in contatos):
        return {"ok": False, "erro": f"Já existe um contato com id '{novo_id}' no CRM."}

    hoje = _hoje_iso()
    data_convite = hoje if status == "convidado" else ""
    data_aceitacao = hoje if status == "aceito" else ""
    linha = [
        novo_id, nome, empresa or "", cargo or "", url_perfil or "",
        status, data_convite, data_aceitacao, "", "", origem or "", notas or "",
    ]
    planilha.aba(ABA_CONTATOS).append_row(linha, value_input_option="USER_ENTERED")
    return {"ok": True, "contato": dict(zip(CAMPOS, linha))}


def atualizar_status(nome: str, novo_status: str, notas: Optional[str] = None) -> dict:
    """Atualiza o status de um contato já existente no CRM.

    Use quando o Gustavo disser que alguém aceitou o convite ("o João aceitou"),
    começou uma conversa, precisa de follow-up, ou quer arquivar um contato.
    Se o nome não for encontrado, diga que não achou e pergunte se é para
    cadastrar como novo.

    Args:
        nome: Nome do contato (busca por correspondência parcial, sem
            diferenciar maiúsculas/minúsculas).
        novo_status: Um de: convidado, aceito, conversando, followup_pendente,
            arquivado.
        notas: Nota opcional para acrescentar ao histórico do contato.

    Returns:
        Dicionário com {"ok": True, "contato": {...}} ou {"ok": False, "erro": "..."}.
    """
    if novo_status not in STATUS_VALIDOS:
        return {"ok": False, "erro": f"Status inválido: {novo_status}. Use um de: {', '.join(STATUS_VALIDOS)}."}

    linha, contato = _linha_de(nome)
    if linha is None:
        return {"ok": False, "erro": f"Contato não encontrado: '{nome}'."}

    hoje = _hoje_iso()
    atualizado = dict(contato)
    _escrever_celula(linha, "status", novo_status)
    _escrever_celula(linha, "ultima_interacao", hoje)
    atualizado["status"] = novo_status
    atualizado["ultima_interacao"] = hoje

    if novo_status == "aceito" and not (contato.get("data_aceitacao") or "").strip():
        _escrever_celula(linha, "data_aceitacao", hoje)
        atualizado["data_aceitacao"] = hoje

    if notas:
        anterior = str(contato.get("notas") or "").strip()
        nova = f"{anterior} | {notas}" if anterior else notas
        _escrever_celula(linha, "notas", nova)
        atualizado["notas"] = nova

    return {"ok": True, "contato": atualizado}


def registrar_interacao(
    nome: str,
    resumo: str,
    proximo_followup: Optional[str] = None,
) -> dict:
    """Registra uma interação com um contato e, opcionalmente, agenda o próximo follow-up.

    Use quando o Gustavo disser que falou com alguém, comentou um post dela,
    respondeu uma mensagem, ou quer marcar um follow-up. O resumo entra no
    histórico de notas do contato, prefixado pela data de hoje.

    Args:
        nome: Nome do contato.
        resumo: O que aconteceu, em uma linha curta (ex: "respondi à mensagem
            sobre MLOps", "comentei o post de lançamento").
        proximo_followup: Data AAAA-MM-DD para o próximo follow-up, se ele
            quiser agendar. Se omitido, o campo atual não é alterado.

    Returns:
        Dicionário com {"ok": True, "contato": {...}} ou {"ok": False, "erro": "..."}.
    """
    if not (resumo or "").strip():
        return {"ok": False, "erro": "Resumo da interação é obrigatório."}

    if proximo_followup:
        try:
            date.fromisoformat(proximo_followup)
        except ValueError:
            return {"ok": False, "erro": f"Data de follow-up inválida: {proximo_followup}. Use AAAA-MM-DD."}

    linha, contato = _linha_de(nome)
    if linha is None:
        return {"ok": False, "erro": f"Contato não encontrado: '{nome}'."}

    hoje = _hoje_iso()
    anterior = str(contato.get("notas") or "").strip()
    nota = f"{anterior} | {hoje}: {resumo}" if anterior else f"{hoje}: {resumo}"

    _escrever_celula(linha, "ultima_interacao", hoje)
    _escrever_celula(linha, "notas", nota)
    atualizado = dict(contato)
    atualizado["ultima_interacao"] = hoje
    atualizado["notas"] = nota

    if proximo_followup:
        _escrever_celula(linha, "proximo_followup", proximo_followup)
        atualizado["proximo_followup"] = proximo_followup

    return {"ok": True, "contato": atualizado}


def consultar_contatos(
    status: Optional[str] = None,
    empresa: Optional[str] = None,
    sem_interacao_dias: Optional[int] = None,
) -> dict:
    """Consulta contatos do CRM com filtros opcionais.

    Use quando o Gustavo perguntar quem ele convidou, quem aceitou, com quem
    não fala há um tempo, ou quiser ver os contatos de uma empresa específica.

    Args:
        status: Filtrar por status (convidado, aceito, conversando,
            followup_pendente, arquivado).
        empresa: Filtrar por empresa, correspondência parcial sem diferenciar
            maiúsculas/minúsculas.
        sem_interacao_dias: Mostrar apenas contatos sem interação registrada
            há N dias ou mais (inclui contatos nunca interagidos).

    Returns:
        Dicionário com {"ok": True, "total": N, "contatos": [...]}.
    """
    if status and status not in STATUS_VALIDOS:
        return {"ok": False, "erro": f"Status inválido: {status}. Use um de: {', '.join(STATUS_VALIDOS)}."}

    contatos = _ler_todos()

    if status:
        contatos = [c for c in contatos if c.get("status") == status]
    if empresa:
        alvo = empresa.strip().lower()
        contatos = [c for c in contatos if alvo in (c.get("empresa") or "").lower()]
    if sem_interacao_dias is not None:
        limite = config.hoje() - timedelta(days=sem_interacao_dias)
        filtrados = []
        for c in contatos:
            ultima = (c.get("ultima_interacao") or "").strip()
            if not ultima:
                filtrados.append(c)
                continue
            try:
                if date.fromisoformat(ultima) <= limite:
                    filtrados.append(c)
            except ValueError:
                filtrados.append(c)
        contatos = filtrados

    return {"ok": True, "total": len(contatos), "contatos": contatos}


def listar_followups_pendentes() -> dict:
    """Lista contatos com follow-up agendado para hoje ou já atrasado.

    Use quando o Gustavo perguntar "com quem eu falo hoje?", "o que tenho
    pendente?" ou pedir a agenda de relacionamento do dia.

    Returns:
        Dicionário com {"ok": True, "total": N, "pendentes": [...]}, ordenado
        do follow-up mais antigo para o mais recente.
    """
    contatos = _ler_todos()
    hoje = config.hoje()
    pendentes = []
    for c in contatos:
        data_followup = (c.get("proximo_followup") or "").strip()
        if not data_followup:
            continue
        try:
            if date.fromisoformat(data_followup) <= hoje:
                pendentes.append(c)
        except ValueError:
            continue
    pendentes.sort(key=lambda c: c.get("proximo_followup") or "")
    return {"ok": True, "total": len(pendentes), "pendentes": pendentes}