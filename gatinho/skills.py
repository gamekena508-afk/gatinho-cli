# -*- coding: utf-8 -*-
"""Skills: instrucoes reutilizaveis (requisitos 30-33).

Reaproveita o formato que ja existe na maquina do Pai (pasta com SKILL.md e
frontmatter YAML simples). Nao recria o que ja funciona — le de:

    <projeto>/.gatinho/skills/
    ~/.config/gatinho/skills/
    ~/.claude/skills/            (as skills que ele ja tem)
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

FONTES = [
    Path.cwd() / ".gatinho" / "skills",
    Path(os.environ.get("GATINHO_CONFIG_HOME", Path.home() / ".config" / "gatinho")) / "skills",
    Path.home() / ".claude" / "skills",
]

EMBUTIDAS = {
    "pytest": "Rodar e interpretar pytest: -q para resumo, ler a linha FAILED, "
              "consertar a causa e rodar de novo antes de encerrar.",
    "git": "Status, diff e commit. Nunca commitar sem pedido explicito.",
    "debug": "Ler a mensagem de erro inteira, achar a origem do dado errado e "
             "corrigir na origem — nao mascarar com try/except.",
    "refactor": "Mudar estrutura sem mudar comportamento. Provar com o teste que "
                "ja existia antes da mudanca.",
    "security": "Nao imprimir segredo, nao commitar credencial, recusar comando "
                "destrutivo fora do workspace.",
    "frontend": "HTML/CSS/JS: conferir o render de verdade, nao so o build.",
    "backend": "API e dados: validar entrada, tratar erro, testar caso vazio.",
}


@dataclass
class Skill:
    nome: str
    descricao: str = ""
    caminho: str = ""
    corpo: str = ""
    ativa: bool = True
    embutida: bool = False

    def resumo(self) -> str:
        return (self.descricao or self.corpo[:160]).strip().replace("\n", " ")


class Skills:
    def __init__(self, fontes: list[Path] | None = None):
        self.itens: dict[str, Skill] = {}
        self.fontes = fontes if fontes is not None else FONTES
        self.recarregar()

    def recarregar(self) -> int:
        self.itens = {n: Skill(nome=n, descricao=d, embutida=True) for n, d in EMBUTIDAS.items()}
        for base in self.fontes:
            if not base.exists():
                continue
            for p in sorted(base.iterdir()):
                md = p / "SKILL.md" if p.is_dir() else (p if p.suffix == ".md" else None)
                if not md or not md.exists():
                    continue
                try:
                    txt = md.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                nome, desc = p.stem if p.is_dir() else md.stem, ""
                m = re.match(r"^---\s*\n(.*?)\n---\s*\n", txt, re.S)
                if m:
                    fm = m.group(1)
                    n = re.search(r"^name:\s*(.+)$", fm, re.M)
                    d = re.search(r"^description:\s*(.+)$", fm, re.M)
                    if n:
                        nome = n.group(1).strip()
                    if d:
                        desc = d.group(1).strip()
                    txt = txt[m.end():]
                self.itens[nome] = Skill(nome=nome, descricao=desc, caminho=str(md), corpo=txt)
        return len(self.itens)

    def listar(self, so_ativas=False) -> list[Skill]:
        v = [s for s in self.itens.values() if s.ativa or not so_ativas]
        return sorted(v, key=lambda s: s.nome)

    def get(self, nome: str) -> Skill | None:
        if nome in self.itens:
            return self.itens[nome]
        alvo = nome.lower()
        for k, v in self.itens.items():
            if k.lower() == alvo or alvo in k.lower():
                return v
        return None

    def ligar(self, nome: str, ativa: bool) -> bool:
        s = self.get(nome)
        if not s:
            return False
        s.ativa = ativa
        return True

    # ------------------------------------------------- selecao automatica (33)
    GATILHOS = {
        "pytest": [r"\btest", r"\bpytest\b", r"\bfalh"],
        "debug": [r"\bbug\b", r"\berro\b", r"\bexception\b", r"\btraceback\b", r"\bcausa\b"],
        "refactor": [r"\brefator", r"\blimpar?\s+o?\s*codigo", r"\bsimplific"],
        "git": [r"\bgit\b", r"\bcommit\b", r"\bbranch\b"],
        "security": [r"\bseguran", r"\bcredencia", r"\bsenha\b", r"\bsecret"],
        "frontend": [r"\bhtml\b", r"\bcss\b", r"\bcomponente\b", r"\btela\b"],
        "backend": [r"\bapi\b", r"\bendpoint\b", r"\brota\b", r"\bbanco\b"],
    }

    def sugerir(self, pedido: str) -> list[str]:
        p = (pedido or "").lower()
        achadas = []
        for nome, padroes in self.GATILHOS.items():
            s = self.get(nome)
            if s and s.ativa and any(re.search(x, p) for x in padroes):
                achadas.append(s.nome)
        return achadas

    def prompt_das(self, nomes: list[str], limite_por_skill: int = 400) -> str:
        blocos = []
        for n in nomes:
            s = self.get(n)
            if not s:
                continue
            corpo = (s.corpo or s.descricao or "").strip()[:limite_por_skill]
            if corpo:
                blocos.append(f"[skill: {s.nome}]\n{corpo}")
        return "\n\n".join(blocos)
