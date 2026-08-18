# -*- coding: utf-8 -*-
"""Idioma do usuario: detecta e traduz (pt-BR · en · es · zh).

Duas coisas diferentes, e o codigo separa as duas:

  1. a INTERFACE muda de idioma (rotulos, dicas, mensagens de erro);
  2. o MODELO passa a responder no idioma do usuario — por instrucao no system
     prompt, nao por traducao automatica do texto dele. Traduzir a resposta de um
     modelo com uma tabela daria texto quebrado; pedir que ele escreva no idioma
     certo e mais honesto e funciona melhor.

A deteccao e por sinal, nao por chute: ideograma CJK, palavra funcional e letra
acentuada tipica. Se o sinal for fraco, mantem o idioma anterior — trocar a
interface no meio da conversa por causa de um "ok" seria pior que nao trocar.
"""
from __future__ import annotations

import re

IDIOMAS = {
    "pt": {"nome": "português (Brasil)", "modelo": "português do Brasil", "flag": "BR"},
    "en": {"nome": "English", "modelo": "English", "flag": "EN"},
    "es": {"nome": "español", "modelo": "español", "flag": "ES"},
    "zh": {"nome": "中文", "modelo": "中文（简体）", "flag": "ZH"},
}
PADRAO = "pt"

_CJK = re.compile(r"[一-鿿㐀-䶿]")
_MARCAS = {
    "pt": [r"\bvoc[eê]\b", r"\bn[ãa]o\b", r"\best[áa]\b", r"\barquivo\b", r"\bcriar?\b",
           r"\bfa[çc]a\b", r"\bteste\b", r"\bpasta\b", r"\bcom\b", r"\bpara\b",
           r"\bç\B|ção\b|ções\b", r"\bmuito\b", r"\bagora\b", r"\bpor\s*favor\b"],
    "es": [r"\bel\b", r"\bla\b", r"\blos\b", r"\bque\b", r"\barchivo\b", r"\bcrear\b",
           r"\bhaz\b", r"\bhacer\b", r"\bprueba\b", r"\bcarpeta\b", r"\bpor\s*favor\b",
           r"ñ", r"¿", r"¡", r"\bahora\b", r"\bfunci[óo]n\b"],
    "en": [r"\bthe\b", r"\bfile\b", r"\bcreate\b", r"\bplease\b", r"\bfunction\b",
           r"\btest\b", r"\bfolder\b", r"\bmake\b", r"\brun\b", r"\bwith\b",
           r"\band\b", r"\bfix\b", r"\bnow\b"],
}
# palavras que existem nos dois e nao servem de prova
_AMBIGUAS = {r"\bteste\b": ("pt",), r"\btest\b": ("en",)}


def detectar(texto: str, anterior: str = PADRAO) -> tuple[str, float]:
    """Devolve (idioma, confianca 0..1). Sinal fraco mantem o anterior."""
    t = (texto or "").strip()
    if not t:
        return anterior, 0.0
    if _CJK.search(t):
        n = len(_CJK.findall(t))
        return "zh", min(1.0, 0.5 + n / 20)

    baixo = t.lower()
    pontos = {}
    for idioma, padroes in _MARCAS.items():
        pontos[idioma] = sum(1 for p in padroes if re.search(p, baixo))
    melhor = max(pontos, key=lambda k: pontos[k])
    total = sum(pontos.values())
    if total == 0 or pontos[melhor] == 0:
        return anterior, 0.0
    # empate tecnico entre dois idiomas: nao troca
    segundos = sorted(pontos.values(), reverse=True)
    if len(segundos) > 1 and segundos[0] == segundos[1]:
        return anterior, 0.2
    confianca = pontos[melhor] / max(3, total)
    if confianca < 0.34 or pontos[melhor] < 2:
        return anterior, confianca
    return melhor, min(1.0, confianca)


# ---------------------------------------------------------------- traducoes
T = {
    "app.sub": {
        "pt": "assistente de código. focado. rápido. curioso.",
        "en": "coding assistant. focused. fast. curious.",
        "es": "asistente de código. enfocado. rápido. curioso.",
        "zh": "编程助手。专注。快速。好奇。"},
    "input.placeholder": {
        "pt": "Digite qualquer coisa e veja a IA agir... ou / para comandos",
        "en": "Type anything and watch the AI work... or / for commands",
        "es": "Escribe algo y mira a la IA trabajar... o / para comandos",
        "zh": "输入任何内容，看 AI 工作… 或输入 / 查看命令"},
    "hint.commands": {"pt": "comandos", "en": "commands", "es": "comandos", "zh": "命令"},
    "hint.clear": {"pt": "limpar", "en": "clear", "es": "limpiar", "zh": "清空"},
    "hint.plan": {
        "pt": "no PLANO responda <b>sim</b> p/ implementar",
        "en": "in PLAN reply <b>yes</b> to implement",
        "es": "en PLAN responde <b>sí</b> para implementar",
        "zh": "在 计划 模式回复 <b>是</b> 开始实现"},
    "mode.plan": {"pt": "PLANEJAMENTO", "en": "PLANNING", "es": "PLANIFICACIÓN", "zh": "计划"},
    "mode.full": {"pt": "FULL ACESSO", "en": "FULL ACCESS", "es": "ACCESO TOTAL", "zh": "完全访问"},
    "mode.perm": {"pt": "PEDIR PERMISSÃO", "en": "ASK PERMISSION", "es": "PEDIR PERMISO", "zh": "请求许可"},
    "label.type": {"pt": "Tipo:", "en": "Type:", "es": "Tipo:", "zh": "类型："},
    "label.mode": {"pt": "Modo:", "en": "Mode:", "es": "Modo:", "zh": "模式："},
    "label.perms": {"pt": "Permissões:", "en": "Permissions:", "es": "Permisos:", "zh": "权限："},
    "label.desc": {"pt": "Descrição:", "en": "Description:", "es": "Descripción:", "zh": "描述："},
    "label.agent": {"pt": "agente de código", "en": "coding agent",
                    "es": "agente de código", "zh": "编程智能体"},
    "label.model": {"pt": "modelo", "en": "model", "es": "modelo", "zh": "模型"},
    "label.tokens": {"pt": "tokens", "en": "tokens", "es": "tokens", "zh": "词元"},
    "label.workspace": {"pt": "pasta", "en": "workspace", "es": "carpeta", "zh": "工作区"},
    "sandbox.on": {
        "pt": "SANDBOX — o agente trabalha numa cópia em works/",
        "en": "SANDBOX — the agent works on a copy in works/",
        "es": "SANDBOX — el agente trabaja en una copia en works/",
        "zh": "沙盒 — 智能体在 works/ 的副本中工作"},
    "sandbox.off": {
        "pt": "DIRETO — o agente escreve na pasta de verdade",
        "en": "DIRECT — the agent writes to the real folder",
        "es": "DIRECTO — el agente escribe en la carpeta real",
        "zh": "直接模式 — 智能体写入真实文件夹"},
    "live.on": {"pt": "AO VIVO", "en": "LIVE", "es": "EN VIVO", "zh": "实时"},
    "live.off": {"pt": "DEMO (sem servidor)", "en": "DEMO (no server)",
                 "es": "DEMO (sin servidor)", "zh": "演示（无服务器）"},
    "err.server": {
        "pt": "não consegui falar com o servidor",
        "en": "could not reach the server",
        "es": "no pude comunicarme con el servidor",
        "zh": "无法连接到服务器"},
    "msg.thinking": {"pt": "pensando", "en": "thinking", "es": "pensando", "zh": "思考中"},
    "msg.plan": {"pt": "plano", "en": "plan", "es": "plan", "zh": "计划"},
    "msg.done": {"pt": "Pronto", "en": "Done", "es": "Listo", "zh": "完成"},
    "plano.nada_feito": {
        "pt": "⚠ Nada foi escrito: estamos em PLANEJAMENTO e {n} ação(ões) foram bloqueadas. "
              "O modelo pode dizer que criou — não criou.",
        "en": "⚠ Nothing was written: we are in PLANNING and {n} action(s) were blocked. "
              "The model may claim it created files — it did not.",
        "es": "⚠ No se escribió nada: estamos en PLANIFICACIÓN y {n} acción(es) fueron bloqueadas. "
              "El modelo puede decir que creó archivos — no los creó.",
        "zh": "⚠ 未写入任何内容：当前为计划模式，已阻止 {n} 个操作。模型可能声称已创建文件——并没有。"},
    "plano.aprovar": {
        "pt": "O plano está bom? Responda **sim** que eu implemento.",
        "en": "Does the plan look good? Reply **yes** and I will implement it.",
        "es": "¿El plan está bien? Responde **sí** y lo implemento.",
        "zh": "计划可以吗？回复 **是** 我就开始实现。"},
    "perm.pergunta": {
        "pt": "posso?", "en": "may I?", "es": "¿puedo?", "zh": "可以吗？"},
    "status.mode": {"pt": "modo", "en": "mode", "es": "modo", "zh": "模式"},
    "footer.tip": {"pt": "Dica", "en": "Tip", "es": "Consejo", "zh": "提示"},
    "resumo.criei": {"pt": "criei", "en": "created", "es": "creé", "zh": "已创建"},
    "resumo.editei": {"pt": "editei", "en": "edited", "es": "edité", "zh": "已编辑"},
    "resumo.validei": {
        "pt": "Validei rodando a verificação ({n}x).",
        "en": "Verified by running the check ({n}x).",
        "es": "Validé ejecutando la verificación ({n}x).",
        "zh": "已通过运行验证确认（{n} 次）。"},
    "resumo.sem_prova": {
        "pt": "Ainda não rodei verificação nenhuma.",
        "en": "I have not run any verification yet.",
        "es": "Todavía no ejecuté ninguna verificación.",
        "zh": "尚未运行任何验证。"},
    "resumo.nada": {
        "pt": "Não alterei nenhum arquivo.",
        "en": "I did not change any file.",
        "es": "No modifiqué ningún archivo.",
        "zh": "没有修改任何文件。"},
}


def t(chave: str, idioma: str = PADRAO) -> str:
    linha = T.get(chave)
    if not linha:
        return chave
    return linha.get(idioma) or linha.get(PADRAO) or chave


def pacote(idioma: str = PADRAO) -> dict:
    """Todas as strings num dicionario — e o que a interface web consome."""
    return {k: t(k, idioma) for k in T}


def instrucao_modelo(idioma: str) -> str:
    """A frase que entra no system prompt para o modelo responder no idioma certo."""
    nome = IDIOMAS.get(idioma, IDIOMAS[PADRAO])["modelo"]
    return (f"Responda SEMPRE em {nome}. O usuario escreveu nesse idioma; "
            f"mantenha nomes de arquivo, comandos e codigo como estao.")
