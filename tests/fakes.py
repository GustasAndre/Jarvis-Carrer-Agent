"""Dublês de teste para o cliente Gemini (google.genai), sem nenhuma chamada de rede.

A ideia: `Jarvis` só enxerga `cliente()` (de llm.py) e `self.chat.send_message(...)`.
Substituindo essas duas coisas por fakes controláveis, dá pra testar toda a lógica
de retry/fallback/idempotência de agente.py sem tocar na API do Gemini de verdade.
"""


class RespostaFalsa:
    def __init__(self, texto):
        self.text = texto


class ChatFalso:
    """Um 'chat' de um modelo específico, com uma fila de comportamentos.

    Cada item da fila é uma função sem argumentos: ou devolve uma RespostaFalsa,
    ou levanta uma exceção (simulando uma chamada real ao Gemini).
    """

    def __init__(self, modelo, filas_por_modelo):
        self.modelo = modelo
        self._fila = filas_por_modelo[modelo]
        self.chamadas = 0

    def send_message(self, partes):
        self.chamadas += 1
        if not self._fila:
            raise AssertionError(f"send_message chamado para '{self.modelo}' sem comportamento configurado")
        comportamento = self._fila.pop(0)
        return comportamento()

    def get_history(self):
        return []


class ClienteFalso:
    """Substitui o `genai.Client` real. `filas_por_modelo` é compartilhado entre
    todos os chats criados, então o estado (quantas respostas já foram consumidas
    de cada modelo) persiste entre as trocas de modelo feitas por `Jarvis._usar`.
    """

    def __init__(self, filas_por_modelo):
        self._filas_por_modelo = filas_por_modelo
        self.modelos_criados = []
        self.chats = self

    def create(self, model, config, history=None):
        self.modelos_criados.append(model)
        return ChatFalso(model, self._filas_por_modelo)
