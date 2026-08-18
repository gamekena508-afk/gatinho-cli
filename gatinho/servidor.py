# -*- coding: utf-8 -*-
"""Servidor do Gatinho — a interface do navegador falando com o motor de verdade.

Nao e maquete: cada acao que aparece na tela e uma ferramenta real rodando no
disco, e o texto vem do modelo por streaming (SSE do llama-server).

Rotas:
    GET  /                 a interface
    GET  /assets/<arq>     arte
    GET  /api/estado       modelo, modo, contexto, harness, sessao
    POST /api/chat         {"texto": "..."} -> SSE com os eventos do runtime
    POST /api/comando      {"texto": "/status"} -> resposta do command router
    POST /api/parar        interrompe a execucao em andamento
"""
from __future__ import annotations

import json
import mimetypes
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from . import handlers  # noqa: F401  — registra os comandos
from . import i18n, sandbox
from .comandos import resolver
from .config import humano
from .estado import Contexto
from .runtime import Runtime

WEB = Path(__file__).parent.parent / "web"
_LOCK = threading.Lock()
_EM_CURSO = {"desde": 0.0, "texto": ""}   # para a mensagem honesta de "ocupado"


class Servidor(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, endereco, ctx: Contexto):
        self.ctx = ctx
        super().__init__(endereco, Handler)


class Handler(BaseHTTPRequestHandler):
    server_version = "Gatinho/3.0"

    # ------------------------------------------------------------ utilidades
    def log_message(self, fmt, *args):        # silencia o log padrao do stdlib
        pass

    @property
    def ctx(self) -> Contexto:
        return self.server.ctx

    def _envia(self, corpo: bytes, tipo="application/json", codigo=200, extra=None):
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(corpo)

    def _json(self, dados, codigo=200):
        self._envia(json.dumps(dados, ensure_ascii=False).encode("utf-8"), codigo=codigo)

    def _corpo(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:                                          # noqa: BLE001
            return {}

    def _estado(self) -> dict:
        c = self.ctx
        d = c.ultima_decisao_roteador
        return {
            "modelo": c.modelo(), "provider": c.config.get("provider"),
            "modo": c.modo, "modo_nome": c.nome_modo(),
            "tokens": c.metricas.contexto_atual, "janela": c.janela(),
            "tokens_h": humano(c.metricas.contexto_atual), "janela_h": humano(c.janela()),
            "harness_pedido": c.harness_pedido(),
            "harness_efetivo": d.get("selected_harness", "—"),
            "sessao": c.sessao.nome or c.sessao.session_id,
            "projeto": str(c.projeto), "executando": c.executando,
            "emitidas": c.metricas.tool_calls_emitted,
            "executadas": c.metricas.tool_calls_executed,
            "bloqueadas": c.metricas.tool_calls_blocked,
            "arquivos": c.sessao.files,
            "idioma": c.idioma,
            "idiomas": {k: v["nome"] for k, v in i18n.IDIOMAS.items()},
            "textos": i18n.pacote(c.idioma),
            "sandbox": c.modo_pasta == sandbox.MODO_SANDBOX,
            "aguardando_plano": c.aguardando_plano,
            "bloqueadas_ultima": c.metricas.tool_calls_blocked,
            "pasta": str(c.pasta_trabalho()),
            "aviso_sandbox": i18n.t("sandbox.on" if c.modo_pasta == sandbox.MODO_SANDBOX
                                    else "sandbox.off", c.idioma),
        }

    # ------------------------------------------------------------------- GET
    def do_GET(self):
        caminho = unquote(urlparse(self.path).path)
        if caminho in ("/", "/index.html"):
            arq = WEB / "index.html"
            if not arq.exists():
                return self._envia(b"index.html nao encontrado. Rode web/gerar.py",
                                   "text/plain; charset=utf-8", 500)
            return self._envia(arq.read_bytes(), "text/html; charset=utf-8")
        if caminho.startswith("/assets/"):
            arq = (WEB / caminho.lstrip("/")).resolve()
            if not str(arq).startswith(str(WEB.resolve())) or not arq.exists():
                return self._envia(b"nao encontrado", "text/plain", 404)
            tipo = mimetypes.guess_type(str(arq))[0] or "application/octet-stream"
            return self._envia(arq.read_bytes(), tipo)
        if caminho == "/api/estado":
            return self._json(self._estado())
        if caminho == "/api/comandos":
            return self._json(self._comandos())
        self._envia(b"nao encontrado", "text/plain", 404)

    def _comandos(self) -> dict:
        """O registro REAL, para a web montar a paleta com ele.

        Ate 2026-08-18 a paleta da web era a lista do mockup: 8 comandos escritos na
        mao, tres deles inexistentes no motor (/agents, /limpar, /modo), e os outros
        50 comandos reais — incluindo /model, /models, /sandbox, /idioma — invisiveis.
        Digitar "/" mostrava um menu que nao correspondia ao programa. Lista escrita
        na mao ao lado de um registro que existe e divergencia garantida: agora vem
        deste endpoint, e a auditoria compara os dois.
        """
        from .comandos import ALIASES, REGISTRO
        itens = [{"nome": "/" + c.name, "desc": c.description,
                  "uso": c.usage or "/" + c.name, "categoria": c.category}
                 for c in sorted(REGISTRO.values(), key=lambda x: x.name)]
        return {"comandos": itens,
                "aliases": {"/" + a: "/" + d for a, d in sorted(ALIASES.items())},
                "total": len(itens)}

    # ------------------------------------------------------------------ POST
    def do_POST(self):
        caminho = urlparse(self.path).path
        if caminho == "/api/permissao":
            d = self._corpo()
            canal = getattr(self.ctx, "canal_permissao", None)
            if not canal:
                return self._json({"erro": True, "linhas": ["nao ha nada esperando permissao"]})
            evento, caixa = canal
            caixa["ok"] = bool(d.get("ok"))
            evento.set()
            return self._json({"ok": True, "aprovado": caixa["ok"]})
        if caminho == "/api/parar":
            self.ctx.parar = True
            canal = getattr(self.ctx, "canal_permissao", None)
            if canal:                    # destrava quem estiver esperando resposta
                evento, caixa = canal
                caixa["ok"] = False
                evento.set()
            return self._json({"ok": True, "linhas": ["parando…"]})
        if caminho == "/api/comando":
            return self._comando()
        if caminho == "/api/chat":
            return self._chat()
        self._envia(b"nao encontrado", "text/plain", 404)

    def _comando(self):
        texto = (self._corpo().get("texto") or "").strip()
        cmd, args = resolver(texto)
        if not cmd:
            return self._json({"erro": True, "linhas": [f"comando {texto} nao existe"]})
        try:
            r = cmd.handler(self.ctx, args)
        except Exception as exc:                                   # noqa: BLE001
            return self._json({"erro": True,
                               "linhas": [f"{type(exc).__name__}: {exc}"]})
        return self._json({"erro": r.erro, "ok": r.ok, "titulo": r.titulo,
                           "linhas": r.linhas, "escolhas": r.escolhas,
                           "acao": r.acao, "estado": self._estado()})

    def _chat(self):
        texto = (self._corpo().get("texto") or "").strip()
        if not texto:
            return self._json({"erro": True, "linhas": ["mensagem vazia"]})
        if not _LOCK.acquire(blocking=False):
            ha = int(time.time() - (_EM_CURSO["desde"] or time.time()))
            return self._json({"erro": True, "linhas": [
                f"ja tem uma tarefa rodando ha {ha}s: {_EM_CURSO['texto'][:60]}",
                "use /parar para interromper, ou espere ela terminar"]})
        _EM_CURSO.update(desde=time.time(), texto=texto)

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        def manda(ev: dict):
            self.wfile.write(f"data: {json.dumps(ev, ensure_ascii=False)}\n\n".encode("utf-8"))
            self.wfile.flush()

        c = self.ctx
        try:
            # 1) idioma do usuario decide a interface E o idioma da resposta
            antes = c.idioma
            idioma, conf = c.definir_idioma(texto)
            if idioma != antes:
                manda({"tipo": "idioma", "idioma": idioma, "confianca": round(conf, 2),
                       "textos": i18n.pacote(idioma)})
            # 2) a sessao trabalha na propria sandbox, criada na primeira mensagem
            if c.modo_pasta == sandbox.MODO_SANDBOX and c.work is None:
                c.garantir_work(semear_de=c.projeto)
                manda({"tipo": "sandbox", "pasta": str(c.pasta_trabalho()),
                       "aviso": i18n.t("sandbox.on", c.idioma)})
            # 3) fluxo do PLANO: "sim" depois de um plano aprova e implementa
            if c.aguardando_plano and re.match(r"^\s*(sim|s|yes|y|ok|si|是|好)\b",
                                               texto.strip(), re.I):
                c.aguardando_plano = False
                c.modo = "full"
                manda({"tipo": "aviso", "texto": "plano aprovado → FULL ACESSO"})
                manda({"tipo": "politica", "modo": "full"})

            # 4) PEDIR PERMISSAO: canal que bloqueia o runtime ate o usuario responder
            evento_perm = threading.Event()
            caixa = {"ok": False}
            c.canal_permissao = (evento_perm, caixa)

            def pedir(ferramenta, alvo):
                """Espera a resposta, mas nao para sempre.

                Bug medido (2026-08-17): o navegador fechou no meio de um pedido
                de permissao e a execucao ficou 5 min presa segurando o lock —
                a interface inteira respondia "ja tem uma tarefa rodando".
                """
                evento_perm.clear()
                caixa["ok"] = False
                try:
                    manda({"tipo": "permissao", "ferramenta": ferramenta, "alvo": alvo})
                except (BrokenPipeError, OSError):
                    c.parar = True
                    return False
                esperou = 0.0
                while esperou < 90:
                    if evento_perm.wait(timeout=2):
                        return caixa["ok"]
                    esperou += 2
                    if c.parar:
                        return False
                    try:                       # o cliente ainda esta ai?
                        manda({"tipo": "ping"})
                    except (BrokenPipeError, OSError):
                        c.parar = True
                        return False
                try:
                    manda({"tipo": "aviso", "texto": "ninguem respondeu em 90s — neguei"})
                except Exception:              # noqa: BLE001
                    pass
                return False

            c.pedir_permissao = pedir if c.modo_pedido_permissao() else None

            c.sessao.mensagem("user", texto)
            rt = Runtime(c)
            for ev in rt.conversar_eventos(texto):
                if ev.get("tipo") == "fim":
                    if c.so_leitura():
                        c.aguardando_plano = True
                        extra = ""
                        # o modelo as vezes AFIRMA que criou o arquivo que foi
                        # bloqueado. A interface nao pode repetir isso calada.
                        if c.metricas.tool_calls_blocked:
                            extra = ("\n\n" + i18n.t("plano.nada_feito", c.idioma)
                                     .replace("{n}", str(c.metricas.tool_calls_blocked)))
                        ev["texto"] = (ev.get("texto", "") + extra +
                                       "\n\n" + i18n.t("plano.aprovar", c.idioma))
                    c.sessao.mensagem("assistant", ev.get("texto", ""))
                    c.sessao.salvar()
                    ev["estado"] = self._estado()
                manda(ev)
        except BrokenPipeError:
            c.parar = True                       # o navegador fechou a aba
        except Exception as exc:                                   # noqa: BLE001
            import traceback
            print(f"[chat] {type(exc).__name__}: {exc}\n{traceback.format_exc()}",
                  file=sys.stderr, flush=True)
            try:
                manda({"tipo": "erro", "texto": f"{type(exc).__name__}: {exc}"})
            except Exception:                                      # noqa: BLE001
                pass
        finally:
            c.executando = False
            c.pedir_permissao = None
            c.canal_permissao = None
            _LOCK.release()


def servir(ctx: Contexto, host="127.0.0.1", porta=8777) -> Servidor:
    return Servidor((host, porta), ctx)
