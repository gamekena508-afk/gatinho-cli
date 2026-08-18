# -*- coding: utf-8 -*-
"""Camada de desenho. Nao contem regra de negocio (requisito 94).

Decisao de layout, registrada: o requisito 77 pede uma barra de status "superior".
Num terminal que ROLA (que e o pedido: algo como Claude Code/OpenCode, nao um
dashboard de painel fixo), uma barra no topo sobe junto com o scroll e some.
Entao a barra permanente vive no rodape do prompt (`bottom_toolbar`), que fica
sempre colada no input, e o cabecalho e impresso no topo da tela ao abrir e a
cada /clear. Conteudo e ordem sao os do requisito 77.
"""
from __future__ import annotations

import shutil

from rich.cells import cell_len
from rich.console import Console
from rich.text import Text

from .config import humano

console = Console()

# paleta enxuta (requisito 90)
C_TEXTO, C_FRACO = "grey85", "grey50"
C_INFO, C_OK, C_AVISO, C_ERRO = "cyan", "green", "yellow", "red"
C_GATO = "yellow"

GATO = r""" /\_/\
( ^.^ )
 > ^ <"""

SIMBOLO = {"acao": "●", "ok": "✓", "erro": "✗", "info": "●"}
COR_EV = {"acao": C_INFO, "ok": C_OK, "erro": C_ERRO, "info": C_FRACO}


def largura() -> int:
    return shutil.get_terminal_size((80, 24)).columns


# ------------------------------------------------------------------ cabecalho
def cabecalho(ctx):
    """Impresso no topo da tela (abertura e /clear)."""
    m = ctx.metricas
    esq = Text("🐱 GATINHO CLI ", style=f"bold {C_GATO}")
    esq.append(f" v{ctx.versao}", style=C_FRACO)
    dir_ = Text()
    dir_.append(f"{humano(m.contexto_atual)} / {humano(ctx.janela())}", style=C_TEXTO)
    dir_.append("   ")
    dir_.append(ctx.modelo(), style=C_TEXTO)
    dir_.append("   ")
    cor_modo = C_INFO if ctx.modo == "plan" else C_OK
    dir_.append(ctx.nome_modo(), style=f"bold {cor_modo}")
    if ctx.executando:
        dir_.append(" ●", style=C_OK)
    # cell_len, nao len: 🐱 ocupa DUAS colunas no terminal. Com len() a barra
    # estourava a largura e quebrava linha (visto no pty a 92 colunas).
    espaco = largura() - cell_len(esq.plain) - cell_len(dir_.plain)
    if espaco < 1:                       # terminal estreito: corta o que e opcional
        dir_ = Text(f"{humano(m.contexto_atual)}/{humano(ctx.janela())}  {ctx.nome_modo()}",
                    style=C_TEXTO)
        espaco = max(1, largura() - cell_len(esq.plain) - cell_len(dir_.plain))
    console.print(Text.assemble(esq, " " * espaco, dir_))
    console.print("─" * largura(), style="grey30")


def tela_inicial(ctx):
    console.clear()
    cabecalho(ctx)
    alt = shutil.get_terminal_size((80, 24)).lines
    console.print("\n" * max(1, (alt - 16) // 3), end="")
    linhas = GATO.splitlines()
    larg_bloco = max(cell_len(l) for l in linhas)
    pad = " " * max(0, (largura() - larg_bloco) // 2)
    for linha in linhas:
        console.print(Text(pad + linha, style=C_GATO))
    console.print()
    console.print(Text("GATINHO CLI".center(largura()), style=f"bold {C_TEXTO}"))
    console.print(Text(f"v{ctx.versao}".center(largura()), style=C_FRACO))
    console.print()
    console.print(Text("Seu agente de coding.".center(largura()), style=C_FRACO))
    console.print()
    console.print(Text("/help para ver os comandos".center(largura()), style=C_FRACO))
    console.print()


# -------------------------------------------------------------------- eventos
def evento(ev, verbose="normal"):
    """Uma linha por acao (requisito 47). Detalhe fica recolhido (requisito 48)."""
    if verbose == "quiet" and ev["tipo"] not in ("erro", "ok"):
        return
    cor = COR_EV.get(ev["tipo"], C_FRACO)
    marca = "▶" if (ev.get("detalhe") and not ev.get("aberto")) else SIMBOLO.get(ev["tipo"], "●")
    console.print(Text.assemble((f"{marca} ", cor), (ev["texto"], C_TEXTO)))
    if ev.get("detalhe") and (ev.get("aberto") or verbose in ("verbose", "debug")):
        for linha in str(ev["detalhe"]).splitlines()[:40]:
            console.print(Text("   " + linha, style=C_FRACO))


def resposta(r, verbose="normal"):
    """Desenha o retorno de um comando."""
    if r.titulo:
        console.print()
        console.print(Text(r.titulo, style=f"bold {C_INFO if not r.erro else C_ERRO}"))
    estilo = C_ERRO if r.erro else (C_OK if r.ok else C_TEXTO)
    for linha in r.linhas:
        console.print(Text(linha, style=estilo if (r.erro or r.ok) else C_TEXTO))
    if r.escolhas:
        for e in r.escolhas:
            marca = "●" if e.get("ativo") else " "
            t = Text.assemble((f"{marca} ", C_OK if e.get("ativo") else C_FRACO),
                              (e["rotulo"], C_TEXTO))
            if e.get("detalhe"):
                t.append(f"   {e['detalhe']}", style=C_FRACO)
            console.print(t)
    console.print()


def fala_do_gatinho(texto: str):
    console.print()
    console.print(Text("Gatinho:", style=f"bold {C_GATO}"))
    console.print(Text(texto, style=C_TEXTO))
    console.print()


def fala_do_usuario(texto: str):
    console.print()
    console.print(Text("Você:", style=f"bold {C_TEXTO}"))
    console.print(Text(texto, style=C_FRACO))


def aviso(texto: str, cor=C_AVISO):
    console.print(Text(texto, style=cor))


def erro_humano(titulo: str, motivo: str = ""):
    """requisito 89 — erro legivel, sem stack trace por padrao."""
    console.print(Text(f"✗ {titulo}", style=C_ERRO))
    if motivo:
        console.print(Text(f"  Motivo: {motivo}", style=C_FRACO))
    console.print(Text("  /debug mostra o detalhe tecnico.", style=C_FRACO))


def barra_status(ctx) -> str:
    """Texto do rodape fixo — o mesmo conteudo do requisito 77."""
    m = ctx.metricas
    ponto = " ●" if ctx.executando else ""
    return (f" 🐱 GATINHO v{ctx.versao}   "
            f"{humano(m.contexto_atual)} / {humano(ctx.janela())}   "
            f"{ctx.modelo()}   {ctx.nome_modo()}{ponto}")
