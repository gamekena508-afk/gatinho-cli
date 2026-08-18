# -*- coding: utf-8 -*-
"""Sessoes: criar, listar, retomar, renomear, apagar, compactar (requisitos 22-29, 87).

Cada sessao guarda o que o requisito 22 pede e mais o que o 87 exige para nao
repetir investigacao: objetivo, decisoes, arquivos relevantes, progresso, erros.

Um arquivo JSON por sessao em ~/.local/share/gatinho/sessoes/.
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path

RAIZ_SESSOES = Path(os.environ.get(
    "GATINHO_DATA_HOME", Path.home() / ".local" / "share" / "gatinho")) / "sessoes"


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _idade(iso: str) -> str:
    try:
        t = datetime.fromisoformat(iso)
    except Exception:  # noqa: BLE001
        return "?"
    seg = (datetime.now(timezone.utc) - t).total_seconds()
    if seg < 90:
        return "agora"
    if seg < 3600:
        return f"ha {int(seg // 60)} min"
    if seg < 86400:
        return f"ha {int(seg // 3600)}h"
    if seg < 172800:
        return "ontem"
    return t.strftime("%d %b").lower()


@dataclass
class Sessao:
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    nome: str = ""
    created_at: str = field(default_factory=_agora)
    updated_at: str = field(default_factory=_agora)
    project: str = ""
    model: str = ""
    provider: str = ""
    harness: str = "auto"
    context: int = 16384
    messages: list = field(default_factory=list)
    files: dict = field(default_factory=dict)        # caminho -> lido|editado|criado
    tool_history: list = field(default_factory=list)
    # memoria da tarefa (requisito 87)
    objetivo: str = ""
    decisoes: list = field(default_factory=list)
    erros: list = field(default_factory=list)
    plano: dict = field(default_factory=dict)
    runs: list = field(default_factory=list)
    compaction_count: int = 0
    skills_carregadas: list = field(default_factory=list)

    # ---------------------------------------------------------------- edicao
    def mensagem(self, papel: str, texto: str, **extra):
        self.messages.append({"role": papel, "content": texto, "ts": _agora(), **extra})
        self.updated_at = _agora()
        if papel == "user" and not self.objetivo:
            self.objetivo = texto.strip()[:300]
        if papel == "user" and not self.nome:
            self.nome = self.sugerir_nome(texto)

    @staticmethod
    def sugerir_nome(texto: str) -> str:
        limpo = re.sub(r"[^a-z0-9\s-]", "", texto.lower().strip())
        palavras = [p for p in limpo.split() if len(p) > 2][:3]
        return "-".join(palavras)[:40] or "sessao"

    def tocar_arquivo(self, caminho: str, acao: str):
        """acao: lido | editado | criado. Editado/criado nao regride para lido."""
        atual = self.files.get(caminho)
        if atual in ("criado", "editado") and acao == "lido":
            return
        self.files[caminho] = acao
        self.updated_at = _agora()

    def registrar_tool(self, nome: str, args: dict, resultado: str, erro: bool):
        self.tool_history.append({"tool": nome, "args": args, "erro": erro,
                                  "resumo": (resultado or "")[:200], "ts": _agora()})

    def decidir(self, texto: str):
        self.decisoes.append({"texto": texto, "ts": _agora()})

    # ---------------------------------------------------- compactacao (29)
    def compactar(self, manter: int = 8) -> tuple[int, int]:
        """Preserva objetivo, decisoes, arquivos e as ultimas `manter` mensagens.

        Devolve (antes, depois) em caracteres — o chamador converte para tokens.
        """
        antes = sum(len(str(m.get("content") or "")) for m in self.messages)
        if len(self.messages) <= manter + 2:
            return antes, antes
        cabeca = self.messages[:1]
        miolo = self.messages[1:-manter]
        fim = self.messages[-manter:]

        arquivos = ", ".join(f"{k} ({v})" for k, v in list(self.files.items())[:10]) or "nenhum"
        decisoes = "; ".join(d["texto"] for d in self.decisoes[-5:]) or "nenhuma registrada"
        erros = "; ".join(str(e)[:80] for e in self.erros[-3:]) or "nenhum"
        resumo = (
            "[historico compactado — o essencial foi preservado]\n"
            f"objetivo: {self.objetivo or '(nao registrado)'}\n"
            f"arquivos ja tocados: {arquivos}\n"
            f"decisoes ja tomadas: {decisoes}\n"
            f"erros ja vistos (nao repita): {erros}\n"
            f"({len(miolo)} mensagens antigas resumidas nesta linha)"
        )
        self.messages = cabeca + [{"role": "system", "content": resumo, "ts": _agora(),
                                   "compactado": True}] + fim
        self.compaction_count += 1
        self.updated_at = _agora()
        depois = sum(len(str(m.get("content") or "")) for m in self.messages)
        return antes, depois

    # --------------------------------------------------------- persistencia
    def caminho(self) -> Path:
        return RAIZ_SESSOES / f"{self.session_id}.json"

    def salvar(self) -> Path:
        RAIZ_SESSOES.mkdir(parents=True, exist_ok=True)
        p = self.caminho()
        p.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")
        return p

    @classmethod
    def carregar(cls, session_id: str) -> "Sessao | None":
        p = RAIZ_SESSOES / f"{session_id}.json"
        if not p.exists():
            achados = list(RAIZ_SESSOES.glob(f"{session_id}*.json")) if RAIZ_SESSOES.exists() else []
            if not achados:
                return None
            p = achados[0]
        try:
            return cls(**json.loads(p.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001
            return None


def listar(limite: int = 20, projeto: str | None = None) -> list[dict]:
    """Resumo das sessoes, mais recente primeiro (requisito 24)."""
    if not RAIZ_SESSOES.exists():
        return []
    saida = []
    for p in RAIZ_SESSOES.glob("*.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if projeto and d.get("project") != projeto:
            continue
        saida.append({"session_id": d.get("session_id", p.stem),
                      "nome": d.get("nome") or "(sem nome)",
                      "updated_at": d.get("updated_at", ""),
                      "idade": _idade(d.get("updated_at", "")),
                      "model": d.get("model", ""), "project": d.get("project", ""),
                      "mensagens": len(d.get("messages", []))})
    saida.sort(key=lambda x: x["updated_at"], reverse=True)
    return saida[:limite]


def apagar(session_id: str) -> bool:
    p = RAIZ_SESSOES / f"{session_id}.json"
    if p.exists():
        p.unlink()
        return True
    return False


def exportar(s: Sessao, formato: str = "markdown") -> str:
    """requisito 69 — json ou markdown."""
    if formato == "json":
        return json.dumps(asdict(s), indent=2, ensure_ascii=False)
    linhas = [f"# {s.nome or s.session_id}", "",
              f"- sessao: `{s.session_id}`", f"- projeto: {s.project}",
              f"- modelo: {s.model} ({s.provider})", f"- criada: {s.created_at}", ""]
    if s.objetivo:
        linhas += ["## Objetivo", "", s.objetivo, ""]
    if s.files:
        linhas += ["## Arquivos", ""] + [f"- `{k}` — {v}" for k, v in s.files.items()] + [""]
    linhas += ["## Conversa", ""]
    for m in s.messages:
        quem = {"user": "Voce", "assistant": "Gatinho", "system": "sistema"}.get(m["role"], m["role"])
        linhas += [f"**{quem}:**", "", str(m.get("content") or ""), ""]
    return "\n".join(linhas)
