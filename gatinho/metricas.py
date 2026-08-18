# -*- coding: utf-8 -*-
"""Metricas — com a separacao que o benchmark exigiu (requisitos 36, 82).

    tool_calls_emitted   o modelo PEDIU
    tool_calls_executed  o runtime RODOU
    tool_calls_blocked   o runtime BARROU (excedente do passo, guarda, permissao)

Chamar os tres de "tool calls" ja produziu diagnostico errado no harness-bench:
um modelo emitiu 139 numa resposta e teve 5 executadas.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict


@dataclass
class Metricas:
    turnos: int = 0
    tool_calls_emitted: int = 0
    tool_calls_executed: int = 0
    tool_calls_blocked: int = 0
    motivos_bloqueio: dict = field(default_factory=dict)
    erros_ferramenta: int = 0
    erros_por_ferramenta: dict = field(default_factory=dict)
    escritas_revertidas: int = 0
    # contexto
    contexto_atual: int = 0
    contexto_pico: int = 0
    compaction_count: int = 0
    context_before: int = 0
    context_after: int = 0
    # tempo
    tempo_modelo: float = 0.0
    tempo_ferramentas: float = 0.0
    inicio: float = field(default_factory=time.time)
    # entrega
    provas_executadas: int = 0
    encerramentos_vazios_barrados: int = 0

    @property
    def tempo_total(self) -> float:
        return round(time.time() - self.inicio, 1)

    def bloquear(self, quantos: int, motivo: str):
        self.tool_calls_blocked += quantos
        self.motivos_bloqueio[motivo] = self.motivos_bloqueio.get(motivo, 0) + quantos

    def erro(self, ferramenta: str):
        self.erros_ferramenta += 1
        self.erros_por_ferramenta[ferramenta] = self.erros_por_ferramenta.get(ferramenta, 0) + 1

    def marcar_contexto(self, tokens: int):
        self.contexto_atual = tokens
        self.contexto_pico = max(self.contexto_pico, tokens)

    def dic(self) -> dict:
        d = asdict(self)
        d["tempo_total"] = self.tempo_total
        d.pop("inicio", None)
        return d

    def resumo_linhas(self) -> list[str]:
        """O que /metrics mostra. Nada disso fica permanente na tela (requisito 66)."""
        return [
            f"Turnos: {self.turnos}",
            "",
            f"Tools emitidas:   {self.tool_calls_emitted}",
            f"Tools executadas: {self.tool_calls_executed}",
            f"Tools bloqueadas: {self.tool_calls_blocked}"
            + (f"  ({', '.join(f'{k}={v}' for k, v in self.motivos_bloqueio.items())})"
               if self.motivos_bloqueio else ""),
            "",
            f"Contexto pico: {self.contexto_pico}",
            f"Compactacoes: {self.compaction_count}",
            "",
            f"Tempo modelo: {self.tempo_modelo:.0f}s",
            f"Tempo ferramentas: {self.tempo_ferramentas:.0f}s",
            f"Tempo total: {self.tempo_total:.0f}s",
        ]
