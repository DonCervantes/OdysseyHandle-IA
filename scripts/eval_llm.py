#!/usr/bin/env python
"""Set de evaluación con LLM real (T-28).

Mide precisión de extracción documental (meta ≥90%) y recall de daños (meta ≥80%)
sobre `data/samples/` + `data/eval/` (casos SIMULADOS extra). Requiere
`OPENAI_API_KEY`; fuerza `LLM_CACHE=1` y reporta costo estimado en tokens.

Sin llave sale con mensaje claro (código 2). No forma parte de la suite pytest
(los tests nunca llaman a la red).

Uso:
    python scripts/eval_llm.py              # evalúa (exige llave)
    python scripts/eval_llm.py --generate   # regenera PNGs + ground_truth en data/eval/
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import autoguard  # noqa: F401  — carga .env
from autoguard import llm
from autoguard.agents import documental, visual

EVAL_DIR = ROOT / "data" / "eval"
EVAL_DOCS = EVAL_DIR / "docs"
EVAL_FOTOS = EVAL_DIR / "fotos"
SAMPLES_DOCS = ROOT / "data" / "samples" / "docs"
SAMPLES_FOTOS = ROOT / "data" / "samples" / "fotos"

META_PRECISION = 0.90
META_RECALL = 0.80

# Precios de referencia USD / millón de tokens (estimación; no factura real).
# Ajusta con LLM_PRICE_IN / LLM_PRICE_OUT si el modelo cambia.
_DEFAULT_PRICE_IN = 2.0   # gpt-6.1-sol (developers.openai.com, 2026-11-09)
_DEFAULT_PRICE_OUT = 10.0
# Heurística si la API no reporta usage: ~4 chars/token texto; imagen típica ~1600 tok.
_CHARS_PER_TOKEN = 4
_IMAGE_TOKENS = 1600


MSG_NO_KEY = (
    "OPENAI_API_KEY no está configurada. "
    "Este script mide precisión/recall con el LLM real y no corre en modo mock. "
    "Copia `.env.example` a `.env`, pon tu llave, y vuelve a ejecutar "
    "`python scripts/eval_llm.py` (activa LLM_CACHE=1 automáticamente)."
)


@dataclass
class UsageStats:
    api_calls: int = 0
    cache_hits: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated: bool = False  # True si algún conteo fue heurístico
    _orig_call: Any = field(default=None, repr=False)
    _orig_cache_get: Any = field(default=None, repr=False)

    def install(self) -> None:
        """Intercepta llamadas LLM y caché para acumular tokens."""
        self._orig_call = llm._call
        self._orig_cache_get = llm._cache_get
        stats = self

        def tracked_call(client: Any, model: str, system: str, content: list[dict], max_tokens: int) -> str:
            resp = client.responses.create(**llm.build_request(model, system, content, max_tokens))
            stats.api_calls += 1
            usage = getattr(resp, "usage", None)
            if usage is not None and getattr(usage, "input_tokens", None) is not None:
                stats.input_tokens += int(usage.input_tokens)
                stats.output_tokens += int(getattr(usage, "output_tokens", 0) or 0)
            else:
                stats.estimated = True
                text_in = len(system) + sum(len(b.get("text", "")) for b in content if b.get("type") == "input_text")
                n_img = sum(1 for b in content if b.get("type") in ("input_image", "input_file"))
                stats.input_tokens += text_in // _CHARS_PER_TOKEN + n_img * _IMAGE_TOKENS
                stats.output_tokens += max(1, len(llm._response_text(resp)) // _CHARS_PER_TOKEN)
            return llm._response_text(resp)

        def tracked_cache_get(key: str) -> Optional[dict[str, Any]]:
            cached = stats._orig_cache_get(key)
            if cached is not None:
                stats.cache_hits += 1
            return cached

        llm._call = tracked_call  # type: ignore[assignment]
        llm._cache_get = tracked_cache_get  # type: ignore[assignment]

    def uninstall(self) -> None:
        if self._orig_call is not None:
            llm._call = self._orig_call  # type: ignore[assignment]
        if self._orig_cache_get is not None:
            llm._cache_get = self._orig_cache_get  # type: ignore[assignment]

    def add_output_estimate(self, data: dict[str, Any]) -> None:
        """Si la API no dio usage de salida, estima a partir del JSON parseado."""
        if not self.estimated:
            return
        self.output_tokens += max(1, len(json.dumps(data, ensure_ascii=False)) // _CHARS_PER_TOKEN)

    def cost_usd(self) -> float:
        pin = float(os.getenv("LLM_PRICE_IN", _DEFAULT_PRICE_IN))
        pout = float(os.getenv("LLM_PRICE_OUT", _DEFAULT_PRICE_OUT))
        return (self.input_tokens * pin + self.output_tokens * pout) / 1_000_000.0


# ---------------------------------------------------------------- generación data/eval
def _extra_docs() -> list[dict[str, Any]]:
    """Expedientes SIMULADOS adicionales (no están en data/samples/)."""
    vin4 = documental._con_digito("3VWLL7AJ0EM012345")  # VW Golf 2014
    vin5 = documental._con_digito("MAJERDE20JC045678")  # Honda City 2018 (MX)
    vin5_bad = documental._con_digito("MAJERDE20JC099999")
    base = [
        ("EXP-004", "Volkswagen", "Golf", 2014, "JAL-321-D", vin4, {}, "2027-11-30",
         ["DOCUMENTO_VENCIDO:poliza_anterior"]),
        ("EXP-005", "Honda", "City", 2018, "GTO-654-E", vin5,
         {"tarjeta_circulacion": {"vin": vin5_bad}}, "2029-01-15", ["VIN_NO_COINCIDE"]),
    ]
    exps = []
    for exp_id, marca, modelo, anio, placas, vin, overrides, vig_tc, esperadas in base:
        n = exp_id[-3:]
        docs = [
            {"documento_id": f"{exp_id}-FAC", "tipo": "factura", "vin": vin, "placas": None,
             "marca": marca, "modelo": modelo, "anio": anio, "vigencia": None,
             "campos_extra": {"folio": f"SIM-F{n}", "emisor": "Agencia SIMULADA SA de CV",
                              "valor_factura": 280000 + 5000 * int(n), "nota": "SIMULADO"}},
            {"documento_id": f"{exp_id}-TC", "tipo": "tarjeta_circulacion", "vin": vin, "placas": placas,
             "marca": marca, "modelo": modelo, "anio": anio, "vigencia": vig_tc,
             "campos_extra": {"propietario": "PERSONA SIMULADA"}},
            {"documento_id": f"{exp_id}-POL", "tipo": "poliza_anterior", "vin": vin, "placas": placas,
             "marca": marca, "modelo": modelo, "anio": anio, "vigencia": "2025-12-01",
             "campos_extra": {"aseguradora": "Aseguradora SIMULADA", "numero_poliza": f"SIM-P{n}"}},
        ]
        for d in docs:
            d.update(overrides.get(d["tipo"], {}))
            d["archivo"] = f"{d['documento_id']}.png"
            d["expediente"] = exp_id
        exps.append({"expediente": exp_id, "documentos": docs, "alertas_esperadas": esperadas})
    return exps


_EXTRA_FOTOS: list[tuple[str, list[tuple[str, str]]]] = [
    ("FOTO-007.png", [("toldo", "rayon"), ("puerta_delantera_der", "abolladura")]),
    ("FOTO-008.png", [("cajuela", "reparacion"), ("calavera_izq", "estrellado")]),
    ("FOTO-009.png", [("espejo_der", "reemplazo")]),
]


def generate_eval_set() -> dict[str, Any]:
    """Regenera PNGs SIMULADOS y ground_truth en data/eval/."""
    EVAL_DOCS.mkdir(parents=True, exist_ok=True)
    EVAL_FOTOS.mkdir(parents=True, exist_ok=True)

    gt_docs: dict[str, Any] = {
        "nota": (
            "Documentos SIMULADOS extra para eval LLM (T-28). "
            "No corresponden a personas ni autos reales."
        ),
        "fecha_referencia": "2026-11-09",
        "documentos": {},
        "expedientes": {},
    }
    for exp in _extra_docs():
        gt_docs["expedientes"][exp["expediente"]] = {
            "documentos": [d["documento_id"] for d in exp["documentos"]],
            "alertas_esperadas": exp["alertas_esperadas"],
        }
        for d in exp["documentos"]:
            documental._render(d, EVAL_DOCS / d["archivo"])
            gt_docs["documentos"][d["documento_id"]] = {k: v for k, v in d.items() if k != "documento_id"}
    (EVAL_DOCS / "ground_truth.json").write_text(
        json.dumps(gt_docs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    gt_fotos: dict[str, Any] = {
        "nota": "Fotos esquemáticas SIMULADAS extra para eval LLM (T-28).",
        "fotos": {},
    }
    for nombre, danos in _EXTRA_FOTOS:
        visual._render(danos, EVAL_FOTOS / nombre)
        gt_fotos["fotos"][nombre] = {"danos": [{"zona": z, "tipo": t} for z, t in danos]}
    (EVAL_FOTOS / "ground_truth.json").write_text(
        json.dumps(gt_fotos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    manifest = {
        "nota": "Set de evaluación LLM (T-28). Todos los datos son SIMULADOS.",
        "metas": {"precision_documental": META_PRECISION, "recall_danos": META_RECALL},
        "fuentes": {
            "samples_docs": SAMPLES_DOCS.relative_to(ROOT).as_posix(),
            "samples_fotos": SAMPLES_FOTOS.relative_to(ROOT).as_posix(),
            "eval_docs": EVAL_DOCS.relative_to(ROOT).as_posix(),
            "eval_fotos": EVAL_FOTOS.relative_to(ROOT).as_posix(),
        },
        "extras": {
            "documentos": list(gt_docs["documentos"]),
            "fotos": list(gt_fotos["fotos"]),
        },
    }
    (EVAL_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {"docs": gt_docs, "fotos": gt_fotos, "manifest": manifest}


# ---------------------------------------------------------------- métricas
def _eval_documental(dirs: list[Path]) -> dict[str, Any]:
    aciertos: Counter[str] = Counter()
    totales: Counter[str] = Counter()
    n_docs = 0
    detalle: dict[str, Any] = {}
    for samples_dir in dirs:
        if not (samples_dir / documental.GROUND_TRUTH).exists():
            continue
        gt = documental._load_ground_truth(samples_dir)
        for doc_id, d in gt["documentos"].items():
            path = samples_dir / d["archivo"]
            if not path.exists():
                continue
            n_docs += 1
            ex = documental.extract(path.read_bytes(), d["tipo"], doc_id, mime="image/png")
            ok_campos = {}
            for c in documental.CAMPOS:
                esperado = documental._norm_campo(c, d.get(c))
                obtenido = documental._norm_campo(c, getattr(ex, c))
                if esperado is None and obtenido is None:
                    continue
                totales[c] += 1
                hit = esperado == obtenido
                aciertos[c] += int(hit)
                ok_campos[c] = hit
            detalle[doc_id] = {"fuente": str(samples_dir.name), "campos": ok_campos}
    precision = {c: (aciertos[c] / totales[c] if totales[c] else 1.0) for c in documental.CAMPOS}
    total_c = sum(totales.values())
    return {
        "n_documentos": n_docs,
        "precision_por_campo": precision,
        "precision_global": (sum(aciertos.values()) / total_c) if total_c else 1.0,
        "campos_evaluados": total_c,
        "detalle": detalle,
    }


def _eval_visual(dirs: list[Path]) -> dict[str, Any]:
    tp = fn = fp = 0
    n_fotos = 0
    por_foto: dict[str, Any] = {}
    for fotos_dir in dirs:
        if not (fotos_dir / visual.GROUND_TRUTH).exists():
            continue
        gt = visual._load_ground_truth(fotos_dir)
        for nombre, d in gt["fotos"].items():
            path = fotos_dir / nombre
            if not path.exists():
                continue
            n_fotos += 1
            esperado = {(x["zona"], x["tipo"]) for x in d["danos"]}
            # sin hints: un fallo del LLM no debe caer al ground truth
            obtenido = {(x.zona, x.tipo) for x in visual.inspect([path.read_bytes()], hints=None)}
            tp_i = len(esperado & obtenido)
            fn_i = len(esperado - obtenido)
            fp_i = len(obtenido - esperado)
            tp, fn, fp = tp + tp_i, fn + fn_i, fp + fp_i
            por_foto[nombre] = {
                "fuente": str(fotos_dir.name),
                "recall": tp_i / len(esperado) if esperado else 1.0,
                "falsos_positivos": fp_i,
            }
    return {
        "n_fotos": n_fotos,
        "recall": tp / (tp + fn) if tp + fn else 1.0,
        "precision": tp / (tp + fp) if tp + fp else 1.0,
        "tp": tp,
        "fn": fn,
        "fp": fp,
        "por_foto": por_foto,
    }


def run_eval() -> dict[str, Any]:
    os.environ["LLM_CACHE"] = "1"
    # no forzar mock aunque alguien tenga LLM_PROVIDER=mock en el entorno
    if os.getenv("LLM_PROVIDER", "auto") == "mock":
        os.environ["LLM_PROVIDER"] = "auto"

    if llm.is_mock():
        raise RuntimeError("modo mock activo; se requiere OPENAI_API_KEY")

    stats = UsageStats()
    stats.install()
    try:
        docs = _eval_documental([SAMPLES_DOCS, EVAL_DOCS])
        fotos = _eval_visual([SAMPLES_FOTOS, EVAL_FOTOS])
    finally:
        stats.uninstall()

    precision_ok = docs["precision_global"] >= META_PRECISION
    recall_ok = fotos["recall"] >= META_RECALL
    return {
        "modo": "llm",
        "modelo": os.getenv("LLM_MODEL", llm.DEFAULT_MODEL),
        "llm_cache": True,
        "metas": {
            "precision_documental": META_PRECISION,
            "recall_danos": META_RECALL,
            "precision_ok": precision_ok,
            "recall_ok": recall_ok,
            "pasa": precision_ok and recall_ok,
        },
        "documental": docs,
        "visual": fotos,
        "tokens": {
            "api_calls": stats.api_calls,
            "cache_hits": stats.cache_hits,
            "input_tokens": stats.input_tokens,
            "output_tokens": stats.output_tokens,
            "total_tokens": stats.input_tokens + stats.output_tokens,
            "estimado_heuristico": stats.estimated,
            "costo_usd_estimado": round(stats.cost_usd(), 4),
            "precio_ref_usd_por_mtok": {
                "input": float(os.getenv("LLM_PRICE_IN", _DEFAULT_PRICE_IN)),
                "output": float(os.getenv("LLM_PRICE_OUT", _DEFAULT_PRICE_OUT)),
            },
        },
        "nota": "Todos los casos evaluados son SIMULADOS.",
    }


def _print_report(r: dict[str, Any]) -> None:
    print("=" * 60)
    print("KAVAK AUTOGUARD AI · eval LLM (datos SIMULADOS)")
    print("=" * 60)
    print(f"Modelo: {r['modelo']}  ·  caché: {r['llm_cache']}")
    d, v, m, t = r["documental"], r["visual"], r["metas"], r["tokens"]
    print(f"\nDocumental ({d['n_documentos']} docs, {d['campos_evaluados']} campos):")
    for c, p in d["precision_por_campo"].items():
        print(f"  {c:<10} {p:6.1%}")
    print(f"  {'GLOBAL':<10} {d['precision_global']:6.1%}  "
          f"(meta ≥{m['precision_documental']:.0%})  {'OK' if m['precision_ok'] else 'FALLA'}")
    print(f"\nVisual ({v['n_fotos']} fotos):")
    print(f"  recall     {v['recall']:6.1%}  (meta ≥{m['recall_danos']:.0%})  "
          f"{'OK' if m['recall_ok'] else 'FALLA'}")
    print(f"  precisión  {v['precision']:6.1%}  (tp={v['tp']} fn={v['fn']} fp={v['fp']})")
    print(f"\nTokens / costo estimado:")
    print(f"  llamadas API: {t['api_calls']}  ·  cache hits: {t['cache_hits']}")
    print(f"  input: {t['input_tokens']:,}  ·  output: {t['output_tokens']:,}  "
          f"·  total: {t['total_tokens']:,}")
    heur = " (heurístico)" if t["estimado_heuristico"] else ""
    print(f"  costo USD estimado{heur}: ${t['costo_usd_estimado']:.4f}")
    print(f"\nResultado: {'PASA metas' if m['pasa'] else 'NO alcanza metas'}")


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Eval LLM real: precisión documental + recall de daños (SIMULADO)")
    ap.add_argument("--generate", action="store_true", help="regenera muestras SIMULADAS en data/eval/")
    ap.add_argument("--json", action="store_true", help="imprime el reporte completo en JSON")
    args = ap.parse_args(argv)

    if args.generate:
        out = generate_eval_set()
        print(
            f"Generados {len(out['docs']['documentos'])} docs y "
            f"{len(out['fotos']['fotos'])} fotos SIMULADAS en {EVAL_DIR}"
        )
        return 0

    if not os.getenv("OPENAI_API_KEY"):
        print(MSG_NO_KEY, file=sys.stderr)
        return 2

    report = run_eval()
    if args.json:
        # detalle por doc puede ser verboso; se incluye completo a propósito
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_report(report)
    return 0 if report["metas"]["pasa"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
