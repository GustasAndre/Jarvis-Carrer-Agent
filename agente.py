"""O Jarvis: agente roteador que interpreta a mensagem e escolhe a ferramenta.

Cadeia de modelos: Gemini (principal) → Gemini reserva.
"""
import functools
import logging

from google.genai import types

import config
from llm import carregar_prompt, cliente, erro_transitorio
from tools import conteudo, contatos, registro

log = logging.getLogger("jarvis.agente")

DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]

# Ferramentas que mudam algo (planilha, rascunho, arquivo). Se uma delas rodar e a
# resposta final falhar, a mensagem NÃO pode ser reenviada, senão a ação se repete.
COM_EFEITO = {
    "registrar_dia", "rascunhar_post", "ajustar_post", "aprovar_post", "descartar_post",
    "adicionar_contato", "atualizar_status", "registrar_interacao",
}
_execucoes: list[tuple[str, dict, dict]] = []


class AcoesSemResposta(Exception):
    """Ações já executadas, mas o modelo caiu antes de responder."""

    def __init__(self, execucoes):
        super().__init__("ações executadas sem resposta final")
        self.execucoes = execucoes


class ModelosIndisponiveis(Exception):
    """Nenhum modelo conseguiu responder e nada foi alterado."""


def _rastrear(funcao):
    @functools.wraps(funcao)  # preserva nome, docstring e assinatura que o Gemini lê
    def envoltorio(*args, **kwargs):
        log.info("Ferramenta chamada: %s %s", funcao.__name__, kwargs)
        resultado = funcao(*args, **kwargs)
        falhou = isinstance(resultado, dict) and resultado.get("ok") is False
        if funcao.__name__ in COM_EFEITO and not falhou:
            _execucoes.append((funcao.__name__, kwargs, resultado))
        return resultado
    return envoltorio


FERRAMENTAS = [_rastrear(f) for f in (
    registro.registrar_dia,
    registro.consultar_dia,
    registro.resumo_semana,
    conteudo.rascunhar_post,
    conteudo.ajustar_post,
    conteudo.aprovar_post,
    conteudo.descartar_post,
    contatos.adicionar_contato,
    contatos.atualizar_status,
    contatos.registrar_interacao,
    contatos.consultar_contatos,
    contatos.listar_followups_pendentes,
)]


class Jarvis:
    def __init__(self) -> None:
        self._sistema = carregar_prompt("jarvis.md")
        self._config = types.GenerateContentConfig(system_instruction=self._sistema, tools=FERRAMENTAS)
        self._modelos = [m for m in dict.fromkeys([config.MODELO, config.MODELO_RESERVA]) if m]
        self._modelo_atual = config.MODELO
        self.chat = cliente().chats.create(model=config.MODELO, config=self._config)
        self._notas: list[str] = []  # avisos do sistema para a próxima mensagem

    def _usar(self, modelo: str, historico=None) -> None:
        """Troca de modelo mantendo o histórico da conversa."""
        historico = self.chat.get_history() if historico is None else historico
        self.chat = cliente().chats.create(model=modelo, config=self._config, history=historico)
        self._modelo_atual = modelo

    def _falhou_depois_de_agir(self, e: Exception) -> None:
        resumo = "; ".join(f"{nome}({args})" for nome, args, _ in _execucoes)
        self._notas = [f"[Sistema: na mensagem anterior do Gustavo, estas ações JÁ foram executadas e não devem ser repetidas: {resumo}]"]
        raise AcoesSemResposta(list(_execucoes)) from e

    def responder(self, texto: str | None = None, audio: bytes | None = None,
                  mime: str = "audio/ogg") -> str:
        agora = config.agora()
        # A data vai em cada mensagem (e não no prompt de sistema) para continuar
        # correta mesmo numa conversa que atravessa a meia-noite.
        partes_texto = [f"[Contexto: agora é {DIAS[agora.weekday()]}, {agora:%Y-%m-%d %H:%M}, horário de Brasília]"]
        partes_texto += self._notas
        if texto:
            partes_texto.append(texto)
        partes: list = list(partes_texto)
        if audio:
            partes.insert(len(partes_texto) - (1 if texto else 0), types.Part.from_bytes(data=audio, mime_type=mime))

        for modelo in self._modelos:
            if modelo != self._modelo_atual:
                log.warning("Usando o modelo %s.", modelo)
                self._usar(modelo)
            _execucoes.clear()
            try:
                resp = self.chat.send_message(partes)
            except Exception as e:
                if not erro_transitorio(e):
                    raise
                if _execucoes:
                    self._falhou_depois_de_agir(e)
                log.warning("Modelo %s indisponível (%s).", modelo, getattr(e, "code", type(e).__name__))
                continue
            self._notas = []
            if self._modelo_atual != config.MODELO:
                self._usar(config.MODELO)  # volta ao principal na próxima mensagem
            return resp.text or "(sem resposta em texto)"

        raise ModelosIndisponiveis("modelos indisponíveis")