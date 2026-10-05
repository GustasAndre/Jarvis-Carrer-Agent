"""Setup compartilhado por toda a suíte de testes.

config.py lê GEMINI_API_KEY, GOOGLE_CREDENTIALS e PLANILHA_ID direto de
os.environ no nível do módulo (fora de qualquer função). Isso significa que o
primeiro `import config` (direto ou via agente.py/llm.py) explode com
KeyError se essas variáveis não existirem — mesmo em testes que não usam
nenhuma delas de verdade.

Por isso elas precisam existir ANTES de qualquer import desses módulos, e
este arquivo é carregado pelo pytest antes da coleta dos testes do diretório.

python-dotenv (chamado dentro de config.py) não sobrescreve variáveis que já
existem no ambiente por padrão, então mesmo que o desenvolvedor tenha um
.env real na raiz do projeto, os valores falsos abaixo continuam valendo
durante os testes.
"""
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

os.environ.setdefault("GEMINI_API_KEY", "test-gemini-api-key")
os.environ.setdefault("GOOGLE_CREDENTIALS", "test-credentials.json")
os.environ.setdefault("PLANILHA_ID", "test-sheet-id")
