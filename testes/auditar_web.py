#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Auditoria de ponta a ponta: TODOS os /comandos pelo HTTP, como a web faz.

Por que existe (pergunta do Pai, 2026-08-18: "checar se todos os barra funcionam"):
a auditoria antiga chamava `cmd.handler(ctx, args)` direto. Isso pula a resolucao de
nome, a leitura do JSON, os apelidos e a serializacao da resposta — ou seja, pula
exatamente o caminho que o navegador percorre. Um comando podia estar verde ali e
devolver "comando desconhecido" na tela.

Aqui e pela porta: sobe o servidor, le GET /api/comandos e dispara cada um em
POST /api/comando. Tambem confere o contrario — que a paleta desenhada no
web/index.html nao ofereca comando que o motor nao tem.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

tmp = Path(tempfile.mkdtemp(prefix="gatinho-web-audit-"))
os.environ["GATINHO_CONFIG_HOME"] = str(tmp / "cfg")
os.environ["GATINHO_DATA_HOME"] = str(tmp / "dados")
os.environ["GATINHO_WORKS"] = str(tmp / "works")
os.environ["GATINHO_MOTOR"] = "off"        # nao mexer em llama-server desta maquina

from gatinho import handlers, sandbox, servidor  # noqa: E402,F401
from gatinho.estado import Contexto  # noqa: E402
from gatinho.skills import Skills  # noqa: E402

sandbox.WORKS = tmp / "works"
PROJ = tmp / "projeto"; PROJ.mkdir(parents=True)
(PROJ / "exemplo.py").write_text("def f():\n    return 1\n", encoding="utf-8")

PORTA = int(os.environ.get("PORTA_AUDITORIA", "8798"))
BASE = f"http://127.0.0.1:{PORTA}"

ARGS = {
    "/model": "deltacoder-9b", "/provider": "local", "/context": "8k",
    "/effort": "medium", "/temperature": "0.3", "/top-p": "0.9",
    "/max-output": "2048", "/mode": "plan", "/harness": "auto",
    "/router": "threshold 3000", "/rename": "auditoria", "/session": "info",
    "/export": "markdown", "/skills": "list", "/skill": "pytest", "/tool": "read",
    "/tools-per-step": "4", "/permissions": "shell ask", "/verbose": "normal",
    "/benchmark": "list", "/run": "echo auditoria", "/sandbox": "info",
    "/idioma": "pt",
}
# mudam o mundo de um jeito que atrapalha a propria varredura
PULAR = {"/exit", "/new", "/clear", "/delete-session", "/reset", "/rollback", "/quit",
         "/q", "/cls", "/limpar", "/sair", "/novo"}


def http(caminho, corpo=None, timeout=25):
    dados = json.dumps(corpo).encode() if corpo is not None else None
    req = urllib.request.Request(BASE + caminho, data=dados,
                                 headers={"Content-Type": "application/json"} if dados else {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


ctx = Contexto(projeto=PROJ, skills=Skills(fontes=[]))
ctx.garantir_work()
srv = servidor.servir(ctx, porta=PORTA)
threading.Thread(target=srv.serve_forever, daemon=True).start()

falhas, vazios, ok = [], [], 0
try:
    print(f"servidor de auditoria em {BASE}\n")

    print("=== 1) o registro que a web recebe")
    st, reg = http("/api/comandos")
    cmds = reg["comandos"]
    print(f"    GET /api/comandos -> {st} · {reg['total']} comandos · {len(reg['aliases'])} apelidos")

    print("\n=== 2) disparando cada comando pelo HTTP")
    for c in cmds:
        nome = c["nome"]
        if nome in PULAR:
            continue
        texto = nome + (" " + ARGS[nome] if nome in ARGS else "")
        try:
            st, d = http("/api/comando", {"texto": texto})
        except Exception as exc:  # noqa: BLE001
            falhas.append((texto, f"{type(exc).__name__}: {exc}")); continue
        if st != 200:
            falhas.append((texto, f"HTTP {st}")); continue
        txt = " ".join(d.get("linhas") or [])
        if "comando desconhecido" in txt.lower() or "nao reconheci" in txt.lower():
            falhas.append((texto, f"o motor nao reconheceu: {txt[:60]}")); continue
        if not (d.get("linhas") or d.get("escolhas") or d.get("acao") or d.get("titulo")):
            vazios.append(texto); continue
        ok += 1
    print(f"    {ok} responderam · {len(falhas)} quebraram · {len(vazios)} vazios")

    print("\n=== 3) os apelidos resolvem pelo HTTP?")
    ruins_alias = []
    for alias, destino in list(reg["aliases"].items()):
        if alias in PULAR or destino in PULAR:
            continue
        arg = ARGS.get(destino, "")
        try:
            st, d = http("/api/comando", {"texto": alias + (" " + arg if arg else "")})
            txt = " ".join(d.get("linhas") or [])
            if st != 200 or "comando desconhecido" in txt.lower():
                ruins_alias.append(f"{alias} -> {destino}")
        except Exception as exc:  # noqa: BLE001
            ruins_alias.append(f"{alias}: {exc}")
    print(f"    {len(reg['aliases']) - len(ruins_alias)} apelidos ok · {len(ruins_alias)} quebrados")
    for a in ruins_alias:
        print(f"      XX {a}")

    print("\n=== 4) a paleta da web promete algum comando que nao existe?")
    html = (RAIZ / "web" / "index.html").read_text(encoding="utf-8", errors="replace")
    trecho = html[html.find("let CMDS="):html.find("let ALIASES=")]
    oferecidos = set(re.findall(r'\["(/[a-z0-9-]+)', trecho))
    reais = {c["nome"] for c in cmds} | set(reg["aliases"])
    fantasmas = sorted(oferecidos - reais)
    print(f"    a lista de reserva (modo DEMO) oferece {len(oferecidos)}: {' '.join(sorted(oferecidos))}")
    if fantasmas:
        print(f"    XX prometidos e inexistentes: {' '.join(fantasmas)}")
    else:
        print("    OK todos existem no motor")

    print("\n=== 5) trocar de modelo esta ao alcance da web?")
    st, d = http("/api/comando", {"texto": "/model"})
    tem_menu = bool(d.get("escolhas"))
    print(f"    /model devolve menu com {len(d.get('escolhas') or [])} modelos: "
          f"{'OK' if tem_menu else 'XX NAO'}")
    if not tem_menu:
        falhas.append(("/model", "nao devolveu menu de modelos"))

    print("\n=== o que quebrou")
    for t_, e in falhas:
        print(f"    XX {t_}: {e}")
    for t_ in vazios:
        print(f"    (vazio) {t_}")
    if not falhas and not vazios:
        print("    nada")

    ruins = len(falhas) + len(ruins_alias) + len(fantasmas) + (0 if tem_menu else 1)
    print(f"\n=== RESUMO: {ok}/{len(cmds) - len(PULAR & {c['nome'] for c in cmds})} comandos ok pelo HTTP · "
          f"{len(falhas)} quebrados · {len(ruins_alias)} apelidos ruins · {len(fantasmas)} fantasmas")
finally:
    srv.shutdown()
sys.exit(1 if ruins else 0)
