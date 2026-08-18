# -*- coding: utf-8 -*-
"""Registro de modelos e provedores — capacidades declaradas (requisitos 84, 85, 13).

Regra dura (requisito 15): nunca fingir que um parametro foi aplicado. Se o modelo
nao suporta `reasoning_effort`, o comando recusa em vez de aceitar em silencio.
"""
from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass, field, asdict
from pathlib import Path

REGISTRY_LOCAL = Path(__file__).parent / "modelos.json"
# Os GGUF moram DENTRO do projeto (ordem do Pai, 2026-08-18): arquivo real em
# servidor/modelos/, nao copia nem atalho. O .gitignore barra *.gguf, entao o
# repositorio sobe sem os 192 GB — quem clonar baixa pelos links do README de la.
MODELOS_DIR = Path(os.environ.get("GATINHO_MODELOS",
                                  Path(__file__).parent.parent / "servidor" / "modelos"))


@dataclass
class Capacidades:
    supports_tools: bool = True
    supports_temperature: bool = True
    supports_top_p: bool = True
    supports_reasoning_effort: bool = False
    supports_streaming: bool = True
    supports_context_override: bool = True
    max_context: int = 16384
    max_output: int = 4096


@dataclass
class Modelo:
    id: str
    provider: str = "local"
    nome: str = ""
    arquivo: str = ""
    cap: Capacidades = field(default_factory=Capacidades)

    def dic(self):
        d = asdict(self)
        d["cap"] = asdict(self.cap)
        return d


@dataclass
class Provedor:
    nome: str
    tipo: str                      # local | openai-compatible | openrouter
    base_url: str = ""
    chave_env: str = ""            # NOME da variavel de ambiente, nunca o valor
    ativo: bool = True

    @property
    def tem_chave(self) -> bool:
        return bool(self.chave_env and os.environ.get(self.chave_env))

    def dic_seguro(self) -> dict:
        """Nunca expoe a chave (requisito 13) — so diz se existe."""
        return {"nome": self.nome, "tipo": self.tipo, "base_url": self.base_url,
                "chave_configurada": self.tem_chave, "ativo": self.ativo}


PROVEDORES_PADRAO = {
    "local": Provedor("local", "openai-compatible", "http://127.0.0.1:8099"),
    "llamacpp": Provedor("llamacpp", "openai-compatible", "http://127.0.0.1:8080"),
    "openrouter": Provedor("openrouter", "openai-compatible",
                           "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "openai": Provedor("openai", "openai-compatible", "https://api.openai.com/v1", "OPENAI_API_KEY"),
}


class Registro:
    """Model registry: descobre no provider quando da, senao usa o registry local."""

    def __init__(self, caminho: Path | None = None):
        self.provedores = dict(PROVEDORES_PADRAO)
        self.modelos: dict[str, Modelo] = {}
        self._carregar(caminho or REGISTRY_LOCAL)

    def _carregar(self, p: Path):
        dados = {}
        if p.exists():
            try:
                dados = json.loads(p.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                dados = {}
        for m in dados.get("modelos", []):
            cap = Capacidades(**(m.get("cap") or {}))
            self.modelos[m["id"]] = Modelo(id=m["id"], provider=m.get("provider", "local"),
                                           nome=m.get("nome", m["id"]), arquivo=m.get("arquivo", ""),
                                           cap=cap)
        for pr in dados.get("provedores", []):
            self.provedores[pr["nome"]] = Provedor(**pr)

    # ------------------------------------------------------------ descoberta
    def descobrir(self, provedor: str, timeout: int = 4) -> list[str]:
        """Pergunta ao provider quais modelos existem (requisito 85).

        Sem rede ou sem servidor, devolve lista vazia — quem chama cai no registry.
        """
        pr = self.provedores.get(provedor)
        if not pr or not pr.base_url:
            return []
        url = pr.base_url.rstrip("/") + "/models"
        req = urllib.request.Request(url)
        if pr.chave_env and os.environ.get(pr.chave_env):
            req.add_header("Authorization", f"Bearer {os.environ[pr.chave_env]}")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                d = json.loads(r.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            return []
        achados = []
        for item in (d.get("data") or d.get("models") or []):
            mid = item.get("id") if isinstance(item, dict) else str(item)
            if not mid:
                continue
            achados.append(mid)
            if mid not in self.modelos:
                self.modelos[mid] = Modelo(id=mid, provider=provedor, nome=mid)
        return achados

    def descobrir_locais(self) -> list[str]:
        """GGUF na pasta de modelos do Pai vira modelo do provider 'local'."""
        achados = []
        if not MODELOS_DIR.exists():
            return achados
        for p in sorted(MODELOS_DIR.glob("*.gguf")):
            mid = p.stem.lower().replace(".gguf", "")
            achados.append(mid)
            if mid not in self.modelos:
                self.modelos[mid] = Modelo(id=mid, provider="local", nome=p.stem, arquivo=str(p))
        return achados

    # ------------------------------------------------------------ consulta
    def caminho(self, m: "Modelo") -> Path | None:
        """O .gguf deste modelo, como caminho ABSOLUTO — ou None se nao existe.

        O modelos.json guarda nome pelado ("Qwen3.5-9B-Q4_1.gguf"). Nome pelado nao
        identifica arquivo nenhum: tem que ser resolvido contra MODELOS_DIR antes de
        virar decisao. Foi assim que o /model tentou abrir um arquivo inexistente.
        """
        if not m or not m.arquivo:
            return None
        p = Path(m.arquivo)
        if not p.is_absolute():
            p = MODELOS_DIR / p.name
        return p if p.is_file() else None

    def get(self, mid: str) -> Modelo | None:
        if mid in self.modelos:
            return self.modelos[mid]
        alvo = mid.lower()
        for k, v in self.modelos.items():
            if k.lower() == alvo or alvo in k.lower():
                return v
        return None

    def cap(self, mid: str) -> Capacidades:
        m = self.get(mid)
        return m.cap if m else Capacidades()

    def listar(self, provedor: str | None = None) -> list[Modelo]:
        ms = list(self.modelos.values())
        if provedor:
            ms = [m for m in ms if m.provider == provedor]
        return sorted(ms, key=lambda m: (m.provider, m.id))


def checar_parametro(cap: Capacidades, parametro: str) -> tuple[bool, str]:
    """Devolve (suportado, mensagem). Usado por /effort, /temperature, /top-p."""
    mapa = {
        "reasoning_effort": (cap.supports_reasoning_effort, "Este modelo nao suporta reasoning effort."),
        "temperature": (cap.supports_temperature, "Este modelo nao aceita temperatura."),
        "top_p": (cap.supports_top_p, "Este modelo nao aceita top-p."),
        "tools": (cap.supports_tools, "Este modelo nao suporta tool calling."),
        "context": (cap.supports_context_override, "Este modelo nao permite mudar a janela."),
    }
    ok, msg = mapa.get(parametro, (True, ""))
    return ok, ("" if ok else msg)
