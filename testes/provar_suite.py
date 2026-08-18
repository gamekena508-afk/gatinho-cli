#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Teste do teste: quebra o codigo de proposito e cobra que a suite acuse.

Licao da v3 (ESPECIFICACAO-V3.md): teste que passa nao prova nada se ele nao
sabe reprovar. Cada mutacao abaixo desliga UMA garantia; se a suite continuar
verde, aquele teste e decorativo.

Nada e deixado quebrado: o arquivo original volta sempre (try/finally).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PY = "/home/julianshin/Documentos/benchmarks/harness-bench/tools/venv/bin/python"

MUTACOES = [
    ("limite de ferramentas por passo", "gatinho/runtime.py",
     "        if len(chamadas) > teto:",
     "        if False:",
     "test_tools_por_step_limita_e_contabiliza"),

    ("capabilities barram parametro", "gatinho/handlers.py",
     '    ok, msg = checar_parametro(cap, "reasoning_effort")\n    if not ok:\n        return Resposta([msg], erro=True)',
     '    ok, msg = checar_parametro(cap, "reasoning_effort")\n    if False:\n        return Resposta([msg], erro=True)',
     "test_capabilities_barram_parametro_incompativel"),

    ("compactacao preserva o objetivo", "gatinho/sessao.py",
     'f"objetivo: {self.objetivo or \'(nao registrado)\'}\\n"',
     '""',
     "test_compactacao_preserva_o_essencial"),

    ("encerramento vazio e barrado", "gatinho/runtime.py",
     "        if not houve_escrita and not self.ctx.sessao.files:",
     "        if False:",
     "test_encerramento_vazio_e_barrado"),

    ("contexto respeita o maximo do modelo", "gatinho/handlers.py",
     "    if v > cap.max_context:\n        return Resposta([f\"{humano(v)} passa do maximo do modelo",
     "    if False:\n        return Resposta([f\"{humano(v)} passa do maximo do modelo",
     "test_context_respeita_o_maximo_do_modelo"),

    ("hierarquia de config", "gatinho/config.py",
     "        v = _funde(v, self.camada_projeto)",
     "        v = v",
     "test_config_hierarquia_o_mais_especifico_vence"),
]


def roda_teste(nome: str) -> bool:
    """True se PASSOU."""
    r = subprocess.run([PY, "-m", "pytest", f"testes/test_gatinho.py::{nome}", "-q"],
                       cwd=str(RAIZ), capture_output=True, text=True)
    return r.returncode == 0


def main() -> int:
    print("verificando que a suite passa antes de qualquer mutacao...")
    base = subprocess.run([PY, "-m", "pytest", "testes/", "-q"], cwd=str(RAIZ),
                          capture_output=True, text=True)
    if base.returncode != 0:
        print("a suite ja esta vermelha; conserte antes de mutar.")
        print(base.stdout[-800:])
        return 1

    decorativos = []
    for descricao, arquivo, de, para, teste in MUTACOES:
        p = RAIZ / arquivo
        original = p.read_text(encoding="utf-8")
        if de not in original:
            print(f"  ?? {descricao}: trecho nao encontrado em {arquivo} — mutacao invalida")
            decorativos.append(descricao + " (mutacao invalida)")
            continue
        try:
            p.write_text(original.replace(de, para, 1), encoding="utf-8")
            passou = roda_teste(teste)
        finally:
            p.write_text(original, encoding="utf-8")
        if passou:
            print(f"  XX {descricao}: quebrei o codigo e {teste} continuou VERDE")
            decorativos.append(descricao)
        else:
            print(f"  OK {descricao}: {teste} acusou a quebra")

    print()
    depois = subprocess.run([PY, "-m", "pytest", "testes/", "-q"], cwd=str(RAIZ),
                            capture_output=True, text=True)
    if depois.returncode != 0:
        print("ATENCAO: a suite ficou vermelha depois das mutacoes — restauracao falhou.")
        return 1
    print("codigo restaurado; suite verde de novo.")

    if decorativos:
        print(f"\nSUITE REPROVADA: {len(decorativos)} garantia(s) sem teste que as defenda:")
        for d in decorativos:
            print("   -", d)
        return 1
    print(f"\nSUITE OK: as {len(MUTACOES)} mutacoes foram todas detectadas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
