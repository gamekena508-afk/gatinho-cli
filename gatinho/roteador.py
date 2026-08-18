# -*- coding: utf-8 -*-
"""Roteador V3.1 — mast-agent por padrao; fast so com razao concreta.

Historia curta, porque ela e a licao:

  V3.0 leu "ate 3K os dois empatam" como "ate 3K use o fast". Nao e a mesma coisa.
  O empate era em TAXA DE SUCESSO. Em QUALIDADE o mast ganhou ate nas rapidas.

A/B com 30 execucoes por configuracao (5 modelos x 6 tarefas, servidor conferido):

    config     sucesso   qualidade   tempo
    V2 fast     21/30      3.80      26min
    V2 mast     23/30      4.17      30min     <- melhor em tudo
    V3 auto     22/30      3.97      40min     <- pior E mais lento

Entao (V3.1):
  - o padrao e mast-agent;
  - fast entra quando o pedido prioriza LATENCIA e a tarefa e realmente curta
    (<= LIMIAR_CURTO), sem sinal de investigacao;
  - qualquer sinal de contexto grande, muitos arquivos ou investigacao -> mast.

Registra sempre: context_estimate, router_threshold, selected_harness, router_reason.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from pathlib import Path

LIMIAR_PADRAO = 3000
LIMIAR_ARQUIVOS = 6
# V3.1: mesmo com pressa, o fast so entra em tarefa REALMENTE curta.
LIMIAR_CURTO = 2000

# custo fixo de qualquer execucao: system prompt + esquema das ferramentas + margem.
# Calibrado contra o pico real da tarefa mais simples do bench (r1: 1505 tokens
# com semente vazia).
BASE_TOKENS = 1200
# cada byte de arquivo relevante volta mais de uma vez (leitura + releitura apos
# escrita). Fator medido: pico/conteudo ficou entre 1,5 e 2,1 nas tarefas longas.
FATOR_RELEITURA = 2.0

IGNORAR = {".git", "__pycache__", ".pytest_cache", "node_modules", ".venv", "venv", ".gatinho"}
EXT_TEXTO = {".py", ".js", ".ts", ".tsx", ".jsx", ".md", ".txt", ".json", ".toml", ".yaml",
             ".yml", ".html", ".css", ".sh", ".cfg", ".ini", ".rs", ".go", ".c", ".h", ".cpp", ".java"}

SINAIS_INVESTIGACAO = [
    r"\binvestig", r"\bache?\s+a?\s*causa", r"\bcausa\s+raiz", r"\bdebug",
    r"\bpor\s*que\b", r"\bdescubr", r"\brastrei", r"\bauditor",
    r"\brefator", r"\bmigrar?\b", r"\breescrev", r"\bbugs?\b.*\b(varios|espalhad|multipl)",
    r"\bv[aá]rios\s+arquivos", r"\bo\s+projeto\s+(inteiro|todo)",
]


@dataclass
class Decisao:
    context_estimate: int
    router_threshold: int
    selected_harness: str
    router_reason: str
    arquivos: int = 0
    bytes_conteudo: int = 0
    sinais: tuple = ()
    forcado: bool = False

    def dic(self):
        d = asdict(self)
        d["sinais"] = list(self.sinais)
        return d


def medir_workspace(raiz: Path, alvos: list[str] | None = None) -> tuple[int, int]:
    """(arquivos, bytes) do que provavelmente entra no contexto."""
    raiz = Path(raiz)
    if alvos:
        caminhos = [raiz / a for a in alvos]
    else:
        caminhos = [p for p in raiz.rglob("*") if p.is_file()]
    arquivos = total = 0
    for p in caminhos:
        try:
            if not p.is_file() or any(x in p.parts for x in IGNORAR) or p.name.startswith("_"):
                continue
            if p.suffix and p.suffix not in EXT_TEXTO:
                continue
            total += p.stat().st_size
            arquivos += 1
        except OSError:
            continue
    return arquivos, total


def estimar_contexto(raiz: Path, prompt: str = "", alvos: list[str] | None = None) -> tuple[int, int, int]:
    """Devolve (estimativa_tokens, arquivos, bytes)."""
    arquivos, bytes_ = medir_workspace(raiz, alvos)
    return (int(BASE_TOKENS + (bytes_ / 4) * FATOR_RELEITURA + len(prompt) / 4),
            arquivos, bytes_)


def sinais_no_pedido(prompt: str) -> tuple:
    p = (prompt or "").lower()
    return tuple(s for s in SINAIS_INVESTIGACAO if re.search(s, p))


def pediu_pressa(prompt: str) -> bool:
    """O usuario disse que quer rapidez? So isso libera o fast no automatico."""
    p = (prompt or "").lower()
    return bool(re.search(r"\br[aá]pid|\bs[oó]\s+isso\b|\bpressa\b|\bem\s+segundos\b|"
                          r"\bum[a]?\s+linha\b|\btrivial\b|\bsimples\s+assim\b", p))


def decidir(raiz: Path, prompt: str = "", limiar: int = LIMIAR_PADRAO,
            forcar: str = "auto", alvos: list[str] | None = None,
            pressa: bool | None = None, limiar_curto: int = LIMIAR_CURTO) -> Decisao:
    """`forcar` em 'fast-coder'/'mast-agent' respeita a escolha manual (requisito 21).

    `pressa`: None = deduz do pedido; True/False = decisao de quem chama.
    """
    est, arquivos, bytes_ = estimar_contexto(raiz, prompt, alvos)
    sinais = sinais_no_pedido(prompt)
    if pressa is None:
        pressa = pediu_pressa(prompt)

    if forcar in ("fast-coder", "mast-agent"):
        # V3.1 deixou mast-agent como PADRAO, entao "forcado" nem sempre e escolha
        # manual — dizer que era enganava na tela (visto na primeira run real).
        motivo = ("padrao V3.1: mast-agent ganhou o A/B em sucesso e qualidade"
                  if forcar == "mast-agent" else "harness fixado em /harness")
        return Decisao(est, limiar, forcar, motivo, arquivos, bytes_, sinais, forcado=True)

    # ---- V3.1 (2026-08-17), depois do A/B -----------------------------------
    # O erro da V3.0 foi ler "ate 3K os dois empatam" como "ate 3K use o fast".
    # Nao e a mesma coisa: o empate era em TAXA DE SUCESSO; em QUALIDADE o mast
    # ganhou ate nas rapidas (4.50 x 4.20). Resultado do A/B com 30 execucoes:
    #     V2 fast 21/30 (3.80)   V2 mast 23/30 (4.17)   V3 auto 22/30 (3.97)
    # Entao o padrao passa a ser mast-agent, e o fast so entra com RAZAO CONCRETA.
    if est > limiar:
        return Decisao(est, limiar, "mast-agent",
                       f"contexto estimado {est} acima do limiar {limiar}",
                       arquivos, bytes_, sinais)
    if arquivos >= LIMIAR_ARQUIVOS:
        return Decisao(est, limiar, "mast-agent",
                       f"{arquivos} arquivos no escopo: tarefa espalhada, contexto tende a crescer",
                       arquivos, bytes_, sinais)
    if sinais:
        return Decisao(est, limiar, "mast-agent",
                       "pedido indica investigacao prolongada ou multiplas hipoteses",
                       arquivos, bytes_, sinais)
    if pressa and est <= limiar_curto and not sinais:
        return Decisao(est, limiar, "fast-coder",
                       f"latencia foi priorizada e a tarefa e curta ({est} tokens estimados)",
                       arquivos, bytes_, sinais)
    return Decisao(est, limiar, "mast-agent",
                   f"padrao V3.1: sem razao concreta para trocar, vale o mast "
                   f"(melhor em sucesso e qualidade no A/B)", arquivos, bytes_, sinais)
