# -*- coding: utf-8 -*-
"""Agent runtime: planejamento, roteamento e supervisao (requisitos 4, 5, 6, 47, 80, 81).

REAPROVEITA as ferramentas do harness-filho (requisito 98) — read/write/edit/bash
com escrita verificada, rollback por sintaxe, no-op como erro e read-before-edit.
Nao reescreve o que ja esta medido e funcionando.

O que este modulo acrescenta e a UX: eventos para a tela, permissoes, limite de
ferramentas por passo, e a separacao emitidas/executadas/bloqueadas.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from . import i18n
from .comandos import Resposta
from .config import humano
from .roteador import decidir

HARNESS_FILHO = Path("/home/julianshin/Documentos/automatização/harness-filho")
if str(HARNESS_FILHO) not in sys.path:
    sys.path.insert(0, str(HARNESS_FILHO))

try:                                     # reaproveitamento, com degradacao honesta
    from hbcore.ferramentas import FERRAMENTAS as FERR_HB, ESQUEMA as ESQUEMA_HB, Caixa
    HB_OK = True
except Exception:                        # noqa: BLE001
    FERR_HB, ESQUEMA_HB, Caixa, HB_OK = {}, [], None, False

FERRAMENTAS_INFO = {
    "read": {"descricao": "Le um arquivo e devolve com numero de linha.",
             "parametros": ["path"], "ativa": HB_OK, "permissao": "leitura"},
    "write": {"descricao": "Escreve o arquivo inteiro. A sintaxe e verificada e a escrita "
                           "e revertida se quebrar.",
              "parametros": ["path", "content"], "ativa": HB_OK, "permissao": "escrita"},
    "edit": {"descricao": "Substitui UM trecho exato por outro num arquivo ja lido.",
             "parametros": ["path", "old", "new"], "ativa": HB_OK, "permissao": "escrita"},
    "bash": {"descricao": "Roda um comando dentro do projeto.",
             "parametros": ["command", "timeout"], "ativa": HB_OK, "permissao": "shell"},
}

BENCHES = {
    "harness-bench": {"descricao": "5 tarefas, 9 modelos, 5 harnesses",
                      "comando": "cd /home/julianshin/Documentos/benchmarks/harness-bench && python3 run_harness.py --all"},
    "harness-contexto": {"descricao": "6 tarefas em 3 faixas de contexto",
                         "comando": "cd /home/julianshin/Documentos/benchmarks/harness-contexto && python3 run_ctx.py --all"},
}

_BACKUPS: dict[str, list] = {}       # session_id -> [(caminho, conteudo_antes)]


# ------------------------------------------------------------------ auxiliares
def detectar_testes(raiz: Path) -> str:
    raiz = Path(raiz)
    if (raiz / "pytest.ini").exists() or (raiz / "pyproject.toml").exists() or \
       list(raiz.glob("test_*.py")) or (raiz / "tests").exists() or (raiz / "testes").exists():
        return "python3 -m pytest -q"
    if (raiz / "package.json").exists():
        return "npm test"
    if (raiz / "Cargo.toml").exists():
        return "cargo test"
    if (raiz / "go.mod").exists():
        return "go test ./..."
    return ""


def rodar_comando(ctx, comando: str, timeout: int = 120) -> Resposta:
    perm = ctx.config.get("permissions.shell", "ask")
    if perm == "deny":
        return Resposta(["Execucao de shell esta negada. Veja /permissions."], erro=True)
    # BUG achado na auditoria (2026-08-17): rodava em ctx.projeto enquanto o agente
    # trabalha na sandbox — /tests testava a pasta errada e dava verde falso.
    onde = ctx.pasta_trabalho()
    t0 = time.time()
    try:
        r = subprocess.run(comando, shell=True, cwd=str(onde), capture_output=True,
                           text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return Resposta([f"O comando passou de {timeout}s e foi interrompido."], erro=True)
    except Exception as exc:                                     # noqa: BLE001
        return Resposta([f"Nao consegui executar.", f"  Motivo: {exc}"], erro=True)
    dur = time.time() - t0
    ctx.metricas.tempo_ferramentas += dur
    saida = ((r.stdout or "") + (("\n" + r.stderr) if r.stderr else "")).strip()
    linhas = saida.splitlines()[-40:] or ["(sem saida)"]
    rotulo = Path(onde).name
    if r.returncode != 0:
        return Resposta(linhas, titulo=f"exit {r.returncode} ({dur:.1f}s) · em {rotulo}", erro=True)
    return Resposta(linhas, titulo=f"ok ({dur:.1f}s) · em {rotulo}", ok=True)


def backups_da_sessao(ctx) -> list:
    return _BACKUPS.get(ctx.sessao.session_id, [])


def registrar_backup(ctx, caminho: Path, antes: str | None):
    _BACKUPS.setdefault(ctx.sessao.session_id, []).append((str(caminho), antes))


def desfazer_ultima(ctx) -> tuple[bool, str]:
    pilha = _BACKUPS.get(ctx.sessao.session_id) or []
    if not pilha:
        return False, "Nao ha alteracao do agente para desfazer."
    caminho, antes = pilha.pop()
    p = Path(caminho)
    try:
        if antes is None:
            if p.exists():
                p.unlink()
            return True, f"Desfeito: {p.name} foi removido (ele nao existia antes)."
        p.write_text(antes, encoding="utf-8")
        return True, f"Desfeito: {p.name} voltou ao conteudo anterior."
    except OSError as exc:
        return False, f"Nao consegui desfazer {p.name}: {exc}"


def desfazer_tudo(ctx) -> tuple[int, list]:
    n, erros = 0, []
    while _BACKUPS.get(ctx.sessao.session_id):
        ok, msg = desfazer_ultima(ctx)
        if ok:
            n += 1
        else:
            erros.append(msg)
    return n, erros


# ------------------------------------------------------------------- runtime
class Runtime:
    """Um passo de trabalho: planeja, roteia, executa sob supervisao."""

    def __init__(self, ctx, on_evento=None):
        self.ctx = ctx
        self.on_evento = on_evento or (lambda *a, **k: None)
        self.cx = Caixa(raiz=Path(ctx.pasta_trabalho())) if HB_OK else None

    # ------------------------------------------------------------- eventos
    def _ev(self, tipo, texto, detalhe=""):
        e = self.ctx.evento(tipo, texto, detalhe)
        self.on_evento(e)
        return e

    # --------------------------------------------------------- planejamento
    def planejar(self, pedido: str) -> dict:
        """Modo PLANEJAMENTO (requisito 4): entende, mede, escolhe o harness."""
        c = self.ctx
        c.fase = "plan"
        self._ev("acao", "Lendo estrutura do projeto")
        skills = c.skills.sugerir(pedido)
        if skills:
            self._ev("info", f"Skill carregada: {', '.join(skills)}")
            c.sessao.skills_carregadas = sorted(set(c.sessao.skills_carregadas) | set(skills))
        self._ev("acao", "Analisando arquivos relacionados")
        self._ev("acao", "Estimando contexto necessario")

        d = decidir(c.pasta_trabalho(), pedido,
                    limiar=int(c.config.get("router.threshold", 3000)),
                    forcar=c.harness_pedido())
        c.ultima_decisao_roteador = d.dic()
        c.sessao.plano = {"pedido": pedido, "skills": skills, **d.dic()}
        c.sessao.decidir(f"harness={d.selected_harness}: {d.router_reason}")
        c.log("info", f"roteador: {d.selected_harness} ({d.router_reason})")
        self._ev("ok", "Plano pronto",
                 f"Contexto estimado: {humano(d.context_estimate)}\n"
                 f"Harness selecionado: {d.selected_harness}")
        return c.sessao.plano

    # ------------------------------------------------------------ modos
    MUTANTES = {"write", "edit", "bash"}

    def _modo_permite(self, ferramenta: str, args: dict) -> tuple[bool, str]:
        """Os tres modos deixam de ser enfeite aqui.

        Bug achado na auditoria (2026-08-17): os botoes PLAN/FULL/PERM mudavam so
        o rotulo. O usuario escolhia "PEDIR PERMISSAO" e o agente escrevia direto.
        """
        c = self.ctx
        if ferramenta not in self.MUTANTES:
            return True, ""                      # ler e sempre permitido
        if c.so_leitura():
            return False, ("modo PLANEJAMENTO: so leitura. Aprove o plano "
                           "(responda sim) para eu implementar.")
        return True, ""

    def _permissao_do_usuario(self, ferramenta: str, args: dict) -> tuple[bool, str]:
        """Modo PEDIR PERMISSAO: pergunta de verdade e espera."""
        c = self.ctx
        if c.config.get("auto_approve"):
            return True, ""
        if not callable(c.pedir_permissao):
            return True, ""                      # sem UI para perguntar: nao trava
        alvo = args.get("path") or args.get("command") or ""
        try:
            aprovado = c.pedir_permissao(ferramenta, str(alvo)[:120])
        except Exception:                        # noqa: BLE001
            aprovado = False
        return bool(aprovado), ("" if aprovado else "negado por voce")

    # ------------------------------------------------------------ permissao
    def _pode(self, ferramenta: str) -> tuple[bool, str]:
        info = FERRAMENTAS_INFO.get(ferramenta, {})
        cat = info.get("permissao", "leitura")
        modo = self.ctx.config.get(f"permissions.{cat}", "ask")
        if modo == "allow" or self.ctx.config.get("auto_approve"):
            return True, ""
        if modo == "deny":
            return False, f"permissao '{cat}' esta em deny"
        return True, ""      # 'ask' vira pendencia na UI; no runtime seguimos

    # ------------------------------------------------------------- execucao
    def executar_ferramentas(self, chamadas: list) -> list:
        """Aplica limite por passo, permissoes e guardas. Devolve resultados.

        Separa emitidas / executadas / bloqueadas (requisitos 36, 37, 82).
        """
        c = self.ctx
        m = c.metricas
        m.tool_calls_emitted += len(chamadas)

        teto = int(c.config.get("tools.max_per_step", 4))
        if len(chamadas) > teto:
            m.bloquear(len(chamadas) - teto, "limite por passo")
            c.log("info", f"{len(chamadas)} ferramentas pedidas; executando {teto}")
            chamadas = chamadas[:teto]

        saidas = []
        for ch in chamadas:
            if c.parar:
                m.bloquear(1, "parado pelo usuario")
                continue
            nome = ch.get("nome") or ch.get("name")
            args = ch.get("args") or ch.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:                                # noqa: BLE001
                    args = {}
            pode, motivo = self._modo_permite(nome, args)
            if pode and self.ctx.modo_pedido_permissao() and nome in self.MUTANTES:
                pode, motivo = self._permissao_do_usuario(nome, args)
            if pode:
                pode, motivo = self._pode(nome)
            if not pode:
                m.bloquear(1, motivo)
                saidas.append({"nome": nome, "erro": True, "texto": f"bloqueado: {motivo}"})
                self._ev("erro", f"Bloqueado: {nome}", motivo)
                continue
            if nome not in FERR_HB:
                m.bloquear(1, "ferramenta inexistente")
                saidas.append({"nome": nome, "erro": True, "texto": f"ferramenta '{nome}' nao existe"})
                continue

            alvo = args.get("path") or args.get("command") or ""
            rotulo = {"read": "Lendo", "write": "Escrevendo", "edit": "Editando",
                      "bash": "Executando"}.get(nome, nome)
            ev = self._ev("acao", f"{rotulo} {str(alvo)[:60]}")

            if nome in ("write", "edit") and args.get("path"):
                p = Path(c.projeto) / args["path"]
                registrar_backup(c, p, p.read_text(encoding="utf-8", errors="replace")
                                 if p.exists() else None)

            t0 = time.time()
            extra = {}
            try:
                res = FERR_HB[nome](self.cx, **{**args, **extra})
            except TypeError as exc:
                res = type("R", (), {"texto": f"argumentos invalidos: {exc}", "erro": True,
                                     "mudou_arquivo": None, "executou_prova": False})()
            except Exception as exc:                             # noqa: BLE001
                res = type("R", (), {"texto": f"{type(exc).__name__}: {exc}", "erro": True,
                                     "mudou_arquivo": None, "executou_prova": False})()
            m.tempo_ferramentas += time.time() - t0
            m.tool_calls_executed += 1

            if res.erro:
                m.erro(nome)
                c.sessao.erros.append(f"{nome}: {res.texto[:120]}")
                ev["tipo"] = "erro"
            if "REVERTIDA" in (res.texto or ""):
                m.escritas_revertidas += 1
            if getattr(res, "mudou_arquivo", None):
                base = str(c.pasta_trabalho())
                rel = (str(Path(res.mudou_arquivo).relative_to(base))
                       if str(res.mudou_arquivo).startswith(base) else str(res.mudou_arquivo))
                c.sessao.tocar_arquivo(rel, "editado" if nome == "edit" else "criado")
            elif nome == "read" and args.get("path") and not res.erro:
                c.sessao.tocar_arquivo(args["path"], "lido")
            if getattr(res, "executou_prova", False):
                m.provas_executadas += 1

            ev["detalhe"] = (res.texto or "")[:2000]
            c.sessao.registrar_tool(nome, args, res.texto, res.erro)
            saidas.append({"nome": nome, "erro": res.erro, "texto": res.texto})
        return saidas

    # -------------------------------------------------- fim da tarefa (80,81)
    def pode_encerrar(self, houve_escrita: bool) -> tuple[bool, str]:
        """Nao aceita 'pronto' sem prova (80) nem encerramento vazio (81)."""
        m = self.ctx.metricas
        if not houve_escrita and not self.ctx.sessao.files:
            m.encerramentos_vazios_barrados += 1
            return False, ("Voce esta encerrando sem ter criado nem alterado nenhum arquivo. "
                           "Se a tarefa pede mudanca, faca agora; se nao pede, diga por que.")
        if houve_escrita and m.provas_executadas == 0:
            return False, ("Voce alterou arquivo e ainda nao provou que funciona. "
                           "Rode o teste, o import ou o programa antes de encerrar.")
        return True, ""

    # ------------------------------------------------------------ contexto
    def talvez_compactar(self, tokens_prompt: int) -> bool:
        janela = self.ctx.janela()
        if tokens_prompt < janela * 0.70:
            return False
        antes, depois = self.ctx.sessao.compactar()
        self.ctx.metricas.compaction_count = self.ctx.sessao.compaction_count
        self.ctx.metricas.context_before = antes // 4
        self.ctx.metricas.context_after = depois // 4
        self._ev("info", "Contexto compactado")
        return True

    def resumo_do_trabalho(self) -> str:
        """Fecha a tarefa contando o que foi feito — no idioma do usuario."""
        c = self.ctx
        idi = c.idioma
        criados = [k for k, v in c.sessao.files.items() if v == "criado"]
        editados = [k for k, v in c.sessao.files.items() if v == "editado"]
        partes = []
        if criados:
            partes.append(f"{i18n.t('resumo.criei', idi)} " + ", ".join(criados[:6]))
        if editados:
            partes.append(f"{i18n.t('resumo.editei', idi)} " + ", ".join(editados[:6]))
        if not partes:
            return i18n.t("resumo.nada", idi)
        frase = f"{i18n.t('msg.done', idi)}: " + "; ".join(partes) + "."
        n = c.metricas.provas_executadas
        frase += " " + (i18n.t("resumo.validei", idi).replace("{n}", str(n)) if n
                        else i18n.t("resumo.sem_prova", idi))
        return frase

    # ---------------------------------------------------------------- runs
    def abrir_run(self) -> dict:
        r = {"id": "run_" + uuid.uuid4().hex[:4], "inicio": time.time(),
             "modelo": self.ctx.modelo(), "provider": self.ctx.config.get("provider"),
             "harness": self.ctx.harness_efetivo(), "status": "rodando",
             "arquivos": [], "duracao": "—"}
        self.ctx.runs.append(r)
        self.ctx.sessao.runs.append(r["id"])
        return r

    def fechar_run(self, r: dict, status: str, testes: str = "—"):
        m = self.ctx.metricas
        seg = int(time.time() - r["inicio"])
        r.update({"status": status, "duracao": f"{seg // 60}m{seg % 60:02d}s",
                  "contexto_pico": m.contexto_pico, "testes": testes,
                  "arquivos": sorted(self.ctx.sessao.files),
                  "tool_calls_emitted": m.tool_calls_emitted,
                  "tool_calls_executed": m.tool_calls_executed,
                  "tool_calls_blocked": m.tool_calls_blocked})
        return r

    # ------------------------------------------------------------ transporte
    def _endpoint(self) -> str:
        pr = self.ctx.registro.provedores.get(self.ctx.config.get("provider"))
        base = (pr.base_url if pr else "http://127.0.0.1:8099").rstrip("/")
        return base + "/chat/completions" if base.endswith("/v1") else base + "/v1/chat/completions"

    def completar(self, mensagens: list) -> dict:
        """Chama o modelo. So manda parametro que o modelo declara suportar (84)."""
        c = self.ctx
        cap = c.cap()
        corpo = {"model": c.modelo(), "messages": mensagens,
                 "max_tokens": int(c.config.get("max_output", 4096))}
        if cap.supports_temperature:
            corpo["temperature"] = float(c.config.get("temperature", 0.2))
        if cap.supports_top_p:
            corpo["top_p"] = float(c.config.get("top_p", 0.95))
        if cap.supports_reasoning_effort:
            corpo["reasoning_effort"] = c.config.get("effort", "medium")
        if cap.supports_tools and HB_OK:
            corpo["tools"] = ESQUEMA_HB
            corpo["tool_choice"] = "auto"

        pr = c.registro.provedores.get(c.config.get("provider"))
        cab = {"Content-Type": "application/json"}
        if pr and pr.chave_env and os.environ.get(pr.chave_env):
            cab["Authorization"] = f"Bearer {os.environ[pr.chave_env]}"
        req = urllib.request.Request(self._endpoint(),
                                     data=json.dumps(corpo).encode("utf-8"), headers=cab)
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                d = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detalhe = ""
            try:
                detalhe = exc.read().decode("utf-8", "replace")[:200]
            except Exception:                                    # noqa: BLE001
                pass
            raise RuntimeError(f"o modelo respondeu HTTP {exc.code}. {detalhe}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"nao consegui falar com o modelo em {self._endpoint()} "
                               f"({exc.reason}). O servidor esta no ar?") from exc
        c.metricas.tempo_modelo += time.time() - t0
        uso = d.get("usage") or {}
        if uso.get("prompt_tokens"):
            c.metricas.marcar_contexto(int(uso["prompt_tokens"]))
        return d

    def montar_mensagens(self, pedido: str, historico: list) -> list:
        c = self.ctx
        skills = c.sessao.skills_carregadas
        sistema = [
            "Voce e o Gatinho, um agente de programacao trabalhando na pasta do projeto.",
            "Ferramentas: read, write, edit, bash. O ambiente aplica sozinho:",
            "- escrita com sintaxe quebrada e DESFEITA e voce recebe o erro;",
            "- edit troca UM trecho exato; se nao existir ou repetir, nada muda;",
            "- leia o arquivo antes de editar;",
            f"- no maximo {c.config.get('tools.max_per_step', 4)} ferramentas por resposta: "
            "aja um pouco, veja o resultado, continue.",
            "Nao termine dizendo 'pronto' sem prova: rode o teste, o import ou o programa.",
            i18n.instrucao_modelo(c.idioma),
            "Seja direto, sem plano longo.",
        ]
        if skills:
            corpo = c.skills.prompt_das(skills)
            if corpo:
                sistema += ["", corpo]
        msgs = [{"role": "system", "content": "\n".join(sistema)}]
        for m in historico[-24:]:
            papel = m.get("role")
            if papel in ("user", "assistant", "system", "tool"):
                msgs.append({k: v for k, v in m.items() if k in
                             ("role", "content", "tool_calls", "tool_call_id", "name")})
        msgs.append({"role": "user", "content": pedido})
        return msgs

    def conversar(self, pedido: str, max_turnos: int = 24) -> str:
        """Loop de trabalho no modo SUPERVISÃO. Devolve o texto final do agente."""
        c = self.ctx
        c.fase = "supervise"
        c.executando = True
        c.parar = False
        run = self.abrir_run()
        msgs = self.montar_mensagens(pedido, c.sessao.messages)
        houve_escrita = False
        cobrancas = 0
        final = ""
        try:
            for _ in range(max_turnos):
                if c.parar:
                    final = "Interrompido a seu pedido."
                    break
                while c.pausado and not c.parar:
                    time.sleep(0.3)
                c.metricas.turnos += 1
                try:
                    d = self.completar(msgs)
                except RuntimeError as exc:
                    self._ev("erro", "Falhei ao falar com o modelo", str(exc))
                    final = str(exc)
                    self.fechar_run(run, "falhou")
                    return final

                msg = ((d.get("choices") or [{}])[0].get("message")) or {}
                texto = msg.get("content") or ""
                chamadas_brutas = msg.get("tool_calls") or []
                chamadas = [{"nome": (x.get("function") or {}).get("name"),
                             "args": (x.get("function") or {}).get("arguments"),
                             "id": x.get("id", "")} for x in chamadas_brutas]

                if not chamadas:
                    pode, cobranca = self.pode_encerrar(houve_escrita)
                    if not pode and cobrancas < 2:
                        cobrancas += 1
                        self._ev("info", "Pedindo a prova antes de encerrar")
                        msgs.append({"role": "assistant", "content": texto or None})
                        msgs.append({"role": "user", "content": cobranca})
                        continue
                    # o modelo as vezes encerra sem texto. Em vez de mostrar
                    # "(nao disse nada)", conta o que REALMENTE foi feito — que e
                    # o que o usuario precisa saber (requisito 93).
                    final = texto.strip() or self.resumo_do_trabalho()
                    break

                msgs.append({"role": "assistant", "content": texto or None,
                             "tool_calls": chamadas_brutas[:int(c.config.get('tools.max_per_step', 4))]})
                saidas = self.executar_ferramentas(chamadas)
                for ch, s in zip(chamadas[:len(saidas)], saidas):
                    if not s["erro"] and ch["nome"] in ("write", "edit"):
                        houve_escrita = True
                    msgs.append({"role": "tool", "tool_call_id": ch.get("id", ""),
                                 "name": s["nome"], "content": (s["texto"] or "")[:6000]})
                self.talvez_compactar(c.metricas.contexto_atual)
            else:
                final = "Cheguei ao limite de passos desta tarefa."
        finally:
            c.executando = False
            status = "sucesso" if (houve_escrita and c.metricas.provas_executadas) else \
                     ("parcial" if houve_escrita else "sem alteracao")
            self.fechar_run(run, status)
        return final

    # ============================================================ streaming
    def completar_stream(self, mensagens: list):
        """Fala com o modelo em streaming de verdade (SSE do llama-server).

        Emite ("texto", pedaco) enquanto o modelo escreve, acumula as tool_calls
        e no fim emite ("fim", {"texto":..., "tool_calls":[...]}).
        """
        c = self.ctx
        cap = c.cap()
        # stream_options: sem isto o llama-server nao manda `usage` no streaming
        # e a barra de contexto fica em 0.0K (visto na primeira execucao real).
        corpo = {"model": c.modelo(), "messages": mensagens, "stream": True,
                 "stream_options": {"include_usage": True},
                 "max_tokens": int(c.config.get("max_output", 4096))}
        if cap.supports_temperature:
            corpo["temperature"] = float(c.config.get("temperature", 0.2))
        if cap.supports_top_p:
            corpo["top_p"] = float(c.config.get("top_p", 0.95))
        if cap.supports_reasoning_effort:
            corpo["reasoning_effort"] = c.config.get("effort", "medium")
        if cap.supports_tools and HB_OK:
            corpo["tools"] = ESQUEMA_HB
            corpo["tool_choice"] = "auto"

        pr = c.registro.provedores.get(c.config.get("provider"))
        cab = {"Content-Type": "application/json"}
        if pr and pr.chave_env and os.environ.get(pr.chave_env):
            cab["Authorization"] = f"Bearer {os.environ[pr.chave_env]}"
        req = urllib.request.Request(self._endpoint(),
                                     data=json.dumps(corpo).encode("utf-8"), headers=cab)
        t0 = time.time()
        texto, chamadas = "", {}
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                for linha in r:
                    linha = linha.decode("utf-8", "replace").strip()
                    if not linha.startswith("data:"):
                        continue
                    dados = linha[5:].strip()
                    if dados == "[DONE]":
                        break
                    try:
                        d = json.loads(dados)
                    except Exception:                             # noqa: BLE001
                        continue
                    uso = d.get("usage") or {}
                    if uso.get("prompt_tokens"):
                        c.metricas.marcar_contexto(int(uso["prompt_tokens"]))
                    delta = ((d.get("choices") or [{}])[0].get("delta")) or {}
                    if delta.get("content"):
                        texto += delta["content"]
                        yield ("texto", delta["content"])
                    for tc in delta.get("tool_calls") or []:
                        i = tc.get("index", 0)
                        alvo = chamadas.setdefault(i, {"id": "", "nome": "", "args": ""})
                        if tc.get("id"):
                            alvo["id"] = tc["id"]
                        fn = tc.get("function") or {}
                        if fn.get("name"):
                            alvo["nome"] = fn["name"]
                        if fn.get("arguments"):
                            alvo["args"] += fn["arguments"]
        except urllib.error.HTTPError as exc:
            corpo_erro = ""
            try:
                corpo_erro = exc.read().decode("utf-8", "replace")[:200]
            except Exception:                                     # noqa: BLE001
                pass
            raise RuntimeError(f"o modelo respondeu HTTP {exc.code}. {corpo_erro}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"nao consegui falar com o modelo em {self._endpoint()} "
                               f"({exc.reason}). O servidor esta no ar?") from exc
        c.metricas.tempo_modelo += time.time() - t0
        yield ("fim", {"texto": texto,
                       "tool_calls": [chamadas[k] for k in sorted(chamadas)]})

    def conversar_eventos(self, pedido: str, max_turnos: int = 24):
        """Mesma logica de `conversar`, mas como GERADOR de eventos para a web.

        Eventos: plano · texto · acao · resultado · aviso · fim · erro
        """
        c = self.ctx
        c.fase = "plan"
        yield {"tipo": "fase", "fase": "plan"}

        d = decidir(c.pasta_trabalho(), pedido,
                    limiar=int(c.config.get("router.threshold", 3000)),
                    forcar=c.harness_pedido())
        c.ultima_decisao_roteador = d.dic()
        c.sessao.plano = {"pedido": pedido, **d.dic()}
        skills = c.skills.sugerir(pedido)
        if skills:
            c.sessao.skills_carregadas = sorted(set(c.sessao.skills_carregadas) | set(skills))
            yield {"tipo": "acao", "classe": "t-read", "tag": "Skill",
                   "texto": ", ".join(skills)}
        yield {"tipo": "plano", "estimativa": d.context_estimate,
               "harness": d.selected_harness, "motivo": d.router_reason}

        c.fase = "supervise"
        c.executando = True
        c.parar = False
        yield {"tipo": "fase", "fase": "supervise"}
        run = self.abrir_run()
        msgs = self.montar_mensagens(pedido, c.sessao.messages)
        houve_escrita = False
        cobrancas = 0
        try:
            for _ in range(max_turnos):
                if c.parar:
                    yield {"tipo": "aviso", "texto": "interrompido"}
                    break
                c.metricas.turnos += 1
                texto, chamadas_brutas = "", []
                try:
                    for tipo, payload in self.completar_stream(msgs):
                        if tipo == "texto":
                            yield {"tipo": "texto", "texto": payload}
                        else:
                            texto = payload["texto"]
                            chamadas_brutas = payload["tool_calls"]
                except RuntimeError as exc:
                    yield {"tipo": "erro", "texto": str(exc)}
                    self.fechar_run(run, "falhou")
                    return

                if not chamadas_brutas:
                    pode, cobranca = self.pode_encerrar(houve_escrita)
                    if not pode and cobrancas < 2:
                        cobrancas += 1
                        yield {"tipo": "aviso", "texto": "pedindo a prova antes de encerrar"}
                        msgs.append({"role": "assistant", "content": texto or None})
                        msgs.append({"role": "user", "content": cobranca})
                        continue
                    yield {"tipo": "fim", "texto": texto.strip() or self.resumo_do_trabalho(),
                           "metricas": self.metricas_web()}
                    break

                msgs.append({"role": "assistant", "content": texto or None,
                             "tool_calls": [{"id": x["id"], "type": "function",
                                             "function": {"name": x["nome"], "arguments": x["args"]}}
                                            for x in chamadas_brutas]})
                chamadas = [{"nome": x["nome"], "args": x["args"], "id": x["id"]}
                            for x in chamadas_brutas]
                for ch in chamadas[:int(c.config.get("tools.max_per_step", 4))]:
                    args_txt = ch["args"]
                    try:
                        alvo = (json.loads(args_txt or "{}").get("path")
                                or json.loads(args_txt or "{}").get("command") or "")
                    except Exception:                             # noqa: BLE001
                        alvo = ""
                    rotulo = {"read": ("t-read", "Read"), "write": ("t-write", "Wrote"),
                              "edit": ("t-edit", "Edited"), "bash": ("t-run", "Ran")}.get(
                                  ch["nome"], ("t-read", ch["nome"]))
                    yield {"tipo": "acao", "classe": rotulo[0], "tag": rotulo[1],
                           "texto": str(alvo)[:90]}
                saidas = self.executar_ferramentas(chamadas)
                for ch, s in zip(chamadas[:len(saidas)], saidas):
                    if not s["erro"] and ch["nome"] in ("write", "edit"):
                        houve_escrita = True
                    yield {"tipo": "resultado", "erro": s["erro"],
                           "texto": (s["texto"] or "")[:1200], "ferramenta": s["nome"]}
                    msgs.append({"role": "tool", "tool_call_id": ch.get("id", ""),
                                 "name": s["nome"], "content": (s["texto"] or "")[:6000]})
                self.talvez_compactar(c.metricas.contexto_atual)
                yield {"tipo": "metricas", **self.metricas_web()}
            else:
                yield {"tipo": "fim", "texto": "Cheguei ao limite de passos desta tarefa.",
                       "metricas": self.metricas_web()}
        finally:
            c.executando = False
            status = "sucesso" if (houve_escrita and c.metricas.provas_executadas) else \
                     ("parcial" if houve_escrita else "sem alteracao")
            self.fechar_run(run, status)

    def metricas_web(self) -> dict:
        m = self.ctx.metricas
        return {"tokens": m.contexto_atual, "janela": self.ctx.janela(),
                "emitidas": m.tool_calls_emitted, "executadas": m.tool_calls_executed,
                "bloqueadas": m.tool_calls_blocked, "turnos": m.turnos,
                "tempo": round(m.tempo_total, 1), "compactacoes": m.compaction_count}
