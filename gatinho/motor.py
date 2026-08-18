# -*- coding: utf-8 -*-
"""Dono do llama-server: sobe, derruba e TROCA o modelo de verdade.

Por que este arquivo existe (defeito medido em 2026-08-18): o `/model` mudava
`config["model"]` e o runtime passava a mandar `{"model": "<id>"}` no corpo da
requisicao. So que o llama-server **ignora esse campo** — ele serve o GGUF com que
foi ligado na linha de comando. Resultado: a interface dizia "Modelo alterado para
X" e continuava respondendo com o modelo antigo. Rotulo trocado, motor o mesmo.

Trocar de modelo de verdade e derrubar o processo e subir outro. E aqui entra a
licao que o harness-bench pagou caro: **`/health` respondendo `ok` nao prova qual
modelo esta servindo**. Naquele A/B um llama-server manual ficou segurando a porta,
o health respondeu ok, e 29 execucoes rodaram contra o modelo errado sem ninguem
notar. Entao a prova aqui e sempre o nome do arquivo servido, lido em /v1/models.

Regra de posse: so derrubamos um processo que NOS subimos, ou aquele cujo PID o
gatinho.sh nos entregou em GATINHO_MODELO_PID. Um llama-server de terceiro fica
de pe e o comando recusa, explicando.
"""
from __future__ import annotations

import atexit
import json
import os
import signal
import subprocess
import time
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).parent.parent
BIN = Path(os.environ.get("LLAMA_BIN", RAIZ / "servidor" / "bin" / "llama-server"))
LOGS = RAIZ / "servidor" / "logs"
PORTA = int(os.environ.get("PORTA_MODELO", "8099"))
BASE = f"http://127.0.0.1:{PORTA}"

_PID: int | None = None          # processo que NOS subimos
_PROC: subprocess.Popen | None = None


def gerenciavel() -> bool:
    """Podemos subir/derrubar processo? `GATINHO_MOTOR=off` desliga.

    Existe por um motivo so: a suite de testes nao pode depender do que esta rodando
    na maquina. Sem isto, um llama-server qualquer na porta 8099 faria o teste de
    /model passar ou falhar conforme o humor do dia — e teste que depende do ambiente
    nao prova nada. A auditoria cobra que em producao isto continue LIGADO, porque
    desligar em producao devolveria o /model ao estado decorativo.
    """
    return os.environ.get("GATINHO_MOTOR", "on").strip().lower() not in ("0", "off", "nao", "no")


def _pid_herdado() -> int | None:
    """PID que o gatinho.sh subiu e nos passou — podemos derrubar esse tambem."""
    v = os.environ.get("GATINHO_MODELO_PID", "").strip()
    if not v.isdigit():
        return None
    pid = int(v)
    return pid if _vivo(pid) else None


def _vivo(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _http(caminho: str, timeout: float = 3.0):
    try:
        with urllib.request.urlopen(BASE + caminho, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None


def servindo() -> str | None:
    """Qual arquivo o llama-server esta servindo AGORA. None = ninguem atende.

    Nao pergunta se esta vivo — pergunta o que esta na memoria dele. E a unica
    coisa que distingue "o modelo certo subiu" de "alguma coisa atende na porta".
    """
    d = _http("/v1/models")
    if not d:
        return None
    itens = d.get("data") or d.get("models") or []
    if not itens:
        return None
    it = itens[0]
    alvo = it.get("id") or it.get("model") or "" if isinstance(it, dict) else str(it)
    return Path(alvo).name or None


def no_ar() -> bool:
    return servindo() is not None


def derrubar(timeout: float = 15.0) -> tuple[bool, str]:
    """Encerra o llama-server que nos pertence. Nunca o de terceiro."""
    global _PID, _PROC
    pid = _PID or _pid_herdado()
    if pid is None:
        if no_ar():
            return False, ("tem um llama-server na porta que nao foi este projeto que "
                           "subiu — nao vou derrubar processo dos outros. "
                           "Encerre na mao ou reinicie com ./gatinho.sh")
        return True, "nao havia motor no ar"
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as exc:
        return False, f"nao consegui encerrar o PID {pid}: {exc}"
    fim = time.time() + timeout
    while time.time() < fim:
        if not _vivo(pid):
            break
        time.sleep(0.3)
    else:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    _PID = _PROC = None
    os.environ.pop("GATINHO_MODELO_PID", None)
    return True, f"motor encerrado (PID {pid})"


def subir(gguf: Path, ctx_tokens: int = 16384, ngl: int = 99,
          espera: float = 180.0) -> tuple[bool, str]:
    """Sobe o llama-server com este GGUF e so devolve ok depois de PROVAR.

    Prova = /v1/models dizendo o nome deste arquivo. Health `ok` nao serve.
    """
    global _PID, _PROC
    gguf = Path(gguf)
    if not gguf.is_file():
        return False, f"arquivo nao existe: {gguf}"
    if not BIN.exists():
        return False, f"llama-server nao encontrado em {BIN}"
    LOGS.mkdir(parents=True, exist_ok=True)
    log = (LOGS / "modelo.log").open("a", encoding="utf-8")
    log.write(f"\n===== {time.strftime('%F %T')} subindo {gguf.name} =====\n")
    log.flush()
    _PROC = subprocess.Popen(
        [str(BIN), "-m", str(gguf), "-ngl", str(ngl), "-c", str(ctx_tokens),
         "--host", "127.0.0.1", "--port", str(PORTA), "--jinja",
         "--flash-attn", "on", "--cont-batching", "--no-webui"],
        stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    _PID = _PROC.pid
    fim = time.time() + espera
    while time.time() < fim:
        if _PROC.poll() is not None:
            cauda = _cauda_log()
            _PID = _PROC = None
            return False, f"o llama-server morreu ao carregar {gguf.name}. {cauda}"
        atual = servindo()
        if atual and Path(atual).name == gguf.name:
            return True, f"{gguf.name} servindo na porta {PORTA} (PID {_PID})"
        if atual:                     # atende, mas com OUTRO arquivo
            return False, (f"a porta {PORTA} respondeu servindo '{atual}', nao "
                           f"'{gguf.name}' — tem outro servidor segurando a porta")
        time.sleep(1.0)
    derrubar()
    return False, f"{gguf.name} nao ficou pronto em {int(espera)}s (veja servidor/logs/modelo.log)"


def _cauda_log(n: int = 4) -> str:
    p = LOGS / "modelo.log"
    if not p.exists():
        return ""
    linhas = p.read_text(encoding="utf-8", errors="replace").splitlines()[-n:]
    return "Ultimas linhas: " + " | ".join(x.strip() for x in linhas if x.strip())


def trocar(gguf: Path, ctx_tokens: int = 16384) -> tuple[bool, str]:
    """Derruba o que estiver servindo e sobe este. Operacao completa e verificada."""
    gguf = Path(gguf)
    atual = servindo()
    if atual and Path(atual).name == gguf.name:
        return True, f"{gguf.name} ja era o modelo servindo — nada a fazer"
    if atual:
        ok, msg = derrubar()
        if not ok:
            return False, msg
    return subir(gguf, ctx_tokens=ctx_tokens)


def estado() -> dict:
    a = servindo()
    return {"porta": PORTA, "servindo": a, "no_ar": a is not None,
            "pid": _PID or _pid_herdado(), "nosso": bool(_PID or _pid_herdado())}


@atexit.register
def _saida():
    # a sessao do Pai ja morreu por falta de memoria com llama-server orfao.
    if _PID and _vivo(_PID):
        try:
            os.kill(_PID, signal.SIGTERM)
        except OSError:
            pass


def sincronizar(ctx) -> str:
    """Faz a config concordar com o que o motor esta REALMENTE servindo.

    Medido em 2026-08-18: subindo com `MODELO=omnicoder ./gatinho.sh`, o motor
    carregava omnicoder e a interface anunciava "deltacoder-9b" — o padrao gravado na
    config. Duas fontes de verdade, e a que aparece na tela era a errada. Aqui o
    arquivo servido manda: ele e o unico fato observavel.

    Devolve o id sincronizado, ou "" se nao havia nada para sincronizar.
    """
    arq = servindo()
    if not arq:
        return ""
    alvo = Path(arq).name.lower()
    for m in ctx.registro.listar():
        cam = ctx.registro.caminho(m)
        if cam and cam.name.lower() == alvo:
            if ctx.modelo() != m.id:
                ctx.config.set("model", m.id)
                ctx.sessao.model, ctx.sessao.provider = m.id, m.provider
            return m.id
    return ""
