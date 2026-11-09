"""Meta-mejorador: Thompson sampling por tipo de parche + lecciones. [T-11]

- Cada tipo de parche (brazo) tiene una Beta(alpha, beta). Prior Beta(1, 1).
- Recompensa de un parche = 1 si fue aceptado (o sin veredicto) y su ganancia en el holdout es > 0;
  0 en cualquier otro caso (rechazado, inválido o ganancia <= 0).
- `lecciones` es la "estrategia" que se inyecta al prompt del mejorador. Cada generación se reescribe
  (LLM con fallback determinístico). Ese cambio también se evalúa: si la ganancia media de la
  generación que usó la estrategia nueva es MENOR que la de la generación anterior, se revierte a la
  estrategia previa (y esa generación no propone una estrategia nueva).

No importa ni escribe nada de autoguard.evaluator (seguridad del RSI).
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from autoguard import llm
from autoguard.contracts import MetaStrategy, Patch

MAX_LECCIONES_CHARS = 1500

SYSTEM_LECCIONES = (
    "Eres el meta-mejorador de un sistema de auto-mejora de un cotizador de seguros de autos "
    "(datos SIMULADOS). Resume en español, en <= 8 viñetas breves, las lecciones de los parches "
    "aceptados y rechazados de esta generación, y da recomendaciones concretas al mejorador sobre qué "
    "tipo de parche y qué segmentos priorizar. No inventes métricas. Responde SOLO JSON: "
    '{"lecciones": "<texto>"}'
)

LECCIONES_SCHEMA = {
    "type": "object",
    "properties": {"lecciones": {"type": "string"}},
    "required": ["lecciones"],
}


def patch_gain(patch: Patch) -> float:
    """Ganancia relativa en holdout de un parche a partir de sus métricas (0.0 si no hay datos)."""
    after, before = patch.metrics_after or {}, patch.metrics_before or {}
    for d in (after, before):
        if "ganancia" in d:
            return float(d["ganancia"])
    for key in (patch.metrica_objetivo, "loss", "loss_asimetrica"):
        if key in before and key in after and before[key]:
            return float((before[key] - after[key]) / before[key])
    return 0.0


def patch_reward(patch: Patch) -> int:
    """Recompensa Bernoulli del bandido: 1 si el parche aporta ganancia real (> 0)."""
    if patch.veredicto in ("rechazado", "invalido"):
        return 0
    return int(patch_gain(patch) > 0)


def realized_gain(patch: Patch) -> float:
    """Ganancia que efectivamente aportó el parche (0 si no se aplicó)."""
    if patch.veredicto in ("rechazado", "invalido"):
        return 0.0
    return max(0.0, patch_gain(patch))


class MetaImprover:
    def __init__(self, arms: list[str], seed: int = 0):
        if not arms:
            raise ValueError("MetaImprover requiere al menos un brazo")
        self.arms = list(arms)
        self.rng = np.random.default_rng(seed)
        self.alpha: dict[str, float] = {a: 1.0 for a in self.arms}
        self.beta: dict[str, float] = {a: 1.0 for a in self.arms}
        self.generation = 0
        self.lecciones = ""
        self.tasa_aceptacion = 0.0
        self.ganancia_media = 0.0
        self.history: list[MetaStrategy] = []
        # Estado de la evaluación del cambio de estrategia.
        self._prev_lecciones: Optional[str] = None  # estrategia antes del último cambio pendiente
        self._prev_gain: Optional[float] = None  # ganancia media de la generación previa al cambio
        self.last_reverted = False
        self.reversions = 0

    # ------------------------------------------------------------ bandido
    def choose_arms(self, k: int) -> list[str]:
        """Muestrea k brazos (con reemplazo) por Thompson sampling sobre Beta(alpha, beta)."""
        out: list[str] = []
        a = np.array([self.alpha[x] for x in self.arms])
        b = np.array([self.beta[x] for x in self.arms])
        for _ in range(max(0, k)):
            draws = self.rng.beta(a, b)
            out.append(self.arms[int(np.argmax(draws))])
        return out

    def plan_arms(self, k: int, control: str = "cambio_prompt", max_control: int = 1) -> tuple[list[str], list[str]]:
        """Plan de una generación: k brazos por Thompson sampling, con el brazo de control (no cambia la
        prima) limitado a `max_control` slots (los sorteos extra caen en el mejor brazo no-control de ese
        mismo sorteo). Devuelve también los sustitutos (no-control, por media posterior) para los slots
        cuyo brazo no logre proponer un cambio válido. El bandido sigue aprendiendo de todos los parches."""
        out: list[str] = []
        a = np.array([self.alpha[x] for x in self.arms])
        b = np.array([self.beta[x] for x in self.arms])
        for _ in range(max(0, k)):
            draws = self.rng.beta(a, b)
            order = [self.arms[i] for i in np.argsort(-draws, kind="stable")]
            if out.count(control) >= max_control:
                order = [x for x in order if x != control] or order
            out.append(order[0])
        pm = self.posterior_mean()
        subs = sorted((x for x in self.arms if x != control), key=lambda x: (-pm[x], self.arms.index(x)))
        return out, subs

    def posterior_mean(self) -> dict[str, float]:
        return {x: self.alpha[x] / (self.alpha[x] + self.beta[x]) for x in self.arms}

    # ------------------------------------------------------------ actualización
    def update(self, patches: list[Patch]) -> MetaStrategy:
        """Actualiza posteriors con veredictos (recompensa = ganancia>0), reescribe lecciones (LLM con
        fallback), y revierte el cambio de estrategia si la ganancia media de la generación bajó."""
        gens = [p.generation for p in patches]
        self.generation = max(gens) if gens else self.generation + 1

        for p in patches:
            if p.tipo not in self.alpha:  # brazo desconocido: se agrega con prior plano
                self.arms.append(p.tipo)
                self.alpha[p.tipo] = 1.0
                self.beta[p.tipo] = 1.0
            r = patch_reward(p)
            self.alpha[p.tipo] += r
            self.beta[p.tipo] += 1 - r

        n = len(patches)
        aceptados = sum(1 for p in patches if p.veredicto == "aceptado")
        self.tasa_aceptacion = aceptados / n if n else 0.0
        gain = float(np.mean([realized_gain(p) for p in patches])) if n else 0.0
        self.ganancia_media = gain

        # ¿La estrategia vigente (cambiada al final de la generación anterior) empeoró la ganancia?
        self.last_reverted = False
        if self._prev_lecciones is not None and self._prev_gain is not None and gain < self._prev_gain:
            self.lecciones = self._prev_lecciones
            self.last_reverted = True
            self.reversions += 1
            self._prev_lecciones = None
            self._prev_gain = None
        else:
            # Se acepta la estrategia vigente y se propone una nueva, que se evaluará la próxima vez.
            nuevas = self._rewrite_lecciones(patches)
            self._prev_lecciones = self.lecciones
            self._prev_gain = gain
            self.lecciones = nuevas

        strat = self.strategy()
        self.history.append(strat)
        return strat

    def strategy(self) -> MetaStrategy:
        return MetaStrategy(
            generation=self.generation,
            arms={a: (float(self.alpha[a]), float(self.beta[a])) for a in self.arms},
            lecciones=self.lecciones,
            tasa_aceptacion=float(self.tasa_aceptacion),
            ganancia_media=float(self.ganancia_media),
        )

    # ------------------------------------------------------------ lecciones
    def _rewrite_lecciones(self, patches: list[Patch]) -> str:
        fallback_text = self._fallback_lecciones(patches)
        user = self._lecciones_prompt(patches)
        try:
            res = llm.complete_json(
                SYSTEM_LECCIONES,
                user,
                schema=LECCIONES_SCHEMA,
                fallback=lambda: {"lecciones": fallback_text},
                max_tokens=1200,
            )
            text = str(res.get("lecciones") or "").strip()
        except Exception:  # noqa: BLE001 - el meta-mejorador nunca debe romper el ciclo
            text = ""
        return (text or fallback_text)[:MAX_LECCIONES_CHARS]

    def _lecciones_prompt(self, patches: list[Patch]) -> str:
        lines = [f"Generación {self.generation}. Posterior media por brazo:"]
        for a, m in sorted(self.posterior_mean().items(), key=lambda kv: -kv[1]):
            lines.append(f"- {a}: {m:.2f} (alpha={self.alpha[a]:.0f}, beta={self.beta[a]:.0f})")
        lines.append("Parches de la generación:")
        for p in patches:
            lines.append(
                f"- [{p.veredicto or 'sin_veredicto'}] {p.tipo} ganancia={patch_gain(p):+.3f} "
                f"segmento={p.segmento} hipótesis={p.hipotesis[:160]!r} razón={p.razon[:160]!r}"
            )
        lines.append(f"Lecciones previas:\n{self.lecciones or '(ninguna)'}")
        return "\n".join(lines)

    def _fallback_lecciones(self, patches: list[Patch]) -> str:
        """Resumen determinístico de la generación (modo mock / error del LLM)."""
        pm = self.posterior_mean()
        ranking = sorted(self.arms, key=lambda a: (-pm[a], self.arms.index(a)))
        lines = [
            f"Gen {self.generation}: {sum(p.veredicto == 'aceptado' for p in patches)}/{len(patches)} "
            f"parches aceptados; ganancia media {self.ganancia_media:+.3f}.",
            "Prioriza brazos: " + ", ".join(f"{a} ({pm[a]:.2f})" for a in ranking) + ".",
        ]
        good = sorted((p for p in patches if patch_reward(p)), key=lambda p: -patch_gain(p))[:3]
        bad = [p for p in patches if not patch_reward(p)][:3]
        for p in good:
            lines.append(f"+ Funcionó {p.tipo} en {p.segmento or 'todos'} ({patch_gain(p):+.3f}).")
        for p in bad:
            motivo = p.razon or p.veredicto or "sin ganancia"
            lines.append(f"- Evitar repetir {p.tipo} en {p.segmento or 'todos'}: {motivo}.")
        return "\n".join(lines)
