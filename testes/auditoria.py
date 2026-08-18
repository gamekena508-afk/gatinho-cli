#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Auditoria: executa TODOS os comandos e cobra coerencia do projeto.

Nao e teste unitario — e varredura. Roda cada comando com argumento plausivel,
pega excecao, e depois checa invariantes que teste isolado nao pega (ex.: comando
que mexe em arquivo tem que usar a pasta de trabalho, nao o projeto do usuario).
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
import traceback
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

tmp = Path(tempfile.mkdtemp(prefix="gatinho-audit-"))
os.environ["GATINHO_CONFIG_HOME"] = str(tmp / "cfg")
os.environ["GATINHO_DATA_HOME"] = str(tmp / "dados")
os.environ["GATINHO_WORKS"] = str(tmp / "works")

from gatinho import handlers, sandbox  # noqa: E402
from gatinho.comandos import REGISTRO, resolver, sugestoes  # noqa: E402
from gatinho.estado import Contexto  # noqa: E402
from gatinho.skills import Skills  # noqa: E402

sandbox.WORKS = tmp / "works"

PROJ = tmp / "projeto"
PROJ.mkdir(parents=True)
(PROJ / "exemplo.py").write_text("def f():\n    return 1\n", encoding="utf-8")
(PROJ / "test_exemplo.py").write_text("import exemplo\n\n\ndef test_f():\n    assert exemplo.f() == 1\n",
                                      encoding="utf-8")

# comando -> argumentos com que ele deve funcionar
ARGS = {
    "model": ["deltacoder-9b"], "models": [], "provider": ["local"],
    "context": ["8k"], "effort": ["medium"], "temperature": ["0.3"],
    "top-p": ["0.9"], "max-output": ["2048"], "mode": ["plan"],
    "harness": ["auto"], "router": ["threshold", "3000"],
    "rename": ["auditoria"], "resume": [], "session": ["info"],
    "export": ["markdown"], "skills": ["list"], "skill": ["pytest"],
    "tool": ["read"], "tools-per-step": ["4"], "permissions": ["shell", "ask"],
    "verbose": ["normal"], "config": [], "benchmark": ["list"],
    "run": ["echo", "auditoria"], "sandbox": ["info"], "works": [],
    "idioma": ["pt"], "help": [], "inspect": [], "undo": [], "rollback": [],
    "delete-session": [], "reset": [], "new": [], "clear": [], "exit": [],
}
# comandos que mudam o mundo de forma que atrapalha a propria auditoria
PULAR = {"exit", "new", "clear", "delete-session", "reset", "rollback"}

falhas, avisos, ok = [], [], 0


def rodar(nome, args):
    global ok
    cmd = REGISTRO[nome]
    try:
        r = cmd.handler(ctx, args)
    except Exception as exc:  # noqa: BLE001
        falhas.append((nome, f"{type(exc).__name__}: {exc}",
                       traceback.format_exc().splitlines()[-3:]))
        return None
    if r is None:
        falhas.append((nome, "handler devolveu None", []))
        return None
    if not (r.linhas or r.escolhas or r.acao):
        avisos.append((nome, "resposta vazia: nem linha, nem escolha, nem acao"))
    ok += 1
    return r


print(f"projeto de teste: {PROJ}")
ctx = Contexto(projeto=PROJ, skills=Skills(fontes=[]))
ctx.sessao.mensagem("user", "auditoria do gatinho")

print(f"\n=== 1) executando os {len(REGISTRO)} comandos")
for nome in sorted(REGISTRO):
    if nome in PULAR:
        continue
    rodar(nome, ARGS.get(nome, []))
print(f"    {ok} responderam · {len(falhas)} quebraram · {len(avisos)} com resposta vazia")

print("\n=== 2) invariantes que teste isolado nao pega")
inv = []


def checa(desc, condicao, detalhe=""):
    inv.append((desc, bool(condicao), detalhe))


# a) a pasta de trabalho e a sandbox, nao o projeto
ctx.garantir_work()
checa("pasta de trabalho e a sandbox", ctx.pasta_trabalho() != ctx.projeto,
      str(ctx.pasta_trabalho()))

# b) /run e /tests rodam ONDE o agente trabalha (senao testam o projeto errado)
import inspect  # noqa: E402
from gatinho import runtime  # noqa: E402
src_run = inspect.getsource(runtime.rodar_comando)
checa("/run usa a pasta de trabalho", "pasta_trabalho" in src_run,
      "usa ctx.projeto — roda no lugar errado quando a sandbox esta ligada")

# c) /files, /diff, /git devem olhar a pasta de trabalho
for nome in ("diff", "git"):
    src = inspect.getsource(REGISTRO[nome].handler)
    checa(f"/{nome} usa a pasta de trabalho", "pasta_trabalho" in src,
          "olha ctx.projeto")

# d) todo comando tem contrato completo
faltando = [c.name for c in REGISTRO.values()
            if not (c.name and c.description and c.usage and c.category and callable(c.handler))]
checa("todo comando tem contrato completo", not faltando, ", ".join(faltando))

# e) autocomplete responde para todos
sem_auto = [n for n in REGISTRO if not sugestoes("/" + n[:3])]
checa("autocomplete acha todos os comandos", not sem_auto, ", ".join(sem_auto[:5]))

# f) alias nao aponta para comando inexistente
from gatinho.comandos import ALIASES  # noqa: E402
orfaos = [a for a, d in ALIASES.items() if d not in REGISTRO]
checa("nenhum alias orfao", not orfaos, ", ".join(orfaos))

# g) i18n: toda string existe nos 4 idiomas
from gatinho.i18n import T, IDIOMAS  # noqa: E402
buracos = [f"{k}/{i}" for k, v in T.items() for i in IDIOMAS if not v.get(i)]
checa("i18n completo nos 4 idiomas", not buracos, ", ".join(buracos[:5]))

# g2) o venv tem que ser de verdade, nao uma casca
# Defeito medido em 2026-08-17: `venv/` existia, `import rich` funcionava, e mesmo
# assim as 3 dependencias vinham do pyenv global. O venv usa --system-site-packages
# (de proposito, para reaproveitar torch), entao a existencia da pasta e o import
# limpo NAO provam nada. O que prova e de onde o modulo resolve.
import subprocess  # noqa: E402
VENV_PY = RAIZ / "venv" / "bin" / "python"
if not VENV_PY.exists():
    checa("as dependencias vem do venv, nao do sistema", False, f"nao existe {VENV_PY}")
else:
    sonda = ("import importlib\n"
             "for m in ('prompt_toolkit','rich','pytest'):\n"
             "    print(m, importlib.import_module(m).__file__)\n")
    r = subprocess.run([str(VENV_PY), "-c", sonda], capture_output=True, text=True)
    alvo = str(RAIZ / "venv") + "/"
    fora = [ln for ln in r.stdout.splitlines() if ln and alvo not in ln]
    if r.returncode:
        fora = [r.stderr.strip().splitlines()[-1]] if r.stderr.strip() else ["sonda falhou"]
    checa("as dependencias vem do venv, nao do sistema", not fora,
          "; ".join(x.replace(str(RAIZ), ".") for x in fora))

# g3) requirements.txt tem que citar o que o codigo importa de verdade
req = (RAIZ / "requirements.txt").read_text(encoding="utf-8")
declarados = {l.split("==")[0].split(">=")[0].strip().lower()
              for l in req.splitlines() if l.strip() and not l.startswith("#")}
checa("requirements cobre as dependencias reais",
      {"prompt_toolkit", "rich", "pytest"} <= declarados,
      f"declarados: {sorted(declarados)}")

# g4) o README de modelos nao pode vazar o topo do catalogo do Pai
# Ordem do Pai (2026-08-18): o repositorio vai para o git, mas a avaliacao dele nao
# e entregue de graca. Teto de citacao = SSR; nada de SSSR nem UR, e no maximo tres
# modelos. A lista do que NAO pode ser citado e lida da pasta de benchmarks dele e
# nunca e escrita aqui — um guarda que carrega os nomes secretos vaza os nomes
# secretos. Sem a pasta (ex.: repositorio clonado por outra pessoa), o teste pula.
readme_mod = RAIZ / "servidor" / "modelos" / "README.md"
cartas = Path("/home/julianshin/Documentos/benchmarks/codigo-uso-real/cartas/CARTAS.md")
if readme_mod.exists():
    txt_mod = readme_mod.read_text(encoding="utf-8").lower()
    citados = len(re.findall(r"^\| \*\*", txt_mod, re.M))
    checa("README de modelos cita no maximo 3", citados <= 3, f"cita {citados}")
    if cartas.exists():
        proibidos = []
        for linha in cartas.read_text(encoding="utf-8").splitlines():
            campos = [c.strip() for c in linha.split("|")]
            if len(campos) > 3 and campos[3] in ("UR", "SSSR"):
                proibidos.append(campos[1])
        vazou = [m for m in proibidos if m and m.lower() in txt_mod]
        checa("README de modelos nao cita acima do teto SSR", not vazou,
              f"{len(vazou)} acima do teto citados")
    else:
        avisos.append(("catalogo", "CARTAS.md ausente — nao dava para checar o teto"))

# g5) nenhuma DOCUMENTACAO pode citar modelo acima do teto
# Codigo e configuracao guardam id de modelo por necessidade (o padrao tem que se
# chamar alguma coisa). Documentacao e outra historia: ali o nome vira recomendacao
# publicada, e recomendacao publicada e o benchmark do Pai saindo de graca.
if cartas.exists():
    proibidos = []
    for linha in cartas.read_text(encoding="utf-8").splitlines():
        campos = [c.strip() for c in linha.split("|")]
        if len(campos) > 3 and campos[3] in ("UR", "SSSR"):
            proibidos.append(campos[1])
    docs = [x for x in RAIZ.rglob("*.md")
            if "venv" not in x.parts and "works" not in x.parts
            and ".contract-backup" not in x.parts]
    vazando = []
    for d in docs:
        low = d.read_text(encoding="utf-8", errors="replace").lower()
        for m in proibidos:
            if m and m.lower() in low:
                vazando.append(f"{d.relative_to(RAIZ)}:{m}")
    checa("nenhum .md cita modelo acima do teto", not vazando, "; ".join(vazando[:4]))

# h) a web nao pode ter link externo
html = (RAIZ / "web" / "index.html")
if html.exists():
    txt = html.read_text(encoding="utf-8", errors="replace")
    checa("web sem link externo", 'src="http' not in txt and "@import" not in txt)
    checa("web sem url do chatgpt", "chatgpt.com" not in txt)
else:
    checa("web/index.html existe", False, "rode web/gerar.py")

for desc, passou, detalhe in inv:
    print(f"    {'OK' if passou else 'XX'} {desc}" + (f"  → {detalhe}" if not passou and detalhe else ""))

print("\n=== 3) o que quebrou")
if not falhas:
    print("    nenhum comando levantou excecao")
for nome, erro, tb in falhas:
    print(f"    /{nome}: {erro}")
    for l in tb:
        print(f"        {l.strip()}")
for nome, msg in avisos:
    print(f"    (aviso) /{nome}: {msg}")

ruins = len(falhas) + sum(1 for _, p, _ in inv if not p)
print(f"\n=== RESUMO: {ok} comandos ok · {len(falhas)} quebrados · "
      f"{sum(1 for _, p, _ in inv if not p)} invariantes violados")
sys.exit(1 if ruins else 0)
