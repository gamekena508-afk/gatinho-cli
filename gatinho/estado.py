# -*- coding: utf-8 -*-
"""Contexto da aplicacao — o que os handlers recebem.

A UI nao guarda estado de negocio e o negocio nao sabe desenhar (requisito 94).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import i18n, sandbox
from .capacidades import Registro
from .config import Config, tamanho_contexto
from .metricas import Metricas
from .sessao import Sessao
from .skills import Skills

# POLITICA — o que o usuario escolhe nos botoes; muda o que o agente PODE fazer.
POLITICAS = {"plan":  "PLANEJAMENTO",
             "full":  "FULL ACESSO",
             "perm":  "PEDIR PERMISSÃO"}
# FASE — onde o runtime esta agora; muda so o que a tela mostra.
FASES = {"plan": "PLANEJAMENTO", "supervise": "SUPERVISÃO"}
MODOS = POLITICAS          # compatibilidade com quem ja importava MODOS
VERBOSIDADES = ("quiet", "normal", "verbose", "debug")


@dataclass
class Pendencia:
    """Acao esperando /approve ou /deny (requisitos 44, 45)."""
    ferramenta: str
    args: dict
    motivo: str = ""
    resolvida: str = ""     # "" | approve | deny


@dataclass
class Contexto:
    projeto: Path = field(default_factory=Path.cwd)
    versao: str = "3.0.0"
    config: Config = None
    registro: Registro = None
    skills: Skills = None
    sessao: Sessao = None
    metricas: Metricas = field(default_factory=Metricas)
    # estado de execucao
    modo: str = "full"          # POLITICA escolhida pelo usuario
    fase: str = "plan"          # fase do turno: plan -> supervise
    idioma: str = i18n.PADRAO
    work: object = None                 # sandbox.Work — a pasta desta sessao
    modo_pasta: str = sandbox.MODO_SANDBOX
    executando: bool = False
    pausado: bool = False
    parar: bool = False
    pendencia: Pendencia | None = None
    # callback que a UI instala para perguntar ao usuario (web ou terminal).
    # Recebe (ferramenta, args) e devolve True/False. None = ninguem instalou.
    pedir_permissao: object = None
    aguardando_plano: bool = False
    ultima_decisao_roteador: dict = field(default_factory=dict)
    runs: list = field(default_factory=list)
    logs: list = field(default_factory=list)
    eventos: list = field(default_factory=list)     # o que a UI mostra em SUPERVISÃO

    def __post_init__(self):
        self.projeto = Path(self.projeto)
        if self.config is None:
            self.config = Config(self.projeto)
        if self.registro is None:
            self.registro = Registro()
            # Os GGUF que estao em servidor/modelos/ tem que aparecer no /model.
            # Sem esta varredura o menu mostrava so os 5 do modelos.json, e os 36
            # arquivos reais do projeto ficavam inalcancaveis pela interface.
            try:
                self.registro.descobrir_locais()
            except Exception:  # noqa: BLE001
                pass
        if self.skills is None:
            self.skills = Skills()
        if self.sessao is None:
            self.sessao = self.nova_sessao()

    # ------------------------------------------------------------- pastas
    def pasta_trabalho(self) -> Path:
        """Onde o agente escreve. Padrao: a sandbox da sessao (works/).

        Modelo local erra — o harness-bench mediu arquivo morto por `}` solto e
        agente editando o teste em vez do codigo. Entao o padrao e a copia.
        """
        if self.modo_pasta == sandbox.MODO_SANDBOX and self.work is not None:
            return self.work.p
        return self.projeto

    def garantir_work(self, semear_de: Path | None = None) -> object:
        if self.work is None:
            self.work = sandbox.criar(self.sessao.session_id,
                                      self.sessao.nome or "", self.projeto)
            if semear_de is not None:
                sandbox.semear(self.work, semear_de)
        return self.work

    def usar_sandbox(self, ligado: bool):
        self.modo_pasta = sandbox.MODO_SANDBOX if ligado else sandbox.MODO_DIRETO
        if ligado:
            self.garantir_work()
        return self.modo_pasta

    def definir_idioma(self, texto: str) -> tuple[str, float]:
        novo, conf = i18n.detectar(texto, self.idioma)
        self.idioma = novo
        return novo, conf

    # ------------------------------------------------------------- sessao
    def nova_sessao(self) -> Sessao:
        s = Sessao(project=str(self.projeto),
                   model=self.config.get("model"), provider=self.config.get("provider"),
                   harness=self.config.get("harness"), context=self.janela())
        self.sessao = s
        self.metricas = Metricas()
        self.eventos = []
        self.work = None                 # cada sessao ganha o proprio work
        return s

    # ------------------------------------------------------------- atalhos
    def janela(self) -> int:
        v = self.config.get("context", 16384)
        return v if isinstance(v, int) else tamanho_contexto(v)

    def modelo(self) -> str:
        return self.config.get("model", "")

    def cap(self):
        return self.registro.cap(self.modelo())

    def modo_pedido_permissao(self) -> bool:
        """O usuario escolheu PEDIR PERMISSAO na interface?"""
        return self.modo == "perm"

    def so_leitura(self) -> bool:
        """Politica PLANEJAMENTO: o agente nao escreve ate o plano ser aprovado."""
        return self.modo == "plan"

    def nome_modo(self) -> str:
        return POLITICAS.get(self.modo, self.modo.upper())

    def nome_fase(self) -> str:
        return FASES.get(self.fase, self.fase.upper())

    def harness_pedido(self) -> str:
        return self.config.get("harness", "auto")

    def harness_efetivo(self) -> str:
        d = self.ultima_decisao_roteador
        return d.get("selected_harness") or self.harness_pedido()

    def contexto_usado(self) -> int:
        return self.metricas.contexto_atual

    def log(self, nivel: str, texto: str):
        self.logs.append({"nivel": nivel, "texto": texto})
        if len(self.logs) > 500:
            self.logs = self.logs[-500:]

    def evento(self, tipo: str, texto: str, detalhe: str = ""):
        """tipo: acao | ok | erro | info — a UI escolhe o simbolo e a cor."""
        self.eventos.append({"tipo": tipo, "texto": texto, "detalhe": detalhe, "aberto": False})
        return self.eventos[-1]
