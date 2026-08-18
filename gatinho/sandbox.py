# -*- coding: utf-8 -*-
"""Sandbox por sessao — cada conversa ganha a propria pasta em `works/`.

Razao (ordem do Pai, 2026-08-17): *"modelos locais nao sao tao confiaveis"*.
O harness-bench mediu isso: modelo escrevendo `}` solto e matando o arquivo,
`edit` acertando o trecho errado, agente alterando o arquivo de teste em vez de
consertar o codigo. Numa pasta descartavel isso e um experimento; no projeto do
Pai, e estrago.

Entao o padrao e:  trabalhar em works/<sessao>/ .
E fica a porta aberta:  modo DIRETO, que trabalha no projeto de verdade — mas
avisando, marcando na tela e registrando na sessao.
"""
from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

RAIZ_PROJETO = Path(__file__).parent.parent
WORKS = Path(os.environ.get("GATINHO_WORKS", RAIZ_PROJETO / "works"))

MODO_SANDBOX = "sandbox"   # works/<sessao> — padrao
MODO_DIRETO = "direto"     # a pasta que o usuario abriu — sob aviso


def _limpo(nome: str) -> str:
    n = re.sub(r"[^a-z0-9-]+", "-", (nome or "").lower()).strip("-")
    return (n or "sessao")[:40]


@dataclass
class Work:
    caminho: str
    criado_em: str
    sessao_id: str
    nome: str
    origem: str = ""          # pasta que o usuario abriu, quando houve semente
    modo: str = MODO_SANDBOX

    @property
    def p(self) -> Path:
        return Path(self.caminho)

    def dic(self):
        return asdict(self)


def criar(sessao_id: str, nome: str = "", origem: Path | None = None) -> Work:
    """Cria works/<data>-<hora>-<nome>/ para esta sessao."""
    WORKS.mkdir(parents=True, exist_ok=True)
    carimbo = datetime.now().strftime("%Y%m%d-%H%M")
    pasta = WORKS / f"{carimbo}-{_limpo(nome or sessao_id[:8])}"
    n = 2
    while pasta.exists():
        pasta = WORKS / f"{carimbo}-{_limpo(nome or sessao_id[:8])}-{n}"
        n += 1
    pasta.mkdir(parents=True)
    w = Work(caminho=str(pasta), criado_em=datetime.now().isoformat(timespec="seconds"),
             sessao_id=sessao_id, nome=nome or pasta.name,
             origem=str(origem or ""), modo=MODO_SANDBOX)
    (pasta / ".gatinho-work.json").write_text(
        json.dumps(w.dic(), indent=2, ensure_ascii=False), encoding="utf-8")
    return w


# arquivos que fazem sentido levar para dentro do work quando o usuario pede
EXT_SEMENTE = {".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".md", ".txt", ".toml",
               ".yaml", ".yml", ".html", ".css", ".sh", ".cfg", ".ini", ".rs", ".go"}
IGNORAR = {".git", "__pycache__", ".pytest_cache", "node_modules", ".venv", "venv",
           "works", "assets", ".gatinho"}
LIMITE_ARQUIVOS = 400
LIMITE_BYTES = 8 * 1024 * 1024


def semear(w: Work, origem: Path) -> tuple[int, int, list]:
    """Copia o projeto para dentro do work, para o agente mexer numa COPIA.

    Devolve (arquivos, bytes, avisos). Nunca segue link simbolico e nunca copia
    binario grande — o objetivo e dar contexto, nao clonar o disco.
    """
    origem = Path(origem)
    arquivos = bytes_ = 0
    avisos = []
    if not origem.exists():
        return 0, 0, [f"pasta de origem nao existe: {origem}"]
    for p in sorted(origem.rglob("*")):
        if arquivos >= LIMITE_ARQUIVOS or bytes_ >= LIMITE_BYTES:
            avisos.append("parei de copiar no limite (400 arquivos ou 8 MB)")
            break
        rel = p.relative_to(origem)
        if any(x in rel.parts for x in IGNORAR) or p.is_symlink():
            continue
        if p.is_dir():
            continue
        if p.suffix and p.suffix not in EXT_SEMENTE:
            continue
        try:
            tam = p.stat().st_size
        except OSError:
            continue
        if tam > 512 * 1024:
            avisos.append(f"pulei {rel} ({tam//1024} KB)")
            continue
        destino = w.p / rel
        destino.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(p, destino)
        except OSError as exc:
            avisos.append(f"nao copiei {rel}: {exc}")
            continue
        arquivos += 1
        bytes_ += tam
    return arquivos, bytes_, avisos


def listar(limite: int = 30) -> list[dict]:
    if not WORKS.exists():
        return []
    saida = []
    for p in sorted(WORKS.iterdir(), reverse=True):
        if not p.is_dir():
            continue
        meta = p / ".gatinho-work.json"
        d = {}
        if meta.exists():
            try:
                d = json.loads(meta.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                d = {}
        arquivos = sum(1 for x in p.rglob("*") if x.is_file() and x.name != ".gatinho-work.json")
        saida.append({"nome": p.name, "caminho": str(p), "arquivos": arquivos,
                      "criado_em": d.get("criado_em", ""), "sessao_id": d.get("sessao_id", "")})
    return saida[:limite]


def apagar(nome: str) -> tuple[bool, str]:
    alvo = (WORKS / nome).resolve()
    if not str(alvo).startswith(str(WORKS.resolve())):
        return False, "caminho fora de works/ — recusado"
    if not alvo.exists():
        return False, f"work '{nome}' nao existe"
    shutil.rmtree(alvo)
    return True, f"work '{nome}' apagado"


def tamanho_total() -> tuple[int, int]:
    """(pastas, bytes) de tudo em works/."""
    if not WORKS.exists():
        return 0, 0
    pastas = sum(1 for p in WORKS.iterdir() if p.is_dir())
    bytes_ = sum(p.stat().st_size for p in WORKS.rglob("*") if p.is_file())
    return pastas, bytes_


AVISO_DIRETO = (
    "MODO DIRETO: o agente vai escrever na pasta de verdade, fora da sandbox. "
    "Modelo local erra — ele ja apagou chave de fechamento e editou arquivo de teste "
    "em vez do codigo, nos testes. Tenha o git limpo antes."
)
