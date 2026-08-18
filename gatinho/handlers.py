# -*- coding: utf-8 -*-
"""Handlers de todos os comandos `/`. Puros: devolvem Resposta, nao imprimem."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from . import sessao as ses
from .capacidades import checar_parametro
from .comandos import ALIASES, REGISTRO, Resposta, comando, por_categoria
from .config import humano, tamanho_contexto
from .estado import MODOS, VERBOSIDADES, Pendencia
from .roteador import decidir

VERSAO = "3.0.0"


def _num(args, padrao=None):
    try:
        return float(args[0])
    except (IndexError, ValueError):
        return padrao


# ====================================================================== ajuda
@comando("help", "ajuda", aliases=("h", "?"), category="sistema")
def h_help(ctx, args):
    if args:
        c = REGISTRO.get(args[0].lstrip("/"))
        if not c:
            return Resposta([f"Comando /{args[0]} nao existe."], erro=True)
        linhas = [f"/{c.name} — {c.description}", f"uso: {c.usage}"]
        if c.aliases:
            linhas.append("apelidos: " + ", ".join("/" + a for a in c.aliases))
        if c.autocomplete:
            linhas.append("subcomandos: " + ", ".join(c.autocomplete))
        return Resposta(linhas, titulo=f"/{c.name}")
    principais = ["model", "context", "mode", "session", "skills", "tools",
                  "config", "status", "runs", "inspect", "clear", "help", "exit"]
    linhas = [f"/{n:<11}  {REGISTRO[n].description}" for n in principais if n in REGISTRO]
    linhas += ["", "/help <comando> mostra o detalhe de um só.",
               f"São {len(REGISTRO)} comandos no total — digite / para completar."]
    return Resposta(linhas, titulo="Gatinho — comandos")


@comando("about", "sobre o Gatinho", category="sistema")
def h_about(ctx, args):
    return Resposta([f"Gatinho CLI", f"Versao {VERSAO}", "Harness V3",
                     f"projeto: {ctx.projeto}"], titulo="Sobre")


@comando("version", "versao", aliases=("v",), category="sistema")
def h_version(ctx, args):
    return Resposta([VERSAO])


@comando("exit", "sair preservando a sessao", aliases=("quit", "q"), category="sistema")
def h_exit(ctx, args):
    ctx.sessao.salvar()
    return Resposta(["Sessao salva. Ate mais."], acao="sair", ok=True)


@comando("clear", "limpar a tela (nao apaga a sessao)", aliases=("cls",), category="sistema")
def h_clear(ctx, args):
    return Resposta(acao="limpar", ok=True)


# ===================================================================== modelo
def _reverter(ctx, anterior):
    """Devolve a config ao modelo que o motor esta servindo de fato."""
    mid, smodel, sprov = anterior
    if mid:
        ctx.config.set("model", mid)
    ctx.sessao.model, ctx.sessao.provider = smodel, sprov


@comando("model", "selecionar modelo", usage="/model [id]", category="modelo",
         autocomplete=())
def h_model(ctx, args):
    if not args:
        atual = ctx.modelo()
        escolhas = [{"rotulo": m.id, "valor": m.id, "ativo": m.id == atual,
                     "detalhe": f"{m.provider} · ctx {humano(m.cap.max_context)}"}
                    for m in ctx.registro.listar()]
        return Resposta(titulo="Escolha um modelo", escolhas=escolhas)
    m = ctx.registro.get(args[0])
    if not m:
        return Resposta([f"Modelo '{args[0]}' nao encontrado. Veja /models."], erro=True)
    # guarda o anterior: se a troca do processo falhar, a config NAO pode ficar
    # apontando para um modelo que o motor nao esta servindo. Estado mentindo sobre
    # o motor foi exatamente o defeito que este comando tinha.
    _anterior = (ctx.modelo(), ctx.sessao.model, ctx.sessao.provider)
    ctx.config.set("model", m.id)
    ctx.sessao.model = m.id
    ctx.sessao.provider = m.provider
    janela = ctx.janela()
    aviso = []
    if janela > m.cap.max_context:
        ctx.config.set("context", m.cap.max_context)
        aviso = [f"Janela ajustada para {humano(m.cap.max_context)} "
                 f"(maximo deste modelo)."]

    # Trocar de modelo e trocar o PROCESSO, nao o rotulo.
    # Ate 2026-08-18 este comando so escrevia config["model"] e o runtime mandava
    # {"model": id} no corpo. O llama-server IGNORA esse campo: ele serve o GGUF da
    # linha de comando. A tela dizia "Modelo alterado" e o modelo antigo respondia.
    if m.provider != "local":
        return Resposta([f"Modelo alterado para {m.id}"] + aviso, ok=True)

    from gatinho import motor
    arq = ctx.registro.caminho(m)
    if not motor.gerenciavel():
        return Resposta([f"Modelo alterado para {m.id}",
                         "gestao de motor desligada (GATINHO_MOTOR=off): o processo "
                         "nao foi trocado."] + aviso, ok=True)
    if not arq:
        _reverter(ctx, _anterior)
        return Resposta([f"NAO troquei o modelo: nao achei o .gguf de {m.id}.",
                         "Veja /models — os modelos com arquivo ficam em servidor/modelos/.",
                         f"Continua valendo {_anterior[0]}."], erro=True)
    if not motor.no_ar():
        return Resposta([f"Modelo alterado para {m.id}",
                         f"o motor nao esta no ar — {arq.name} sobe no proximo "
                         f"./gatinho.sh"] + aviso, ok=True)
    ok, msg = motor.trocar(arq, ctx_tokens=ctx.janela())
    if not ok:
        _reverter(ctx, _anterior)
        return Resposta([f"NAO troquei o modelo: {msg}",
                         f"Continua valendo {_anterior[0]} — o que o motor esta servindo."],
                        erro=True)
    return Resposta([f"Modelo alterado para {m.id}", msg] + aviso, ok=True)


@comando("models", "listar modelos com capacidades", category="modelo")
def h_models(ctx, args):
    linhas = []
    for m in ctx.registro.listar():
        c = m.cap
        linhas += [m.id,
                   f"  provider: {m.provider}",
                   f"  contexto maximo: {humano(c.max_context)}",
                   f"  tools: {'sim' if c.supports_tools else 'nao'}",
                   f"  reasoning effort: {'sim' if c.supports_reasoning_effort else 'nao'}",
                   ""]
    return Resposta(linhas or ["Nenhum modelo no registro."], titulo="Modelos")


@comando("provider", "selecionar provider", usage="/provider [nome]", category="modelo")
def h_provider(ctx, args):
    if not args:
        atual = ctx.config.get("provider")
        escolhas = [{"rotulo": p.nome, "valor": p.nome, "ativo": p.nome == atual,
                     "detalhe": f"{p.tipo}"
                                + ("" if not p.chave_env else
                                   f" · chave {'configurada' if p.tem_chave else 'AUSENTE'}")}
                    for p in ctx.registro.provedores.values()]
        return Resposta(titulo="Escolha um provider", escolhas=escolhas)
    nome = args[0].lower()
    p = ctx.registro.provedores.get(nome)
    if not p:
        return Resposta([f"Provider '{nome}' nao existe."], erro=True)
    if p.chave_env and not p.tem_chave:
        return Resposta([f"Provider {nome} exige a variavel {p.chave_env}, que nao esta definida.",
                         "Defina no ambiente — o Gatinho nunca guarda nem mostra a chave."],
                        erro=True)
    ctx.config.set("provider", nome)
    ctx.sessao.provider = nome
    return Resposta([f"Provider: {nome}"], ok=True)


# =================================================================== geracao
@comando("context", "configurar janela de contexto", usage="/context [8k|16k|32k]",
         aliases=("ctx",), category="contexto")
def h_context(ctx, args):
    cap = ctx.cap()
    if not args:
        atual = ctx.janela()
        opcoes = [8192, 16384, 32768, 65536, 131072]
        escolhas = [{"rotulo": humano(o), "valor": str(o), "ativo": o == atual,
                     "detalhe": "" if o <= cap.max_context else "acima do maximo do modelo"}
                    for o in opcoes if o <= cap.max_context]
        return Resposta([f"Janela atual: {humano(atual)}"], titulo="Contexto", escolhas=escolhas)
    ok, msg = checar_parametro(cap, "context")
    if not ok:
        return Resposta([msg], erro=True)
    try:
        v = tamanho_contexto(args[0])
    except ValueError:
        return Resposta([f"Valor invalido: {args[0]}"], erro=True)
    if v > cap.max_context:
        return Resposta([f"{humano(v)} passa do maximo do modelo ({humano(cap.max_context)}).",
                         "O valor nao foi alterado."], erro=True)
    ctx.config.set("context", v)
    ctx.sessao.context = v
    return Resposta([f"Contexto: {humano(v)}"], ok=True)


@comando("effort", "reasoning effort", usage="/effort [minimal|low|medium|high]", category="geracao")
def h_effort(ctx, args):
    cap = ctx.cap()
    ok, msg = checar_parametro(cap, "reasoning_effort")
    if not ok:
        return Resposta([msg], erro=True)
    niveis = ["minimal", "low", "medium", "high"]
    if not args:
        atual = ctx.config.get("effort")
        return Resposta(titulo="Reasoning effort",
                        escolhas=[{"rotulo": n, "valor": n, "ativo": n == atual} for n in niveis])
    v = args[0].lower()
    if v not in niveis:
        return Resposta([f"Nivel invalido: {v}. Use {', '.join(niveis)}."], erro=True)
    ctx.config.set("effort", v)
    return Resposta([f"Effort: {v}"], ok=True)


@comando("temperature", "temperatura", usage="/temperature 0.2", aliases=("temp",),
         category="geracao")
def h_temp(ctx, args):
    ok, msg = checar_parametro(ctx.cap(), "temperature")
    if not ok:
        return Resposta([msg], erro=True)
    v = _num(args)
    if v is None or not 0 <= v <= 2:
        return Resposta([f"Temperatura atual: {ctx.config.get('temperature')}",
                         "Use /temperature <0 a 2>"], erro=bool(args))
    ctx.config.set("temperature", v)
    return Resposta([f"Temperatura: {v}"], ok=True)


@comando("top-p", "top-p", usage="/top-p 0.95", aliases=("topp",), category="geracao")
def h_topp(ctx, args):
    ok, msg = checar_parametro(ctx.cap(), "top_p")
    if not ok:
        return Resposta([msg], erro=True)
    v = _num(args)
    if v is None or not 0 < v <= 1:
        return Resposta([f"top-p atual: {ctx.config.get('top_p')}", "Use /top-p <0 a 1>"],
                        erro=bool(args))
    ctx.config.set("top_p", v)
    return Resposta([f"top-p: {v}"], ok=True)


@comando("max-output", "maximo de tokens de saida", usage="/max-output 4096",
         aliases=("maxout",), category="geracao")
def h_maxout(ctx, args):
    cap = ctx.cap()
    if not args:
        return Resposta([f"max output: {ctx.config.get('max_output')} tokens",
                         f"(nao confundir com a janela de contexto: {humano(ctx.janela())})"])
    try:
        v = int(args[0])
    except ValueError:
        return Resposta([f"Valor invalido: {args[0]}"], erro=True)
    if v > cap.max_output:
        return Resposta([f"{v} passa do maximo de saida do modelo ({cap.max_output})."], erro=True)
    ctx.config.set("max_output", v)
    return Resposta([f"max output: {v} tokens"], ok=True)


# ====================================================================== modo
@comando("mode", "alterar modo", usage="/mode [plan|supervise]", category="modo")
def h_mode(ctx, args):
    if not args:
        return Resposta(titulo="Modo",
                        escolhas=[{"rotulo": MODOS[k], "valor": k, "ativo": k == ctx.modo}
                                  for k in ("plan", "full", "perm")])
    v = args[0].lower()
    apelidos = {"plan": "plan", "planejamento": "plan", "p": "plan",
                "full": "full", "supervise": "full", "supervisao": "full", "s": "full",
                "perm": "perm", "permissao": "perm", "permissão": "perm"}
    if v not in apelidos:
        return Resposta(["Use /mode plan, full ou perm."], erro=True)
    ctx.modo = apelidos[v]
    return Resposta([f"Modo: {ctx.nome_modo()}"], ok=True)


# =================================================================== harness
@comando("harness", "escolher harness manualmente", usage="/harness [auto|fast|mast]",
         category="harness")
def h_harness(ctx, args):
    mapa = {"auto": "auto", "fast": "fast-coder", "fast-coder": "fast-coder",
            "mast": "mast-agent", "mast-agent": "mast-agent"}
    if not args:
        atual = ctx.harness_pedido()
        return Resposta(titulo="Harness",
                        escolhas=[{"rotulo": r, "valor": r, "ativo": r == atual}
                                  for r in ("auto", "fast-coder", "mast-agent")])
    v = mapa.get(args[0].lower())
    if not v:
        return Resposta(["Use auto, fast ou mast."], erro=True)
    ctx.config.set("harness", v)
    ctx.sessao.harness = v
    return Resposta([f"Harness: {v}"], ok=True)


@comando("router", "estado do roteador V3", usage="/router [threshold N]", category="harness",
         autocomplete=("threshold",))
def h_router(ctx, args):
    if args and args[0] == "threshold":
        if len(args) < 2:
            return Resposta([f"Threshold atual: {ctx.config.get('router.threshold')} tokens"])
        try:
            v = int(args[1])
        except ValueError:
            return Resposta([f"Valor invalido: {args[1]}"], erro=True)
        ctx.config.set("router.threshold", v)
        return Resposta([f"Threshold: {v} tokens"], ok=True)
    d = ctx.ultima_decisao_roteador
    linhas = ["Roteador V3", "",
              f"Modo: {'automatico' if ctx.harness_pedido() == 'auto' else 'manual'}",
              f"Threshold: {ctx.config.get('router.threshold')} tokens"]
    if d:
        linhas += ["", "Ultima decisao:",
                   f"Estimativa: {d.get('context_estimate')} tokens",
                   f"Selecionado: {d.get('selected_harness')}",
                   f"Motivo: {d.get('router_reason')}"]
    else:
        linhas += ["", "Ainda nao houve decisao nesta sessao."]
    return Resposta(linhas)


# =================================================================== sessoes
@comando("new", "nova sessao", category="sessao")
def h_new(ctx, args):
    ctx.sessao.salvar()
    s = ctx.nova_sessao()
    return Resposta([f"Nova sessao: {s.session_id}"], acao="novo", ok=True)


@comando("sessions", "listar sessoes recentes", category="sessao")
def h_sessions(ctx, args):
    itens = ses.listar()
    if not itens:
        return Resposta(["Nenhuma sessao salva ainda."], titulo="Sessoes")
    escolhas = [{"rotulo": i["nome"], "valor": i["session_id"],
                 "ativo": i["session_id"] == ctx.sessao.session_id,
                 "detalhe": f"{i['idade']} · {i['mensagens']} msgs"} for i in itens]
    return Resposta(titulo="Sessoes", escolhas=escolhas)


@comando("resume", "retomar sessao", usage="/resume [id]", category="sessao")
def h_resume(ctx, args):
    if not args:
        return h_sessions(ctx, args)
    s = ses.Sessao.carregar(args[0])
    if not s:
        return Resposta([f"Sessao '{args[0]}' nao encontrada."], erro=True)
    ctx.sessao.salvar()
    ctx.sessao = s
    if s.model:
        ctx.config.set("model", s.model)
    if s.context:
        ctx.config.set("context", s.context)
    return Resposta([f"Sessao retomada: {s.nome or s.session_id}",
                     f"{len(s.messages)} mensagens, {len(s.files)} arquivos"], ok=True)


@comando("rename", "renomear a sessao atual", usage="/rename novo-nome", category="sessao")
def h_rename(ctx, args):
    if not args:
        return Resposta([f"Nome atual: {ctx.sessao.nome or '(sem nome)'}",
                         "Use /rename <novo-nome>"], erro=True)
    ctx.sessao.nome = " ".join(args)[:60]
    ctx.sessao.salvar()
    return Resposta([f"Sessao renomeada: {ctx.sessao.nome}"], ok=True)


@comando("delete-session", "apagar uma sessao", usage="/delete-session [id]", category="sessao")
def h_delete_session(ctx, args):
    alvo = args[0] if args else ctx.sessao.session_id
    return Resposta([f"Apagar a sessao '{alvo}'? Isto nao tem volta."],
                    acao="confirmar-apagar", dados={"session_id": alvo})


@comando("session", "gerenciar sessoes", usage="/session <new|list|resume|rename|delete|info>",
         aliases=("sess",), category="sessao",
         autocomplete=("new", "list", "resume", "rename", "delete", "info"))
def h_session(ctx, args):
    sub = args[0] if args else "info"
    resto = args[1:]
    if sub == "new":
        return h_new(ctx, resto)
    if sub in ("list", "ls"):
        return h_sessions(ctx, resto)
    if sub == "resume":
        return h_resume(ctx, resto)
    if sub == "rename":
        return h_rename(ctx, resto)
    if sub == "delete":
        return h_delete_session(ctx, resto)
    s = ctx.sessao
    return Resposta([f"id: {s.session_id}", f"nome: {s.nome or '(sem nome)'}",
                     f"projeto: {s.project}", f"modelo: {s.model} ({s.provider})",
                     f"mensagens: {len(s.messages)}", f"arquivos: {len(s.files)}",
                     f"compactacoes: {s.compaction_count}",
                     f"criada: {s.created_at}"], titulo="Sessao")


@comando("export", "exportar a sessao", usage="/export [json|markdown]", category="sessao")
def h_export(ctx, args):
    fmt = (args[0].lower() if args else "markdown")
    if fmt not in ("json", "markdown", "md"):
        return Resposta(["Formatos: json ou markdown."], erro=True)
    fmt = "json" if fmt == "json" else "markdown"
    texto = ses.exportar(ctx.sessao, fmt)
    destino = ctx.projeto / f"sessao-{ctx.sessao.session_id}.{'json' if fmt == 'json' else 'md'}"
    destino.write_text(texto, encoding="utf-8")
    return Resposta([f"Exportado: {destino}"], ok=True)


@comando("history", "historico resumido da conversa", category="sessao")
def h_history(ctx, args):
    if not ctx.sessao.messages:
        return Resposta(["Conversa vazia."])
    linhas = []
    for m in ctx.sessao.messages[-20:]:
        quem = {"user": "voce", "assistant": "gatinho", "system": "sistema"}.get(m["role"], m["role"])
        texto = str(m.get("content") or "").replace("\n", " ")[:90]
        linhas.append(f"{quem:8} {texto}")
    return Resposta(linhas, titulo="Historico")


# ================================================================== contexto
@comando("compact", "compactar o contexto agora", category="contexto")
def h_compact(ctx, args):
    antes, depois = ctx.sessao.compactar()
    ta, td = antes // 4, depois // 4
    ctx.metricas.compaction_count = ctx.sessao.compaction_count
    ctx.metricas.context_before, ctx.metricas.context_after = ta, td
    ctx.metricas.marcar_contexto(td)
    if antes == depois:
        return Resposta(["Nada a compactar ainda."])
    return Resposta([f"Contexto compactado", f"{humano(ta)} → {humano(td)}"], ok=True)


@comando("context-info", "detalhes do contexto", aliases=("ctxinfo",), category="contexto")
def h_context_info(ctx, args):
    m = ctx.metricas
    return Resposta([f"Usado: {humano(m.contexto_atual)}",
                     f"Maximo: {humano(ctx.janela())}",
                     f"Pico: {humano(m.contexto_pico)}",
                     f"Compactacoes: {m.compaction_count}"], titulo="Contexto")


@comando("reset", "descartar o contexto da conversa atual", category="contexto")
def h_reset(ctx, args):
    n = len(ctx.sessao.messages)
    return Resposta([f"Isto descarta as {n} mensagens desta conversa.",
                     "Arquivos, decisoes e o nome da sessao ficam.",
                     "Confirme para prosseguir."],
                    acao="confirmar-reset", dados={"mensagens": n})


# ==================================================================== skills
@comando("skills", "gerenciar skills", usage="/skills [list|info|enable|disable|reload]",
         category="skills", autocomplete=("list", "info", "enable", "disable", "reload"))
def h_skills(ctx, args):
    sub = args[0] if args else "list"
    resto = args[1:]
    if sub == "reload":
        n = ctx.skills.recarregar()
        return Resposta([f"{n} skills recarregadas."], ok=True)
    if sub == "info" and resto:
        return h_skill(ctx, resto)
    if sub in ("enable", "disable") and resto:
        ligar = sub == "enable"
        if not ctx.skills.ligar(resto[0], ligar):
            return Resposta([f"Skill '{resto[0]}' nao existe."], erro=True)
        return Resposta([f"Skill {resto[0]}: {'ativa' if ligar else 'desativada'}"], ok=True)
    linhas = []
    for s in ctx.skills.listar():
        marca = " " if s.ativa else "×"
        linhas.append(f"{marca} {s.nome}")
    return Resposta(linhas, titulo="Skills disponiveis")


@comando("skill", "detalhe de uma skill", usage="/skill nome", category="skills")
def h_skill(ctx, args):
    if not args:
        return h_skills(ctx, [])
    s = ctx.skills.get(args[0])
    if not s:
        return Resposta([f"Skill '{args[0]}' nao existe."], erro=True)
    linhas = [s.resumo()[:400]]
    if s.caminho:
        linhas += ["", f"arquivo: {s.caminho}"]
    linhas += [f"estado: {'ativa' if s.ativa else 'desativada'}"]
    return Resposta(linhas, titulo=f"skill {s.nome}")


# ================================================================ ferramentas
@comando("tools", "ferramentas disponiveis", category="ferramentas")
def h_tools(ctx, args):
    from .runtime import FERRAMENTAS_INFO
    return Resposta([n for n in FERRAMENTAS_INFO], titulo="Ferramentas")


@comando("tool", "detalhe de uma ferramenta", usage="/tool read_file", category="ferramentas")
def h_tool(ctx, args):
    from .runtime import FERRAMENTAS_INFO
    if not args:
        return h_tools(ctx, [])
    info = FERRAMENTAS_INFO.get(args[0])
    if not info:
        return Resposta([f"Ferramenta '{args[0]}' nao existe. Veja /tools."], erro=True)
    perm = ctx.config.get(f"permissions.{info['permissao']}", "ask")
    return Resposta([info["descricao"], "",
                     "parametros: " + ", ".join(info["parametros"]),
                     f"status: {'ativa' if info['ativa'] else 'inativa'}",
                     f"permissao: {info['permissao']} = {perm}"], titulo=args[0])


@comando("tools-per-step", "maximo de ferramentas por resposta do modelo",
         usage="/tools-per-step [N]", aliases=("tps",), category="ferramentas")
def h_tps(ctx, args):
    if not args:
        return Resposta([f"Maximo atual: {ctx.config.get('tools.max_per_step')}",
                         "O modelo age ate esse limite, ve o resultado, e so entao continua."])
    try:
        v = int(args[0])
    except ValueError:
        return Resposta([f"Valor invalido: {args[0]}"], erro=True)
    if v < 1:
        return Resposta(["Precisa ser pelo menos 1."], erro=True)
    ctx.config.set("tools.max_per_step", v)
    return Resposta([f"Maximo por resposta: {v}"], ok=True)


# ================================================================ permissoes
@comando("permissions", "permissoes por categoria", usage="/permissions [categoria] [ask|allow|deny]",
         aliases=("perms",), category="permissoes")
def h_permissions(ctx, args):
    perms = ctx.config.get("permissions", {})
    if not args:
        return Resposta([f"{k:18} {v}" for k, v in perms.items()], titulo="Permissoes")
    cat = args[0].lower()
    if cat not in perms:
        return Resposta([f"Categoria '{cat}' nao existe. Veja /permissions."], erro=True)
    if len(args) < 2:
        return Resposta([f"{cat}: {perms[cat]}"])
    modo = args[1].lower()
    if modo not in ("ask", "allow", "deny"):
        return Resposta(["Modos: ask, allow, deny."], erro=True)
    ctx.config.set(f"permissions.{cat}", modo)
    return Resposta([f"{cat}: {modo}"], ok=True)


@comando("approve", "aprovar a acao pendente", category="permissoes")
def h_approve(ctx, args):
    if not ctx.pendencia:
        return Resposta(["Nao ha acao pendente."], erro=True)
    ctx.pendencia.resolvida = "approve"
    return Resposta([f"Aprovado: {ctx.pendencia.ferramenta}"], ok=True)


@comando("deny", "negar a acao pendente", category="permissoes")
def h_deny(ctx, args):
    if not ctx.pendencia:
        return Resposta(["Nao ha acao pendente."], erro=True)
    ctx.pendencia.resolvida = "deny"
    return Resposta([f"Negado: {ctx.pendencia.ferramenta}"], ok=True)


@comando("auto-approve", "aprovar tudo automaticamente", usage="/auto-approve [on|off]",
         category="permissoes")
def h_auto_approve(ctx, args):
    if not args:
        estado = "LIGADO" if ctx.config.get("auto_approve") else "desligado"
        return Resposta([f"Auto-aprovacao: {estado}",
                         "Com isso ligado, acoes de shell rodam sem te perguntar."])
    v = args[0].lower() in ("on", "sim", "true", "1")
    ctx.config.set("auto_approve", v)
    return Resposta([f"Auto-aprovacao: {'LIGADA — acoes de shell nao serao confirmadas' if v else 'desligada'}"],
                    ok=True)


# =================================================================== arquivos
@comando("files", "arquivos tocados nesta sessao", category="arquivos")
def h_files(ctx, args):
    if not ctx.sessao.files:
        return Resposta(["Nenhum arquivo tocado ainda."], titulo="Arquivos")
    return Resposta([f"{v:8} {k}" for k, v in sorted(ctx.sessao.files.items())],
                    titulo="Arquivos")


@comando("diff", "o que mudou nesta sessao", category="arquivos")
def h_diff(ctx, args):
    """Na sandbox o git nao serve — o diff util e sandbox × projeto de origem.

    Bug achado na auditoria: olhava ctx.projeto e mostrava "sem alteracoes"
    mesmo com o agente tendo escrito um monte na sandbox.
    """
    import difflib
    from . import sandbox as sb
    onde = ctx.pasta_trabalho()
    if ctx.modo_pasta == sb.MODO_SANDBOX and ctx.work is not None:
        linhas, mudados = [], 0
        for rel, acao in sorted(ctx.sessao.files.items()):
            novo = onde / rel
            velho = ctx.projeto / rel
            if not novo.exists():
                continue
            try:
                txt_novo = novo.read_text(encoding="utf-8", errors="replace").splitlines()
                txt_velho = (velho.read_text(encoding="utf-8", errors="replace").splitlines()
                             if velho.exists() else [])
            except OSError:
                continue
            d = list(difflib.unified_diff(txt_velho, txt_novo,
                                          fromfile=f"projeto/{rel}", tofile=f"work/{rel}",
                                          lineterm="", n=2))
            if d:
                mudados += 1
                linhas += d[:60] + [""]
        if not mudados:
            return Resposta(["Nada mudou ainda nesta sessao."], titulo="Diff")
        return Resposta(linhas, titulo=f"Diff · {mudados} arquivo(s) · sandbox x projeto")
    if not shutil.which("git"):
        return Resposta(["git nao esta instalado — sem base de comparacao."], erro=True)
    r = subprocess.run(["git", "diff", "--stat"], cwd=str(onde), capture_output=True, text=True)
    if r.returncode != 0:
        return Resposta([f"{onde} nao e um repositorio git."], erro=True)
    return Resposta((r.stdout or "(sem alteracoes)").splitlines(), titulo="Diff")


@comando("undo", "desfazer a ultima alteracao do agente", category="arquivos")
def h_undo(ctx, args):
    from .runtime import desfazer_ultima
    ok, msg = desfazer_ultima(ctx)
    return Resposta([msg], ok=ok, erro=not ok)


@comando("rollback", "desfazer todas as alteracoes desta sessao", category="arquivos")
def h_rollback(ctx, args):
    from .runtime import backups_da_sessao
    n = len(backups_da_sessao(ctx))
    if not n:
        return Resposta(["Nao ha alteracao registrada para desfazer."], erro=True)
    return Resposta([f"Isto desfaz {n} alteracao(oes) feitas pelo agente nesta sessao."],
                    acao="confirmar-rollback", dados={"n": n})


@comando("git", "status resumido do git", usage="/git [status|diff|commit]", category="arquivos",
         autocomplete=("status", "diff", "commit"))
def h_git(ctx, args):
    if not shutil.which("git"):
        return Resposta(["git nao esta instalado."], erro=True)
    sub = args[0] if args else "status"
    if sub == "commit":
        return Resposta(["O Gatinho nao faz commit automatico.",
                         "Rode voce mesmo: /run git commit -m \"...\""], erro=True)
    cmd = {"status": ["git", "status", "--short", "--branch"],
           "diff": ["git", "diff", "--stat"]}.get(sub)
    if not cmd:
        return Resposta([f"Subcomando '{sub}' nao suportado."], erro=True)
    # git e do PROJETO, nao da sandbox (a sandbox nao e repositorio).
    onde = ctx.projeto
    r = subprocess.run(cmd, cwd=str(onde), capture_output=True, text=True)
    if r.returncode != 0:
        return Resposta([f"{onde} nao e um repositorio git."], erro=True)
    aviso = ([] if ctx.pasta_trabalho() == onde else
             ["", f"(o agente esta escrevendo em {ctx.pasta_trabalho().name}, "
              f"fora do git — use /diff para ver o trabalho dele)"])
    return Resposta((r.stdout or "(limpo)").splitlines() + aviso, titulo=f"git {sub}")


# =================================================================== execucao
@comando("run", "rodar um comando", usage="/run pytest -q", category="execucao")
def h_run(ctx, args):
    if not args:
        return Resposta(["Use /run <comando>"], erro=True)
    from .runtime import rodar_comando
    return rodar_comando(ctx, " ".join(args))


@comando("tests", "rodar os testes do projeto", category="execucao")
def h_tests(ctx, args):
    from .runtime import detectar_testes, rodar_comando
    cmd = detectar_testes(ctx.pasta_trabalho())
    if not cmd:
        return Resposta(["Nao identifiquei o framework de testes deste projeto.",
                         "Use /run <comando> com o comando certo."], erro=True)
    return rodar_comando(ctx, cmd)


@comando("stop", "interromper a execucao atual", category="execucao")
def h_stop(ctx, args):
    if not ctx.executando:
        return Resposta(["Nada rodando agora."])
    ctx.parar = True
    return Resposta(["Parando apos a acao atual. A sessao fica."], ok=True)


@comando("pause", "pausar o agente", category="execucao")
def h_pause(ctx, args):
    ctx.pausado = True
    return Resposta(["Pausado. /continue retoma."], ok=True)


@comando("continue", "retomar o agente", aliases=("cont",), category="execucao")
def h_continue(ctx, args):
    ctx.pausado = False
    return Resposta(["Retomando."], ok=True)


# ==================================================================== estado
@comando("status", "status atual", aliases=("st",), category="sistema")
def h_status(ctx, args):
    c, m = ctx.config, ctx.metricas
    d = ctx.ultima_decisao_roteador
    dur = int(m.tempo_total)
    linhas = [f"Gatinho v{VERSAO}", "",
              f"Modelo: {ctx.modelo()}",
              f"Provider: {c.get('provider')}",
              f"Contexto: {humano(m.contexto_atual)} / {humano(ctx.janela())}",
              f"Modo: {ctx.nome_modo()}", "",
              f"Harness solicitado: {ctx.harness_pedido()}",
              f"Harness selecionado: {d.get('selected_harness', '—')}", "",
              f"Effort: {c.get('effort')}",
              f"Temperature: {c.get('temperature')}",
              f"Top-p: {c.get('top_p')}",
              f"Max output: {c.get('max_output')}", "",
              f"Sessao: {ctx.sessao.nome or ctx.sessao.session_id}",
              f"Duracao: {dur // 60:02d}:{dur % 60:02d}"]
    return Resposta(linhas, titulo="Status")


@comando("metrics", "metricas da execucao", aliases=("met",), category="sistema")
def h_metrics(ctx, args):
    return Resposta(ctx.metricas.resumo_linhas(), titulo="Metricas")


@comando("runs", "execucoes desta sessao", category="sistema")
def h_runs(ctx, args):
    if not ctx.runs:
        return Resposta(["Nenhuma execucao ainda."], titulo="Execucoes")
    linhas = [f"{r['id']:9} {r['status']:9} {r['duracao']}" for r in ctx.runs]
    return Resposta(linhas, titulo="Execucoes")


@comando("inspect", "detalhes de uma execucao", usage="/inspect run_ab12", category="sistema")
def h_inspect(ctx, args):
    if not ctx.runs:
        return Resposta(["Nenhuma execucao para inspecionar."], erro=True)
    alvo = args[0] if args else ctx.runs[-1]["id"]
    r = next((x for x in ctx.runs if x["id"] == alvo), None)
    if not r:
        return Resposta([f"Execucao '{alvo}' nao encontrada. Veja /runs."], erro=True)
    linhas = [f"modelo: {r.get('modelo')}", f"provider: {r.get('provider')}",
              f"harness: {r.get('harness')}", f"contexto pico: {r.get('contexto_pico')}",
              f"tempo: {r.get('duracao')}",
              f"arquivos: {', '.join(r.get('arquivos', [])) or '—'}",
              f"testes: {r.get('testes', '—')}",
              f"tools emitidas: {r.get('tool_calls_emitted')}",
              f"tools executadas: {r.get('tool_calls_executed')}",
              f"tools bloqueadas: {r.get('tool_calls_blocked')}",
              f"resultado: {r.get('status')}"]
    return Resposta(linhas, titulo=alvo)


@comando("verbose", "nivel de detalhe", usage="/verbose [quiet|normal|verbose|debug]",
         category="sistema")
def h_verbose(ctx, args):
    if not args:
        atual = ctx.config.get("verbose")
        return Resposta(titulo="Detalhamento",
                        escolhas=[{"rotulo": v, "valor": v, "ativo": v == atual}
                                  for v in VERBOSIDADES])
    v = args[0].lower()
    if v not in VERBOSIDADES:
        return Resposta([f"Niveis: {', '.join(VERBOSIDADES)}"], erro=True)
    ctx.config.set("verbose", v)
    return Resposta([f"Detalhamento: {v}"], ok=True)


@comando("debug", "modo tecnico", category="sistema")
def h_debug(ctx, args):
    ctx.config.set("verbose", "debug")
    ultimos = ctx.logs[-15:]
    linhas = [f"[{l['nivel']}] {l['texto']}" for l in ultimos] or ["(sem eventos ainda)"]
    return Resposta(linhas + ["", "Detalhamento agora: debug. Volte com /verbose normal."],
                    titulo="Debug")


@comando("logs", "onde ficam os logs", category="sistema")
def h_logs(ctx, args):
    from .sessao import RAIZ_SESSOES
    linhas = [f"sessoes: {RAIZ_SESSOES}", f"config global: {ctx.config.__class__.__module__}",
              "", "ultimos eventos:"]
    linhas += [f"  [{l['nivel']}] {l['texto']}" for l in ctx.logs[-10:]] or ["  (vazio)"]
    return Resposta(linhas, titulo="Logs")


@comando("config", "configuracao", usage="/config [set chave valor]", category="sistema",
         autocomplete=("set", "show", "save"))
def h_config(ctx, args):
    if not args:
        cats = ["Modelo", "Provider", "Geracao", "Contexto", "Harness",
                "Interface", "Permissoes", "Sessoes", "Skills"]
        return Resposta(titulo="Configuracao",
                        escolhas=[{"rotulo": c, "valor": c.lower(), "ativo": False} for c in cats])
    sub = args[0]
    if sub == "set" and len(args) >= 3:
        chave, valor = args[1], " ".join(args[2:])
        atalhos = {"context": "context", "temperature": "temperature", "temp": "temperature",
                   "top_p": "top_p", "harness": "harness", "model": "model",
                   "effort": "effort", "max_output": "max_output"}
        chave = atalhos.get(chave, chave)
        if chave == "context":
            return h_context(ctx, [valor])
        if chave == "temperature":
            return h_temp(ctx, [valor])
        if chave == "harness":
            return h_harness(ctx, [valor])
        if chave == "model":
            return h_model(ctx, [valor])
        try:
            valor_conv = json.loads(valor)
        except Exception:
            valor_conv = valor
        ctx.config.set(chave, valor_conv)
        return Resposta([f"{chave} = {valor_conv}"], ok=True)
    if sub == "save":
        camada = args[1] if len(args) > 1 else "global"
        if camada not in ("global", "projeto"):
            return Resposta(["Use /config save global ou /config save projeto"], erro=True)
        p = ctx.config.salvar(camada)
        return Resposta([f"Configuracao salva: {p}"], ok=True)
    chaves = ["model", "provider", "context", "effort", "temperature", "top_p",
              "max_output", "harness", "router.threshold", "tools.max_per_step"]
    linhas = [f"{k:20} {ctx.config.get(k)}   ({ctx.config.origem(k)})" for k in chaves]
    return Resposta(linhas, titulo="Configuracao efetiva")


@comando("benchmark", "rodar benchmarks", usage="/benchmark [list|run|compare]",
         aliases=("bench",), category="avancado", autocomplete=("list", "run", "compare"))
def h_benchmark(ctx, args):
    from .runtime import BENCHES
    sub = args[0] if args else "list"
    if sub == "list":
        return Resposta([f"{k:18} {v['descricao']}" for k, v in BENCHES.items()],
                        titulo="Benchmarks")
    if sub == "run":
        if len(args) < 2 or args[1] not in BENCHES:
            return Resposta(["Use /benchmark run <nome>. Veja /benchmark list."], erro=True)
        b = BENCHES[args[1]]
        return Resposta([f"Benchmark '{args[1]}' roda fora da CLI, porque leva horas de GPU.",
                         "Comando:", f"  {b['comando']}"], titulo="Benchmark")
    if sub == "compare":
        return Resposta(["Comparacao entre rodadas fica nos paineis dos benches:",
                         "  harness-bench/BENCHMARK-HARNESS-FINAL.html",
                         "  harness-contexto/BENCHMARK-CONTEXTO-FINAL.html"])
    return Resposta([f"Subcomando '{sub}' nao existe."], erro=True)


# =================================================== sandbox e works (2026-08-17)
@comando("sandbox", "onde o agente escreve", usage="/sandbox [on|off|info]",
         category="sandbox", autocomplete=("on", "off", "info"))
def h_sandbox(ctx, args):
    from . import sandbox as sb
    sub = (args[0].lower() if args else "info")
    if sub in ("on", "ligar", "sim"):
        ctx.usar_sandbox(True)
        return Resposta([f"SANDBOX ligada — o agente escreve em {ctx.pasta_trabalho()}",
                         "A tua pasta de verdade fica intocada."], ok=True)
    if sub in ("off", "desligar", "direto"):
        ctx.usar_sandbox(False)
        return Resposta([sb.AVISO_DIRETO, "", f"pasta: {ctx.pasta_trabalho()}"], erro=True)
    return Resposta([f"modo: {ctx.modo_pasta}",
                     f"escrevendo em: {ctx.pasta_trabalho()}",
                     f"teu projeto:   {ctx.projeto}",
                     "",
                     "/sandbox on  → trabalha numa cópia (padrão)",
                     "/sandbox off → escreve no projeto de verdade"], titulo="Sandbox")


@comando("works", "pastas de trabalho das sessoes", usage="/works [apagar <nome>]",
         category="sandbox", autocomplete=("apagar",))
def h_works(ctx, args):
    from . import sandbox as sb
    if args and args[0] == "apagar" and len(args) > 1:
        ok, msg = sb.apagar(args[1])
        return Resposta([msg], ok=ok, erro=not ok)
    itens = sb.listar()
    if not itens:
        return Resposta(["Nenhum work ainda."], titulo="Works")
    pastas, bytes_ = sb.tamanho_total()
    linhas = [f"{i['nome']:34} {i['arquivos']:3} arquivos  {i['criado_em'][:16]}" for i in itens]
    linhas += ["", f"{pastas} pastas · {bytes_/1048576:.1f} MB em {sb.WORKS}"]
    return Resposta(linhas, titulo="Works")


@comando("idioma", "idioma da interface e da resposta", usage="/idioma [pt|en|es|zh|auto]",
         aliases=("lang", "language"), category="sandbox")
def h_idioma(ctx, args):
    from . import i18n
    if not args:
        atual = i18n.IDIOMAS.get(ctx.idioma, {}).get("nome", ctx.idioma)
        return Resposta([f"idioma atual: {atual}",
                         "detecção automática pela tua mensagem está ligada"],
                        titulo="Idioma",
                        escolhas=[{"rotulo": v["nome"], "valor": k, "ativo": k == ctx.idioma}
                                  for k, v in i18n.IDIOMAS.items()])
    v = args[0].lower()
    if v in ("auto", "automatico"):
        ctx.idioma = i18n.PADRAO
        return Resposta(["detecção automática — escrevo no idioma que tu usar"], ok=True)
    if v not in i18n.IDIOMAS:
        return Resposta([f"idiomas: {', '.join(i18n.IDIOMAS)}"], erro=True)
    ctx.idioma = v
    return Resposta([f"idioma: {i18n.IDIOMAS[v]['nome']}"], ok=True)


# --------------------------------------------------------------- apelidos pt-BR
# A interface fala portugues, e a paleta da web ate prometia "/limpar" e "/modo" —
# que o motor nao conhecia. Quem digitava recebia "comando desconhecido". Prometer
# na tela um comando que nao existe e defeito; ou tira da tela, ou faz existir.
# Como a interface e do Pai e ela e em pt-BR, os apelidos passam a existir.
_APELIDOS_PT = {
    "limpar": "clear", "modo": "mode", "modelo": "model", "modelos": "models",
    "ajuda": "help", "sair": "exit", "testes": "tests", "rodar": "run",
    "historico": "history", "sessoes": "sessions", "sessao": "session",
    "ferramentas": "tools", "ferramenta": "tool", "metricas": "metrics",
    "contexto": "context", "compactar": "compact", "arquivos": "files",
    "permissoes": "permissions", "versao": "version", "sobre": "about",
    "desfazer": "undo", "continuar": "continue", "parar": "stop",
    "renomear": "rename", "exportar": "export", "novo": "new", "logs": "logs",
}
for _apelido, _destino in _APELIDOS_PT.items():
    if _destino in REGISTRO and _apelido not in REGISTRO and _apelido not in ALIASES:
        ALIASES[_apelido] = _destino
