# -*- coding: utf-8 -*-
"""Configuracao com hierarquia — o mais especifico vence (requisito 86).

    defaults internos  ->  config global  ->  config do projeto  ->  sessao/CLI

Global:  ~/.config/gatinho/config.json
Projeto: <cwd>/.gatinho/config.json
"""
from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULTS = {
    "model": "deltacoder-9b",
    "provider": "local",
    "context": 16384,
    "effort": "medium",
    "temperature": 0.2,
    "top_p": 0.95,
    "max_output": 4096,
    "harness": "mast-agent",   # V3.1: o A/B mandou. auto so volta com evidencia
    "mode": "plan",
    "verbose": "normal",
    "router": {"threshold": 3000},
    "tools": {"max_per_step": 4},
    "permissions": {"leitura": "allow", "escrita": "allow", "shell": "ask",
                    "git": "ask", "internet": "deny", "arquivos_externos": "deny"},
    "auto_approve": False,
}

CAMINHO_GLOBAL = Path(os.environ.get("GATINHO_CONFIG_HOME",
                                     Path.home() / ".config" / "gatinho")) / "config.json"
NOME_PROJETO = ".gatinho/config.json"


def _funde(base: dict, novo: dict) -> dict:
    """Funde recursivo: dicionario aninhado nao e substituido inteiro."""
    saida = dict(base)
    for k, v in (novo or {}).items():
        if isinstance(v, dict) and isinstance(saida.get(k), dict):
            saida[k] = _funde(saida[k], v)
        else:
            saida[k] = v
    return saida


def _le(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


class Config:
    """Guarda as camadas separadas para saber DE ONDE cada valor veio."""

    def __init__(self, projeto: Path | None = None, overrides: dict | None = None):
        self.projeto = Path(projeto or Path.cwd())
        self.camada_global = _le(CAMINHO_GLOBAL)
        self.camada_projeto = _le(self.projeto / NOME_PROJETO)
        self.camada_sessao = dict(overrides or {})
        self._recalcula()

    def _recalcula(self):
        v = _funde(DEFAULTS, self.camada_global)
        v = _funde(v, self.camada_projeto)
        self.valores = _funde(v, self.camada_sessao)

    # ---------------------------------------------------------------- acesso
    def get(self, caminho: str, padrao=None):
        """get('router.threshold') anda no dicionario aninhado."""
        no = self.valores
        for parte in caminho.split("."):
            if not isinstance(no, dict) or parte not in no:
                return padrao
            no = no[parte]
        return no

    def origem(self, caminho: str) -> str:
        """De qual camada veio o valor — usado por /config e /status."""
        for nome, camada in (("sessao", self.camada_sessao), ("projeto", self.camada_projeto),
                             ("global", self.camada_global), ("padrao", DEFAULTS)):
            no = camada
            achou = True
            for parte in caminho.split("."):
                if not isinstance(no, dict) or parte not in no:
                    achou = False
                    break
                no = no[parte]
            if achou:
                return nome
        return "desconhecido"

    def set(self, caminho: str, valor, camada: str = "sessao"):
        alvo = {"sessao": self.camada_sessao, "projeto": self.camada_projeto,
                "global": self.camada_global}[camada]
        no = alvo
        partes = caminho.split(".")
        for parte in partes[:-1]:
            no = no.setdefault(parte, {})
        no[partes[-1]] = valor
        self._recalcula()
        return self.get(caminho)

    def salvar(self, camada: str = "global"):
        if camada == "global":
            CAMINHO_GLOBAL.parent.mkdir(parents=True, exist_ok=True)
            CAMINHO_GLOBAL.write_text(json.dumps(self.camada_global, indent=2, ensure_ascii=False),
                                      encoding="utf-8")
            return CAMINHO_GLOBAL
        p = self.projeto / NOME_PROJETO
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.camada_projeto, indent=2, ensure_ascii=False), encoding="utf-8")
        return p


def tamanho_contexto(txt: str) -> int:
    """Aceita '32k', '128K', '16384'. Devolve tokens."""
    t = str(txt).strip().lower().replace(" ", "")
    if t.endswith("k"):
        return int(float(t[:-1]) * 1024)
    return int(float(t))


def humano(n: int) -> str:
    """16384 -> '16K'; 3200 -> '3.2K'."""
    if n is None:
        return "—"
    if n < 1000:
        return str(n)
    k = n / 1024
    return f"{k:.0f}K" if abs(k - round(k)) < 0.05 else f"{k:.1f}K"
