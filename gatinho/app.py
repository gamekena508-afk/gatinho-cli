# -*- coding: utf-8 -*-
"""Loop principal do Gatinho: le, roteia comando ou trabalha (requisitos 1, 79, 101)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings

from . import handlers, runtime, ui                       # handlers registra os comandos
from . import sessao as ses
from .comandos import REGISTRO, resolver, sugestoes
from .config import CAMINHO_GLOBAL
from .estado import Contexto

VERSAO = handlers.VERSAO


class CompletadorDeComandos(Completer):
    """Autocomplete do `/` (requisito 75). Fora do `/`, nao atrapalha a digitacao."""

    def get_completions(self, document, complete_event):
        texto = document.text_before_cursor
        if not texto.lstrip().startswith("/"):
            return
        for s in sugestoes(texto):
            yield Completion(s["valor"], start_position=-len(texto.lstrip()),
                             display=s["valor"], display_meta=s.get("descricao", ""))


def _escolher(sessao_pt, resposta):
    """Menu de escolha: lista + prompt com autocomplete dos valores. Esc cancela."""
    valores = [e["valor"] for e in resposta.escolhas]
    rotulos = {e["valor"]: e["rotulo"] for e in resposta.escolhas}

    class C(Completer):
        def get_completions(self, document, complete_event):
            t = document.text_before_cursor.strip().lower()
            for v in valores:
                if t in v.lower() or t in rotulos[v].lower():
                    yield Completion(v, start_position=-len(document.text_before_cursor),
                                     display=rotulos[v])
    try:
        escolha = sessao_pt.prompt(HTML('<ansicyan>escolha> </ansicyan>'), completer=C(),
                                   complete_while_typing=True)
    except (KeyboardInterrupt, EOFError):
        return None
    escolha = (escolha or "").strip()
    if not escolha:
        return None
    for v in valores:
        if escolha.lower() == v.lower() or escolha.lower() == rotulos[v].lower():
            return v
    return escolha


def _confirmar(sessao_pt, pergunta="confirmar? (s/N) ") -> bool:
    try:
        r = sessao_pt.prompt(HTML(f'<ansiyellow>{pergunta}</ansiyellow>'))
    except (KeyboardInterrupt, EOFError):
        return False
    return (r or "").strip().lower() in ("s", "sim", "y", "yes")


def executar_comando(ctx, sessao_pt, entrada) -> bool:
    """Devolve False quando o app deve encerrar."""
    cmd, args = resolver(entrada)
    if not cmd:
        ui.erro_humano(f"Comando {entrada.split()[0]} nao existe.",
                       "digite / para ver a lista")
        return True
    try:
        r = cmd.handler(ctx, args)
    except Exception as exc:                                     # noqa: BLE001
        ctx.log("erro", f"{cmd.name}: {type(exc).__name__}: {exc}")
        ui.erro_humano(f"O comando /{cmd.name} falhou.", f"{type(exc).__name__}: {exc}")
        return True

    # menu -> reexecuta o comando com o valor escolhido
    if r.escolhas and not r.acao:
        ui.resposta(r, ctx.config.get("verbose"))
        v = _escolher(sessao_pt, r)
        if v is None:
            return True
        if cmd.name in ("sessions",):
            r2 = REGISTRO["resume"].handler(ctx, [v])
        elif cmd.name == "config":
            r2 = REGISTRO["config"].handler(ctx, [])
            r2.escolhas = []
            r2.linhas = [f"categoria '{v}' — use /config set <chave> <valor>"]
        else:
            r2 = cmd.handler(ctx, [v])
        ui.resposta(r2, ctx.config.get("verbose"))
        return True

    ui.resposta(r, ctx.config.get("verbose"))

    if r.acao == "sair":
        return False
    if r.acao == "limpar":
        ui.tela_inicial(ctx)
    elif r.acao == "novo":
        ui.tela_inicial(ctx)
    elif r.acao == "confirmar-apagar":
        if _confirmar(sessao_pt, "apagar esta sessao? (s/N) "):
            ok = ses.apagar(r.dados["session_id"])
            ui.aviso("Sessao apagada." if ok else "Nao achei essa sessao.",
                     ui.C_OK if ok else ui.C_ERRO)
    elif r.acao == "confirmar-reset":
        if _confirmar(sessao_pt, "descartar as mensagens? (s/N) "):
            ctx.sessao.messages = []
            ctx.metricas.marcar_contexto(0)
            ui.aviso("Contexto da conversa descartado.", ui.C_OK)
    elif r.acao == "confirmar-rollback":
        if _confirmar(sessao_pt, "desfazer todas as alteracoes? (s/N) "):
            n, erros = runtime.desfazer_tudo(ctx)
            ui.aviso(f"{n} alteracao(oes) desfeita(s).", ui.C_OK)
            for e in erros:
                ui.aviso(e, ui.C_ERRO)
    return True


def trabalhar(ctx, pedido: str, sessao_pt=None):
    """Fluxo: PLANEJAMENTO -> SUPERVISÃO, honrando a politica escolhida."""
    # A SANDBOX PRIMEIRO. Bug medido (2026-08-17): o Runtime era criado antes e
    # capturava ctx.projeto — o terminal escrevia no projeto do Pai em vez da
    # copia. A ordem aqui e contrato, nao estilo.
    ctx.definir_idioma(pedido)
    if ctx.modo_pasta == "sandbox" and ctx.work is None:
        ctx.garantir_work(semear_de=ctx.projeto)
        ui.aviso(f"sandbox: {ctx.pasta_trabalho()}", ui.C_FRACO)

    rt = runtime.Runtime(ctx, on_evento=lambda ev: ui.evento(ev, ctx.config.get("verbose")))

    # o terminal tambem pergunta quando a politica e PEDIR PERMISSAO
    if ctx.modo_pedido_permissao() and sessao_pt is not None:
        def perguntar(ferramenta, alvo):
            ui.aviso(f"\n🔒 {ferramenta}: {alvo}", ui.C_AVISO)
            return _confirmar(sessao_pt, "permitir? (s/N) ")
        ctx.pedir_permissao = perguntar
    else:
        ctx.pedir_permissao = None

    # "sim" depois de um plano aprova e implementa
    import re as _re
    if ctx.aguardando_plano and _re.match(r"^\s*(sim|s|yes|y|ok)\b", pedido.strip(), _re.I):
        ctx.aguardando_plano = False
        ctx.config.set("harness", ctx.config.get("harness"))
        ctx.modo = "full"
        ui.aviso("plano aprovado → FULL ACESSO", ui.C_OK)

    ctx.sessao.mensagem("user", pedido)

    ui.aviso("\nPLANEJAMENTO", ui.C_INFO)
    plano = rt.planejar(pedido)
    ui.aviso("\nSUPERVISÃO", ui.C_OK)
    resposta = rt.conversar(pedido)
    if ctx.so_leitura():
        from .i18n import t as _t
        ctx.aguardando_plano = True
        resposta += "\n\n" + _t("plano.aprovar", ctx.idioma)
    ctx.sessao.mensagem("assistant", resposta)
    ctx.sessao.salvar()
    ui.fala_do_gatinho(resposta)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="gatinho", description="Gatinho CLI — agente de coding")
    ap.add_argument("pedido", nargs="*", help="pedido direto (sem abrir a interface)")
    ap.add_argument("--cwd", default=".", help="pasta do projeto")
    ap.add_argument("--model", help="modelo")
    ap.add_argument("--provider", help="provider")
    ap.add_argument("--context", help="janela, ex: 32k")
    ap.add_argument("--harness", choices=["auto", "fast-coder", "mast-agent"])
    ap.add_argument("--resume", metavar="ID", help="retomar sessao")
    ap.add_argument("--serve", action="store_true",
                    help="sobe a interface do navegador (a oficial) em vez do terminal")
    ap.add_argument("--porta", type=int, default=8777, help="porta da interface web")
    ap.add_argument("--version", action="version", version=f"gatinho {VERSAO}")
    a = ap.parse_args(argv)

    ctx = Contexto(projeto=Path(a.cwd).resolve())
    ctx.versao = VERSAO
    for chave, valor in (("model", a.model), ("provider", a.provider), ("harness", a.harness)):
        if valor:
            ctx.config.set(chave, valor)
    if a.context:
        handlers.h_context(ctx, [a.context])
    if a.resume:
        r = handlers.h_resume(ctx, [a.resume])
        if r.erro:
            ui.resposta(r)

    if a.serve:
        from . import motor
        from .servidor import servir
        motor.instalar_encerramento()   # SIGTERM sem isto deixa llama-server orfao
        # o que o motor serve manda sobre o que a config guardou (ver motor.sincronizar)
        sincronizado = motor.sincronizar(ctx)
        srv = servir(ctx, porta=a.porta)
        url = f"http://127.0.0.1:{a.porta}"
        print(f"🐱 Gatinho servindo em {url}")
        print(f"   projeto: {ctx.projeto}")
        print(f"   modelo:  {ctx.modelo()} ({ctx.config.get('provider')})"
              + ("  [lido do motor]" if sincronizado else ""))
        print("   Ctrl+C encerra.")
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print("\nencerrando…")
        finally:
            srv.shutdown()
            ctx.sessao.salvar()
        return 0

    if a.pedido:                                   # modo nao-interativo
        trabalhar(ctx, " ".join(a.pedido))
        ctx.sessao.salvar()
        return 0

    hist = CAMINHO_GLOBAL.parent / "historico"
    hist.parent.mkdir(parents=True, exist_ok=True)
    teclas = KeyBindings()

    @teclas.add("c-p")                             # requisito 76: mesma lista dos /
    def _(evento):
        buf = evento.app.current_buffer
        if not buf.text.lstrip().startswith("/"):
            buf.insert_text("/")
        buf.start_completion(select_first=False)

    sessao_pt = PromptSession(history=FileHistory(str(hist)),
                              completer=CompletadorDeComandos(),
                              complete_while_typing=True, key_bindings=teclas)

    ui.tela_inicial(ctx)
    while True:
        try:
            entrada = sessao_pt.prompt(
                HTML('<ansiyellow>gatinho></ansiyellow> '),
                bottom_toolbar=lambda: HTML(f"<ansiblack bg='ansiwhite'>"
                                            f"{ui.barra_status(ctx)}</ansiblack>"))
        except KeyboardInterrupt:
            ui.aviso("(Ctrl+C — use /exit para sair)", ui.C_FRACO)
            continue
        except EOFError:
            break
        entrada = (entrada or "").strip()
        if not entrada:
            continue
        if entrada.startswith("/"):
            if not executar_comando(ctx, sessao_pt, entrada):
                break
            continue
        try:
            trabalhar(ctx, entrada, sessao_pt)
        except KeyboardInterrupt:
            ctx.parar = True
            ui.aviso("\nInterrompido. A sessao continua.", ui.C_AVISO)
        except Exception as exc:                                 # noqa: BLE001
            ctx.log("erro", f"trabalho: {type(exc).__name__}: {exc}")
            ui.erro_humano("A tarefa parou por um erro.", f"{type(exc).__name__}: {exc}")

    ctx.sessao.salvar()
    return 0
