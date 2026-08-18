# -*- coding: utf-8 -*-
"""Suite do requisito 97 — um teste por item que o Pai listou.

Regra herdada da V3 (ESPECIFICACAO-V3.md): quando um teste falha, a primeira
pergunta e "o codigo esta errado ou meu teste esta errado?". Fixture que nao
representa uso real vale menos que nada.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

# A suite nao pode depender do que esta rodando NESTA maquina. Sem isto, um
# llama-server qualquer na porta 8099 decidiria se o teste de /model passa — e
# teste que muda de veredito conforme o ambiente nao prova nada. A auditoria
# cobra que producao continue com a gestao de motor LIGADA.
os.environ["GATINHO_MOTOR"] = "off"


@pytest.fixture()
def ctx(tmp_path, monkeypatch):
    """Contexto isolado: config, sessoes e skills fora das pastas reais do Pai."""
    monkeypatch.setenv("GATINHO_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("GATINHO_DATA_HOME", str(tmp_path / "dados"))
    import importlib
    from gatinho import config as cfg, sessao as ses
    importlib.reload(cfg)
    importlib.reload(ses)
    from gatinho import handlers  # noqa: F401  (registra os comandos)
    from gatinho.estado import Contexto
    from gatinho.skills import Skills
    c = Contexto(projeto=tmp_path / "proj", skills=Skills(fontes=[]))
    (tmp_path / "proj").mkdir(exist_ok=True)
    return c


def roda(ctx, entrada):
    from gatinho.comandos import resolver
    cmd, args = resolver(entrada)
    assert cmd is not None, f"comando nao encontrado: {entrada}"
    return cmd.handler(ctx, args)


# ============================================================ parser e router
def test_parser_de_comandos(ctx):
    from gatinho.comandos import resolver
    cmd, args = resolver("/temperature 0.3")
    assert cmd.name == "temperature" and args == ["0.3"]
    assert resolver("texto normal") == (None, [])
    assert resolver("/naoexiste")[0] is None


def test_todos_os_comandos_tem_contrato_completo(ctx):
    from gatinho.comandos import REGISTRO
    for c in REGISTRO.values():
        assert c.name and c.description and callable(c.handler) and c.usage and c.category


def test_autocomplete(ctx):
    from gatinho.comandos import sugestoes
    v = [s["valor"] for s in sugestoes("/mo")]
    assert {"/model", "/models", "/mode"} <= set(v)
    subs = [s["valor"] for s in sugestoes("/session ")]
    assert "/session new" in subs and "/session resume" in subs
    assert sugestoes("oi") == []


def test_aliases(ctx):
    from gatinho.comandos import resolver
    for alias, destino in (("/temp 0.3", "temperature"), ("/quit", "exit"),
                           ("/sess", "session"), ("/ctx", "context")):
        assert resolver(alias)[0].name == destino


# ==================================================================== modelos
def test_modelos_e_troca(ctx):
    r = roda(ctx, "/models")
    assert any("deltacoder-9b" in l for l in r.linhas)
    r = roda(ctx, "/model qwen35-9b-oficial")
    assert r.ok and ctx.modelo() == "qwen35-9b-oficial"
    r = roda(ctx, "/model nao-existe-xyz")
    assert r.erro and ctx.modelo() == "qwen35-9b-oficial"


def test_model_sem_argumento_abre_menu(ctx):
    r = roda(ctx, "/model")
    assert r.escolhas and any(e["ativo"] for e in r.escolhas)


def test_provider_nao_vaza_chave(ctx):
    r = roda(ctx, "/provider")
    texto = json.dumps(r.escolhas)
    assert "sk-" not in texto and "API_KEY=" not in texto
    r = roda(ctx, "/provider openrouter")
    assert r.erro and "OPENROUTER_API_KEY" in r.texto     # diz o NOME da variavel, nao o valor


def test_capabilities_barram_parametro_incompativel(ctx):
    roda(ctx, "/model deltacoder-9b")                      # nao suporta effort
    r = roda(ctx, "/effort high")
    assert r.erro and "nao suporta" in r.texto
    assert ctx.config.get("effort") == "medium"            # nao fingiu que aplicou
    roda(ctx, "/model qwen35-9b-oficial")                  # suporta
    r = roda(ctx, "/effort high")
    assert r.ok and ctx.config.get("effort") == "high"


# =================================================================== geracao
def test_temperature_top_p_max_output(ctx):
    assert roda(ctx, "/temperature 0.3").ok and ctx.config.get("temperature") == 0.3
    assert roda(ctx, "/temperature 9").erro
    assert roda(ctx, "/top-p 0.9").ok and ctx.config.get("top_p") == 0.9
    assert roda(ctx, "/max-output 2048").ok and ctx.config.get("max_output") == 2048
    assert roda(ctx, "/max-output 999999").erro            # acima do maximo do modelo


def test_context_respeita_o_maximo_do_modelo(ctx):
    roda(ctx, "/model glm46v-flash")                        # max 16384
    assert roda(ctx, "/context 8k").ok and ctx.janela() == 8192
    r = roda(ctx, "/context 128k")
    assert r.erro and ctx.janela() == 8192
    assert roda(ctx, "/context 16384").ok


def test_context_nao_e_max_output(ctx):
    roda(ctx, "/context 16k")
    roda(ctx, "/max-output 4096")
    assert ctx.janela() == 16384 and ctx.config.get("max_output") == 4096


# ===================================================================== modos
def test_politica_e_fase_sao_coisas_diferentes(ctx):
    """Contrato revisado em 2026-08-17.

    O briefing pedia 2 modos (planejamento/supervisão) e a interface que o Pai
    aprovou tem 3 botões (PLAN/FULL/PERM). Eram duas coisas empilhadas na mesma
    variável: POLÍTICA (o que o agente PODE fazer) e FASE (onde ele está agora).
    """
    from gatinho.estado import POLITICAS, FASES
    assert set(POLITICAS) == {"plan", "full", "perm"}
    assert set(FASES) == {"plan", "supervise"}
    assert roda(ctx, "/mode perm").ok and ctx.nome_modo() == "PEDIR PERMISSÃO"
    assert roda(ctx, "/mode plan").ok and ctx.so_leitura()
    assert roda(ctx, "/mode full").ok and not ctx.so_leitura()
    assert roda(ctx, "/mode turbo").erro


def test_politica_plan_impede_escrita(ctx):
    """CASO REAL: os botões mudavam só o rótulo — o agente escrevia igual."""
    from gatinho.runtime import Runtime
    roda(ctx, "/mode plan")
    rt = Runtime(ctx)
    rt.executar_ferramentas([{"nome": "write", "args": {"path": "x.py", "content": "x=1\n"}}])
    assert not (ctx.pasta_trabalho() / "x.py").exists(), "escreveu no modo PLANEJAMENTO"
    assert ctx.metricas.tool_calls_blocked >= 1
    roda(ctx, "/mode full")
    rt2 = Runtime(ctx)
    rt2.executar_ferramentas([{"nome": "write", "args": {"path": "x.py", "content": "x=1\n"}}])
    assert (ctx.pasta_trabalho() / "x.py").exists(), "FULL deveria deixar escrever"


def test_politica_perm_pergunta_antes_de_escrever(ctx):
    from gatinho.runtime import Runtime
    roda(ctx, "/mode perm")
    perguntas = []
    ctx.pedir_permissao = lambda f, alvo: (perguntas.append((f, alvo)), False)[1]
    Runtime(ctx).executar_ferramentas(
        [{"nome": "write", "args": {"path": "y.py", "content": "y=1\n"}}])
    assert perguntas, "modo PEDIR PERMISSÃO não perguntou nada"
    assert not (ctx.pasta_trabalho() / "y.py").exists(), "escreveu mesmo com resposta negativa"
    ctx.pedir_permissao = lambda f, alvo: True
    Runtime(ctx).executar_ferramentas(
        [{"nome": "write", "args": {"path": "y.py", "content": "y=1\n"}}])
    assert (ctx.pasta_trabalho() / "y.py").exists(), "não escreveu mesmo aprovado"


def test_leitura_nunca_pede_permissao(ctx):
    from gatinho.runtime import Runtime
    (ctx.pasta_trabalho() / "leia.py").write_text("x=1\n", encoding="utf-8")
    roda(ctx, "/mode perm")
    ctx.pedir_permissao = lambda f, alvo: False
    r = Runtime(ctx).executar_ferramentas([{"nome": "read", "args": {"path": "leia.py"}}])
    assert not r[0]["erro"], "ler foi bloqueado — leitura não precisa de permissão"


# ================================================================== roteador
def test_router_threshold_configuravel_com_padrao_3000(ctx):
    assert ctx.config.get("router.threshold") == 3000
    assert roda(ctx, "/router threshold 3500").ok
    assert ctx.config.get("router.threshold") == 3500


def test_router_v31_contexto_pequeno_SEM_pressa_fica_no_mast(ctx):
    """V3.1: o A/B mostrou que 'empate em sucesso' nao autoriza trocar pro fast.

    Em qualidade o mast ganhou ate nas rapidas (4.50 x 4.20).
    """
    from gatinho.roteador import decidir
    (ctx.projeto / "a.py").write_text("x = 1\n")
    d = decidir(ctx.projeto, "arruma isso", limiar=3000)
    assert d.selected_harness == "mast-agent"
    assert d.context_estimate < 3000 and "padrao V3.1" in d.router_reason


def test_router_v31_fast_so_com_pressa_e_tarefa_curta(ctx):
    from gatinho.roteador import decidir
    (ctx.projeto / "a.py").write_text("x = 1\n")
    d = decidir(ctx.projeto, "arruma rapido esse typo, e so uma linha", limiar=3000)
    assert d.selected_harness == "fast-coder" and "latencia" in d.router_reason
    # pressa NAO vence sinal de investigacao
    d2 = decidir(ctx.projeto, "rapido, investiga a causa raiz disso", limiar=3000)
    assert d2.selected_harness == "mast-agent"


def test_router_v31_padrao_do_gatinho_e_mast(ctx):
    assert ctx.config.get("harness") == "mast-agent"


def test_router_v3_contexto_grande_vai_pro_mast(ctx):
    from gatinho.roteador import decidir
    (ctx.projeto / "grande.py").write_text("def f():\n    return 1\n" * 400)
    d = decidir(ctx.projeto, "refatora", limiar=3000)
    assert d.selected_harness == "mast-agent" and d.context_estimate > 3000


def test_router_registra_os_quatro_campos(ctx):
    from gatinho.roteador import decidir
    d = decidir(ctx.projeto, "faz").dic()
    for campo in ("context_estimate", "router_threshold", "selected_harness", "router_reason"):
        assert campo in d and d[campo] not in (None, "")


def test_harness_manual_vence_o_roteador(ctx):
    from gatinho.roteador import decidir
    (ctx.projeto / "grande.py").write_text("x = 1\n" * 5000)
    d = decidir(ctx.projeto, "refatora", limiar=3000, forcar="fast-coder")
    assert d.selected_harness == "fast-coder" and d.forcado
    assert roda(ctx, "/harness mast").ok and ctx.harness_pedido() == "mast-agent"
    assert roda(ctx, "/harness auto").ok


# =================================================================== sessoes
def test_sessao_persiste_e_retoma(ctx):
    ctx.sessao.mensagem("user", "consertar o roteador")
    ctx.sessao.tocar_arquivo("src/router.py", "editado")
    sid = ctx.sessao.session_id
    ctx.sessao.salvar()
    from gatinho.sessao import Sessao
    s2 = Sessao.carregar(sid)
    assert s2 and s2.files["src/router.py"] == "editado"
    assert s2.objetivo.startswith("consertar")
    assert s2.nome == "consertar-roteador"


def test_resume_por_comando(ctx):
    ctx.sessao.mensagem("user", "primeira tarefa")
    sid = ctx.sessao.session_id
    ctx.sessao.salvar()
    roda(ctx, "/new")
    assert ctx.sessao.session_id != sid
    r = roda(ctx, f"/resume {sid}")
    assert r.ok and ctx.sessao.session_id == sid


def test_rename_e_lista(ctx):
    ctx.sessao.mensagem("user", "tarefa")
    assert roda(ctx, "/rename benchmark-v3").ok
    r = roda(ctx, "/sessions")
    assert any(e["rotulo"] == "benchmark-v3" for e in r.escolhas)


def test_delete_session_pede_confirmacao(ctx):
    ctx.sessao.salvar()
    r = roda(ctx, "/delete-session")
    assert r.acao == "confirmar-apagar" and "nao tem volta" in r.texto


def test_arquivo_editado_nao_regride_para_lido(ctx):
    ctx.sessao.tocar_arquivo("a.py", "criado")
    ctx.sessao.tocar_arquivo("a.py", "lido")
    assert ctx.sessao.files["a.py"] == "criado"


def test_export_markdown_e_json(ctx, tmp_path):
    ctx.sessao.mensagem("user", "oi")
    ctx.sessao.mensagem("assistant", "ola")
    for fmt in ("markdown", "json"):
        r = roda(ctx, f"/export {fmt}")
        assert r.ok
        destino = Path(r.linhas[0].split(": ", 1)[1])
        assert destino.exists() and destino.stat().st_size > 10


# =============================================================== compactacao
def test_compactacao_preserva_o_essencial(ctx):
    s = ctx.sessao
    s.mensagem("user", "objetivo original da tarefa")
    s.tocar_arquivo("src/router.py", "editado")
    s.decidir("usar mast-agent")
    for i in range(30):
        s.mensagem("assistant", f"mensagem intermediaria {i}")
    antes, depois = s.compactar(manter=8)
    assert depois < antes and s.compaction_count == 1
    assert len(s.messages) <= 10
    # o teste tem que olhar a MENSAGEM DE RESUMO, nao o corpo inteiro: a primeira
    # mensagem do usuario e preservada como cabeca, entao procurar no corpo todo
    # passaria mesmo se o resumo nao guardasse nada. (defeito pego pela mutacao)
    resumos = [m for m in s.messages if m.get("compactado")]
    assert len(resumos) == 1, "a compactacao nao deixou mensagem de resumo"
    resumo = str(resumos[0]["content"])
    assert "objetivo original" in resumo, "o resumo perdeu o objetivo"
    assert "src/router.py" in resumo, "o resumo perdeu os arquivos"
    assert "mast-agent" in resumo, "o resumo perdeu as decisoes"
    assert "mensagem intermediaria 5" not in resumo, "o resumo nao compactou nada"


def test_compact_por_comando_reporta_numeros(ctx):
    for i in range(30):
        ctx.sessao.mensagem("assistant", "x" * 200)
    r = roda(ctx, "/compact")
    assert r.ok and "→" in r.texto
    assert ctx.metricas.context_before > ctx.metricas.context_after


# =============================================== tools: emitidas/exec/blocked
def test_tools_por_step_limita_e_contabiliza(ctx):
    from gatinho.runtime import Runtime
    (ctx.projeto / "a.py").write_text("x = 1\n")
    ctx.config.set("tools.max_per_step", 2)
    rt = Runtime(ctx)
    chamadas = [{"nome": "read", "args": {"path": "a.py"}} for _ in range(7)]
    rt.executar_ferramentas(chamadas)
    m = ctx.metricas
    assert m.tool_calls_emitted == 7
    assert m.tool_calls_executed == 2
    assert m.tool_calls_blocked == 5
    assert m.motivos_bloqueio.get("limite por passo") == 5


def test_tools_per_step_comando(ctx):
    assert roda(ctx, "/tools-per-step 3").ok
    assert ctx.config.get("tools.max_per_step") == 3
    assert roda(ctx, "/tools-per-step 0").erro


def test_metricas_nunca_chamam_tudo_de_tool_calls(ctx):
    campos = ctx.metricas.dic()
    assert {"tool_calls_emitted", "tool_calls_executed", "tool_calls_blocked"} <= set(campos)
    assert "tool_calls" not in campos


def test_permissao_deny_bloqueia_ferramenta(ctx):
    from gatinho.runtime import Runtime
    ctx.config.set("permissions.escrita", "deny")
    rt = Runtime(ctx)
    rt.executar_ferramentas([{"nome": "write", "args": {"path": "n.py", "content": "x=1\n"}}])
    assert ctx.metricas.tool_calls_blocked == 1
    assert not (ctx.projeto / "n.py").exists()


def test_tools_e_tool_listam(ctx):
    assert "read" in roda(ctx, "/tools").linhas
    r = roda(ctx, "/tool read")
    assert not r.erro and "path" in r.texto
    assert roda(ctx, "/tool inexistente").erro


# ==================================================================== skills
def test_skills_listar_ligar_desligar(ctx):
    r = roda(ctx, "/skills")
    assert any("pytest" in l for l in r.linhas)
    assert roda(ctx, "/skills disable pytest").ok
    assert ctx.skills.get("pytest").ativa is False
    assert roda(ctx, "/skills enable pytest").ok
    assert roda(ctx, "/skills info pytest").texto
    assert roda(ctx, "/skills reload").ok


def test_skill_automatica_por_gatilho(ctx):
    assert "pytest" in ctx.skills.sugerir("roda os testes e conserta o que falhar")
    assert "debug" in ctx.skills.sugerir("tem um bug estranho aqui")
    assert ctx.skills.sugerir("escreva um poema") == []


# =============================================== planejamento e supervisao
def test_planejamento_escolhe_harness_e_registra(ctx):
    from gatinho.runtime import Runtime
    (ctx.projeto / "a.py").write_text("x = 1\n")
    rt = Runtime(ctx)
    plano = rt.planejar("conserta o bug do a.py")
    assert plano["selected_harness"] in ("fast-coder", "mast-agent")
    assert ctx.ultima_decisao_roteador["router_reason"]
    assert ctx.fase == "plan"
    assert any(e["texto"] == "Plano pronto" for e in ctx.eventos)


def test_supervisao_mostra_acao_e_nao_raciocinio(ctx):
    from gatinho.runtime import Runtime
    (ctx.projeto / "a.py").write_text("x = 1\n")
    rt = Runtime(ctx)
    rt.executar_ferramentas([{"nome": "read", "args": {"path": "a.py"}}])
    ev = ctx.eventos[-1]
    assert ev["texto"].startswith("Lendo")
    assert "pensando" not in ev["texto"].lower()


# ====================================== fim de tarefa: prova e encerramento
def test_encerramento_vazio_e_barrado(ctx):
    from gatinho.runtime import Runtime
    rt = Runtime(ctx)
    pode, msg = rt.pode_encerrar(houve_escrita=False)
    assert not pode and "nenhum arquivo" in msg
    assert ctx.metricas.encerramentos_vazios_barrados == 1


def test_nao_aceita_pronto_sem_prova(ctx):
    from gatinho.runtime import Runtime
    rt = Runtime(ctx)
    ctx.sessao.tocar_arquivo("a.py", "editado")
    pode, msg = rt.pode_encerrar(houve_escrita=True)
    assert not pode and "provou" in msg
    ctx.metricas.provas_executadas = 1
    pode, _ = rt.pode_encerrar(houve_escrita=True)
    assert pode


# ================================================================== estado
def test_status_traz_o_que_nao_fica_na_tela(ctx):
    t = roda(ctx, "/status").texto
    for pedaco in ("Modelo:", "Provider:", "Contexto:", "Modo:", "Harness solicitado:",
                   "Effort:", "Temperature:", "Top-p:", "Max output:", "Sessao:", "Duracao:"):
        assert pedaco in t


def test_metrics_e_context_info(ctx):
    ctx.metricas.marcar_contexto(5000)
    assert "Tools emitidas" in roda(ctx, "/metrics").texto
    t = roda(ctx, "/context-info").texto
    assert "Pico" in t and "Compactacoes" in t


def test_runs_e_inspect(ctx):
    from gatinho.runtime import Runtime
    rt = Runtime(ctx)
    r = rt.abrir_run()
    rt.fechar_run(r, "sucesso", testes="18 passaram")
    assert r["id"] in roda(ctx, "/runs").texto
    t = roda(ctx, f"/inspect {r['id']}").texto
    assert "tools emitidas" in t and "tools bloqueadas" in t and "18 passaram" in t
    assert roda(ctx, "/inspect run_zzzz").erro


def test_verbose_niveis(ctx):
    assert roda(ctx, "/verbose quiet").ok and ctx.config.get("verbose") == "quiet"
    assert roda(ctx, "/verbose xpto").erro


# =================================================================== config
def test_config_hierarquia_o_mais_especifico_vence(ctx, tmp_path):
    from gatinho.config import Config
    glob = tmp_path / "cfg" / "config.json"
    glob.parent.mkdir(parents=True, exist_ok=True)
    glob.write_text(json.dumps({"temperature": 0.9, "model": "do-global"}))
    proj = ctx.projeto / ".gatinho" / "config.json"
    proj.parent.mkdir(parents=True, exist_ok=True)
    proj.write_text(json.dumps({"model": "do-projeto"}))
    import importlib
    from gatinho import config as cfg
    importlib.reload(cfg)
    c = cfg.Config(ctx.projeto, overrides={"harness": "mast-agent"})
    assert c.get("temperature") == 0.9 and c.origem("temperature") == "global"
    assert c.get("model") == "do-projeto" and c.origem("model") == "projeto"
    assert c.get("harness") == "mast-agent" and c.origem("harness") == "sessao"
    assert c.get("top_p") == 0.95 and c.origem("top_p") == "padrao"


def test_config_set_e_save(ctx):
    assert roda(ctx, "/config set temperature 0.4").ok
    assert ctx.config.get("temperature") == 0.4
    r = roda(ctx, "/config save global")
    assert r.ok and Path(r.linhas[0].split(": ", 1)[1]).exists()


def test_permissions(ctx):
    assert "shell" in roda(ctx, "/permissions").texto
    assert roda(ctx, "/permissions shell allow").ok
    assert ctx.config.get("permissions.shell") == "allow"
    assert roda(ctx, "/permissions shell talvez").erro


def test_approve_e_deny(ctx):
    from gatinho.estado import Pendencia
    assert roda(ctx, "/approve").erro
    ctx.pendencia = Pendencia("bash", {"command": "ls"})
    assert roda(ctx, "/approve").ok and ctx.pendencia.resolvida == "approve"
    ctx.pendencia = Pendencia("bash", {"command": "ls"})
    assert roda(ctx, "/deny").ok and ctx.pendencia.resolvida == "deny"


def test_auto_approve_avisa_que_esta_ligado(ctx):
    r = roda(ctx, "/auto-approve on")
    assert r.ok and "LIGADA" in r.texto


# ======================================================= execucao e controle
def test_run_e_tests(ctx):
    (ctx.projeto / "test_x.py").write_text("def test_ok():\n    assert True\n")
    r = roda(ctx, "/run echo oi")
    assert r.ok and "oi" in r.texto
    from gatinho.runtime import detectar_testes
    assert "pytest" in detectar_testes(ctx.projeto)


def test_run_com_comando_que_falha_nao_explode(ctx):
    r = roda(ctx, "/run comando-que-nao-existe-xyz")
    assert r.erro and r.linhas


def test_stop_pause_continue(ctx):
    assert "Nada rodando" in roda(ctx, "/stop").texto
    ctx.executando = True
    assert roda(ctx, "/stop").ok and ctx.parar
    assert roda(ctx, "/pause").ok and ctx.pausado
    assert roda(ctx, "/continue").ok and not ctx.pausado


def test_undo_e_rollback(ctx):
    from gatinho.runtime import Runtime, desfazer_ultima
    alvo = ctx.projeto / "m.py"
    alvo.write_text("original = 1\n")
    rt = Runtime(ctx)
    rt.executar_ferramentas([{"nome": "write", "args": {"path": "m.py", "content": "novo = 2\n"}}])
    assert alvo.read_text() == "novo = 2\n"
    ok, msg = desfazer_ultima(ctx)
    assert ok and alvo.read_text() == "original = 1\n"
    r = roda(ctx, "/rollback")
    assert r.erro          # nada mais para desfazer


def test_files_e_history(ctx):
    ctx.sessao.tocar_arquivo("src/a.py", "lido")
    assert "src/a.py" in roda(ctx, "/files").texto
    ctx.sessao.mensagem("user", "oi")
    assert "oi" in roda(ctx, "/history").texto


# ==================================================================== erros
def test_comando_inexistente_nao_derruba(ctx):
    from gatinho.comandos import resolver
    assert resolver("/xpto")[0] is None


def test_erro_de_modelo_vira_mensagem_humana(ctx):
    from gatinho.runtime import Runtime
    ctx.registro.provedores["local"].base_url = "http://127.0.0.1:9"   # porta morta
    rt = Runtime(ctx)
    with pytest.raises(RuntimeError) as e:
        rt.completar([{"role": "user", "content": "oi"}])
    assert "nao consegui falar com o modelo" in str(e.value).lower()


def test_help_e_about(ctx):
    assert "/model" in roda(ctx, "/help").texto
    assert "/temperature" in roda(ctx, "/help temperature").texto
    assert "Gatinho CLI" in roda(ctx, "/about").texto


def test_clear_nao_apaga_sessao(ctx):
    ctx.sessao.mensagem("user", "importante")
    r = roda(ctx, "/clear")
    assert r.acao == "limpar" and len(ctx.sessao.messages) == 1


def test_reset_explica_o_que_descarta(ctx):
    ctx.sessao.mensagem("user", "oi")
    r = roda(ctx, "/reset")
    assert r.acao == "confirmar-reset" and "descarta" in r.texto


def test_benchmark_fica_atras_do_comando(ctx):
    assert "harness-bench" in roda(ctx, "/benchmark list").texto
    assert roda(ctx, "/benchmark run xpto").erro


def test_guardas_nao_justificadas_continuam_fora(ctx):
    """Requisito 83: nao voltar com teto agressivo global nem corte 8/10."""
    sys.path.insert(0, "/home/julianshin/Documentos/automatização/harness-filho")
    from hbcore.politicas import FAST, MAST
    assert FAST.max_chamadas == 0 and MAST.max_chamadas == 0
    assert FAST.erros_na_janela == 0 and MAST.erros_na_janela == 0


# ============ regra virou mecanismo: health OK nao prova modelo certo ========

def test_runner_confere_o_modelo_servido_nao_so_o_health():
    """CASO REAL 2026-08-16: um llama-server manual ficou na porta 8099, os
    servidores do bench falharam com "couldn't bind" e o health do servidor
    ALHEIO respondeu OK. 29 execucoes rodaram contra o modelo errado e o pior
    modelo do catalogo "melhorou" de 1.00 para 5.00.
    """
    for runner in ("/home/julianshin/Documentos/benchmarks/harness-contexto/run_ctx.py",
                   "/home/julianshin/Documentos/benchmarks/harness-bench/run_harness.py"):
        txt = Path(runner).read_text(encoding="utf-8")
        assert "def porta_ocupada" in txt, f"{runner} nao checa porta ocupada"
        assert "def modelo_servido" in txt, f"{runner} nao confere o modelo servido"
        assert "gguf=gguf" in txt, f"{runner} nao passa o gguf esperado para o health"


def test_runner_tem_guarda_de_memoria_e_nao_deixa_servidor_orfao():
    """CASO REAL 2026-08-17: a sessao morreu por OOM no meio do A/B.

    Somaram-se 3 Chrome que eu abri para os decks + llama-server de 9B (~7 GB)
    numa maquina com 9 GB livres. Regra virou mecanismo nos dois runners.
    """
    for runner in ("/home/julianshin/Documentos/benchmarks/harness-contexto/run_ctx.py",
                   "/home/julianshin/Documentos/benchmarks/harness-bench/run_harness.py"):
        txt = Path(runner).read_text(encoding="utf-8")
        assert "def memoria_suficiente" in txt, f"{runner} sobe servidor sem checar RAM"
        assert "MemAvailable" in txt, f"{runner} nao le a memoria real do sistema"
        assert "atexit.register" in txt, f"{runner} pode deixar llama-server orfao"
        assert "[ABORTA]" in txt, f"{runner} nao aborta com mensagem clara"


# ==================================================== sandbox por sessao (2026-08-17)
def test_sandbox_e_o_padrao_e_isola_o_projeto(ctx, tmp_path, monkeypatch):
    """Modelo local erra — o padrao tem que ser a copia, nao o projeto do Pai."""
    from gatinho import sandbox as sb
    monkeypatch.setattr(sb, "WORKS", tmp_path / "works")
    assert ctx.modo_pasta == sb.MODO_SANDBOX
    ctx.garantir_work()
    trabalho = ctx.pasta_trabalho()
    assert trabalho != ctx.projeto, "o agente ia escrever no projeto de verdade"
    assert "works" in str(trabalho)
    assert (trabalho / ".gatinho-work.json").exists()


def test_cada_sessao_ganha_um_work_novo(ctx, tmp_path, monkeypatch):
    from gatinho import sandbox as sb
    monkeypatch.setattr(sb, "WORKS", tmp_path / "works")
    ctx.sessao.mensagem("user", "primeira tarefa")
    p1 = ctx.garantir_work().p
    roda(ctx, "/new")
    ctx.sessao.mensagem("user", "outra tarefa")
    p2 = ctx.garantir_work().p
    assert p1 != p2, "duas sessoes dividiram a mesma pasta"


def test_modo_direto_existe_mas_avisa(ctx, tmp_path, monkeypatch):
    from gatinho import sandbox as sb
    monkeypatch.setattr(sb, "WORKS", tmp_path / "works")
    r = roda(ctx, "/sandbox off")
    assert r.erro, "sair da sandbox tem que aparecer como aviso, nao como 'ok'"
    assert "MODO DIRETO" in r.texto
    assert ctx.pasta_trabalho() == ctx.projeto
    r = roda(ctx, "/sandbox on")
    assert r.ok and ctx.pasta_trabalho() != ctx.projeto


def test_semear_copia_codigo_e_ignora_lixo(ctx, tmp_path, monkeypatch):
    from gatinho import sandbox as sb
    monkeypatch.setattr(sb, "WORKS", tmp_path / "works")
    origem = tmp_path / "origem"
    (origem / "src").mkdir(parents=True)
    (origem / "src" / "a.py").write_text("x = 1\n")
    (origem / "README.md").write_text("doc\n")
    (origem / "node_modules").mkdir()
    (origem / "node_modules" / "lixo.js").write_text("x")
    (origem / "foto.bin").write_bytes(b"\x00" * 1000)
    w = sb.criar("sess1", "teste", origem)
    n, b_, _ = sb.semear(w, origem)
    assert (w.p / "src" / "a.py").exists() and (w.p / "README.md").exists()
    assert not (w.p / "node_modules").exists(), "copiou node_modules"
    assert not (w.p / "foto.bin").exists(), "copiou binario"
    assert n == 2


def test_apagar_work_recusa_caminho_de_fora(ctx, tmp_path, monkeypatch):
    from gatinho import sandbox as sb
    monkeypatch.setattr(sb, "WORKS", tmp_path / "works")
    (tmp_path / "works").mkdir()
    ok, msg = sb.apagar("../../etc")
    assert not ok and "recusado" in msg


# ==================================================== idiomas
def test_detecta_os_quatro_idiomas(ctx):
    from gatinho.i18n import detectar
    for txt, esperado in [("cria um arquivo de teste com pytest", "pt"),
                          ("create a file with a test function please", "en"),
                          ("crea un archivo de prueba por favor", "es"),
                          ("创建一个测试文件并运行", "zh")]:
        got, conf = detectar(txt)
        assert got == esperado, f"{txt!r} -> {got}, esperado {esperado}"
        assert conf > 0.3


def test_sinal_fraco_nao_troca_idioma(ctx):
    """"ok" nao pode virar a interface inteira de idioma."""
    from gatinho.i18n import detectar
    got, conf = detectar("ok", anterior="es")
    assert got == "es" and conf < 0.34


def test_todas_as_strings_existem_nos_quatro_idiomas(ctx):
    from gatinho.i18n import T, IDIOMAS
    for chave, linha in T.items():
        for idioma in IDIOMAS:
            assert linha.get(idioma), f"falta {idioma} em {chave}"


def test_modelo_recebe_instrucao_do_idioma(ctx):
    from gatinho.i18n import instrucao_modelo
    from gatinho.runtime import Runtime
    ctx.idioma = "es"
    msgs = Runtime(ctx).montar_mensagens("crea un archivo", [])
    assert "español" in msgs[0]["content"]
    assert "español" in instrucao_modelo("es")


def test_comando_idioma(ctx):
    assert roda(ctx, "/idioma en").ok and ctx.idioma == "en"
    assert roda(ctx, "/idioma klingon").erro
    assert roda(ctx, "/idioma").escolhas


def test_runtime_nasce_apontando_para_a_sandbox(ctx, tmp_path, monkeypatch):
    """CASO REAL 2026-08-17: o Runtime era criado antes da sandbox existir e
    capturava ctx.projeto — o terminal escrevia no projeto do Pai.
    """
    from gatinho import sandbox as sb
    from gatinho.runtime import Runtime
    monkeypatch.setattr(sb, "WORKS", tmp_path / "works")
    ctx.garantir_work()
    rt = Runtime(ctx)
    assert str(rt.cx.raiz) == str(ctx.pasta_trabalho())
    assert str(rt.cx.raiz) != str(ctx.projeto), "o runtime aponta para o projeto real"


def test_ordem_no_app_cria_sandbox_antes_do_runtime():
    """A ordem no trabalhar() e contrato: sandbox primeiro, Runtime depois."""
    src = (Path(__file__).parent.parent / "gatinho" / "app.py").read_text(encoding="utf-8")
    i_sandbox = src.index("garantir_work(semear_de=ctx.projeto)")
    i_runtime = src.index("rt = runtime.Runtime(ctx")
    assert i_sandbox < i_runtime, "o Runtime esta sendo criado antes da sandbox"


# ---------------------------------------------------------------- troca de modelo
def test_caminho_resolve_nome_pelado(ctx):
    """modelos.json guarda 'Qwen3.5-9B-Q4_1.gguf' — nome pelado nao identifica nada."""
    from gatinho import capacidades
    m = ctx.registro.get("deltacoder-9b")
    assert m and not Path(m.arquivo).is_absolute(), "fixture: o json guarda nome pelado"
    p = ctx.registro.caminho(m)
    assert p is None or (p.is_absolute() and p.parent == capacidades.MODELOS_DIR)


def test_model_diz_a_verdade_quando_nao_troca_processo(ctx):
    """Com a gestao de motor desligada o comando PRECISA dizer que nao trocou."""
    os.environ["GATINHO_MOTOR"] = "off"
    r = roda(ctx, "/model qwen35-9b-oficial")
    assert r.ok and ctx.modelo() == "qwen35-9b-oficial"
    assert any("nao foi trocado" in l or "desligada" in l for l in r.linhas), \
        "trocou o rotulo sem avisar que o processo continua o mesmo — e o defeito antigo"


def test_model_recusa_quando_o_gguf_nao_existe(ctx, tmp_path, monkeypatch):
    """Sem arquivo nao ha troca possivel: tem que dar erro, nunca 'ok'."""
    from gatinho import capacidades
    monkeypatch.setenv("GATINHO_MOTOR", "on")
    monkeypatch.setattr(capacidades, "MODELOS_DIR", tmp_path / "vazio")
    r = roda(ctx, "/model qwen35-9b-oficial")
    assert r.erro and "nao achei o .gguf" in " ".join(r.linhas)


def test_motor_nao_derruba_servidor_dos_outros(monkeypatch):
    """Processo que nao subimos nao e nosso para matar."""
    from gatinho import motor
    monkeypatch.setattr(motor, "_PID", None)
    monkeypatch.setattr(motor, "servindo", lambda: "modelo-de-terceiro.gguf")
    monkeypatch.delenv("GATINHO_MODELO_PID", raising=False)
    ok, msg = motor.derrubar()
    assert not ok and "nao vou derrubar processo dos outros" in msg


def test_motor_exige_o_arquivo_certo_e_nao_so_health(monkeypatch, tmp_path):
    """Health 'ok' nao prova nada: se servir outro arquivo, subir() tem que falhar."""
    from gatinho import motor
    gguf = tmp_path / "quero-este.gguf"; gguf.write_bytes(b"x")
    monkeypatch.setattr(motor, "BIN", Path("/bin/sleep"))
    monkeypatch.setattr(motor, "servindo", lambda: "outro-completamente-diferente.gguf")
    ok, msg = motor.subir(gguf, espera=3)
    assert not ok and "nao" in msg.lower() and "outro-completamente-diferente" in msg


def test_troca_que_falha_nao_deixa_a_config_mentindo(ctx, tmp_path, monkeypatch):
    """Se o processo nao trocou, o estado tem que continuar no modelo servido.

    Defeito medido em 2026-08-18: a troca falhou ("nao vou derrubar processo dos
    outros") e mesmo assim /api/estado passou a informar o modelo NOVO. A tela dizia
    um modelo, o motor servia outro — que e o defeito original com outra roupa.
    """
    from gatinho import capacidades
    monkeypatch.setenv("GATINHO_MOTOR", "on")
    monkeypatch.setattr(capacidades, "MODELOS_DIR", tmp_path / "vazio")
    antes = ctx.modelo()
    r = roda(ctx, "/model qwen35-9b-oficial")
    assert r.erro
    assert ctx.modelo() == antes, "config ficou apontando para um modelo que nao subiu"
