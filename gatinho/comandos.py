# -*- coding: utf-8 -*-
"""Command router central (requisitos 9, 95, 96).

Um unico registro. Nada de `if comando == ...` espalhado.
Cada comando declara: name, aliases, description, usage, handler, category, autocomplete.

Os handlers sao PUROS: recebem (ctx, args) e devolvem uma `Resposta` — nao imprimem
nada. Quem desenha e a UI. E o que torna o requisito 97 (testar tudo) possivel sem
abrir terminal.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

REGISTRO: dict[str, "Comando"] = {}
ALIASES: dict[str, str] = {}


@dataclass
class Resposta:
    """O que o handler devolve. `escolhas` vira menu; `acao` a UI interpreta."""
    linhas: list = field(default_factory=list)
    titulo: str = ""
    escolhas: list = field(default_factory=list)   # [{"rotulo","valor","ativo"}]
    acao: str = ""                                  # sair | limpar | novo | ...
    dados: dict = field(default_factory=dict)
    erro: bool = False
    ok: bool = False

    @property
    def texto(self) -> str:
        return "\n".join(self.linhas)


@dataclass
class Comando:
    name: str
    description: str
    handler: Callable
    usage: str = ""
    aliases: tuple = ()
    category: str = "geral"
    autocomplete: tuple = ()       # subcomandos sugeridos


def comando(name, description, usage="", aliases=(), category="geral", autocomplete=()):
    def deco(fn):
        c = Comando(name=name, description=description, handler=fn, usage=usage or f"/{name}",
                    aliases=tuple(aliases), category=category, autocomplete=tuple(autocomplete))
        REGISTRO[name] = c
        for a in aliases:
            ALIASES[a] = name
        return fn
    return deco


# ------------------------------------------------------------------ resolver

def resolver(entrada: str):
    """'/temp 0.3' -> (Comando, ['0.3']). Devolve (None, []) se nao for comando."""
    txt = (entrada or "").strip()
    if not txt.startswith("/"):
        return None, []
    partes = txt[1:].split()
    if not partes:
        return None, []
    nome = partes[0].lower()
    nome = ALIASES.get(nome, nome)
    return REGISTRO.get(nome), partes[1:]


def sugestoes(prefixo: str) -> list[dict]:
    """Autocomplete (requisito 75). '/mo' -> /model, /models, /mode.

    Com espaco depois do comando, sugere os subcomandos dele.
    """
    # lstrip apenas: o espaco FINAL e significativo ("/session " pede os
    # subcomandos de session, nao os comandos que comecam com "session").
    txt = (prefixo or "").lstrip()
    if not txt.startswith("/"):
        return []
    corpo = txt[1:]
    if " " in corpo:
        nome, _, resto = corpo.partition(" ")
        nome = ALIASES.get(nome.lower(), nome.lower())
        c = REGISTRO.get(nome)
        if not c:
            return []
        return [{"valor": f"/{c.name} {s}", "descricao": f"{c.name} {s}"}
                for s in c.autocomplete if s.startswith(resto.strip())]
    vistos, saida = set(), []
    for nome, c in sorted(REGISTRO.items()):
        if nome.startswith(corpo.lower()) and nome not in vistos:
            vistos.add(nome)
            saida.append({"valor": f"/{nome}", "descricao": c.description})
    for alias, destino in sorted(ALIASES.items()):
        if alias.startswith(corpo.lower()) and destino not in vistos:
            vistos.add(destino)
            saida.append({"valor": f"/{alias}", "descricao": REGISTRO[destino].description})
    return saida


def por_categoria() -> dict:
    cats: dict[str, list] = {}
    for c in REGISTRO.values():
        cats.setdefault(c.category, []).append(c)
    for v in cats.values():
        v.sort(key=lambda c: c.name)
    return cats
