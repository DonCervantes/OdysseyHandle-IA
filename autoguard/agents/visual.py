"""Agente de inspección visual de daños. Fotos y costos de ejemplo SIMULADOS.

- El LLM multimodal SOLO clasifica (zona, tipo, confianza); el costo sale de la tabla determinística
  `data/costos_reparacion.yaml` (zona×tipo, MXN SIMULADOS).
- Modo mock (sin llave): usa `hints` (p.ej. nombres de archivo). Primero busca el hint en
  `data/samples/fotos/ground_truth.json`; si no está, interpreta tokens `<zona>-<tipo>` separados por `__`
  (ej. `foto__defensa_trasera-abolladura__faro_izq-estrellado.png`).

CLI:
    python -m autoguard.agents.visual --eval       # recall/precisión sobre las fotos de muestra
    python -m autoguard.agents.visual --generate   # regenera fotos esquemáticas + ground truth
"""
from __future__ import annotations

import argparse
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import yaml

from autoguard import llm
from autoguard.contracts import Dano

_ROOT = Path(__file__).resolve().parents[2]
COSTOS_PATH = _ROOT / "data" / "costos_reparacion.yaml"
FOTOS_DIR = _ROOT / "data" / "samples" / "fotos"
GROUND_TRUTH = "ground_truth.json"

_CONF_MOCK = 0.9
_CONF_MIN = 0.3  # detecciones del LLM por debajo se descartan


@lru_cache(maxsize=4)
def _tabla(path: str = str(COSTOS_PATH)) -> dict[str, Any]:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def zonas() -> list[str]:
    return [z for z in _tabla()["zonas"] if z != "default"]


def tipos() -> list[str]:
    return list(_tabla()["tipos"])


def costo(zona: str, tipo: str) -> float:
    """Costo MXN determinístico por zona×tipo (fila/columna `default` si no existe)."""
    t = _tabla()["zonas"]
    fila = t.get(zona, t["default"])
    if tipo in fila:
        return float(fila[tipo])
    return float(t["default"].get(tipo, t["default"]["reparacion"]))


def _norm(s: Any) -> str:
    return str(s or "").strip().lower().replace(" ", "_").replace("-", "_")


def _consolidar(detecciones: list[tuple[str, str, float]]) -> list[Dano]:
    """Una entrada por zona: se queda el tipo más costoso (p.ej. reemplazo absorbe reparación);
    confianza = máxima observada para ese (zona, tipo). Orden estable por zona."""
    por_zona: dict[str, tuple[str, float]] = {}
    for zona, tipo, conf in detecciones:
        actual = por_zona.get(zona)
        if actual is None or costo(zona, tipo) > costo(zona, actual[0]):
            por_zona[zona] = (tipo, conf)
        elif actual[0] == tipo:
            por_zona[zona] = (tipo, max(conf, actual[1]))
    return [
        Dano(zona=z, tipo=t, costo_est=costo(z, t), confianza=round(min(max(c, 0.0), 1.0), 3))
        for z, (t, c) in sorted(por_zona.items())
    ]


# ---------------------------------------------------------------- mock
def _load_ground_truth(fotos_dir: Path = FOTOS_DIR) -> dict[str, Any]:
    p = fotos_dir / GROUND_TRUTH
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"fotos": {}}


def _parse_hint(hint: str) -> list[tuple[str, str]]:
    nombre = Path(hint).name
    gt = _load_ground_truth()["fotos"].get(nombre)
    if gt is not None:
        return [(d["zona"], d["tipo"]) for d in gt["danos"]]
    stem = Path(nombre).stem
    validos_z, validos_t = set(zonas()), set(tipos())
    out = []
    for tok in stem.split("__"):
        if "-" not in tok:
            continue
        z, t = tok.rsplit("-", 1)
        z, t = _norm(z), _norm(t)
        if z in validos_z and t in validos_t:
            out.append((z, t))
    return out


def _mock(hints: Optional[list[str]]) -> list[Dano]:
    det = [(z, t, _CONF_MOCK) for h in (hints or []) for z, t in _parse_hint(h)]
    return _consolidar(det)


# ---------------------------------------------------------------- LLM
def _system() -> str:
    return (
        "Eres un inspector de daños de carrocería. Analiza las fotos del vehículo y lista SOLO daños "
        "visibles. Responde SOLO JSON: {\"danos\": [{\"zona\": str, \"tipo\": str, \"confianza\": 0..1}]}. "
        f"Zonas permitidas: {', '.join(zonas())}. Tipos permitidos: {', '.join(tipos())}. "
        "No estimes costos. Si no hay daños, devuelve {\"danos\": []}."
    )


_SCHEMA = {
    "type": "object",
    "properties": {
        "danos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"zona": {"type": "string"}, "tipo": {"type": "string"}, "confianza": {"type": "number"}},
                "required": ["zona", "tipo"],
            },
        }
    },
    "required": ["danos"],
}


def inspect(images: list[bytes], hints: list[str] | None = None) -> list[Dano]:
    """Detecta daños visibles y estima costo de reacondicionamiento (tabla de costos determinística por
    zona×tipo; el LLM solo clasifica). Fallback mock usa `hints` (p.ej. nombres de archivo)."""
    if llm.is_mock() or not images:
        return _mock(hints)
    fallback_marker = {"__fallback__": True}
    user = "Inspecciona estas fotos del mismo vehículo."
    if hints:
        user += f" Nombres de archivo (pueden no ser informativos): {', '.join(Path(h).name for h in hints)}."
    data = llm.complete_json(_system(), user, images=list(images), schema=_SCHEMA,
                             fallback=lambda: fallback_marker, max_tokens=1500)
    if not isinstance(data, dict) or data is fallback_marker or data.get("__fallback__"):
        return _mock(hints)
    validos_z, validos_t = set(zonas()), set(tipos())
    det = []
    try:
        for d in data.get("danos", []) or []:
            z, t = _norm(d.get("zona")), _norm(d.get("tipo"))
            conf = float(d.get("confianza", 0.7))
            if t not in validos_t or conf < _CONF_MIN:
                continue
            det.append((z if z in validos_z else "otra", t, conf))  # zona desconocida: costo `default`
    except (AttributeError, TypeError, ValueError):
        return _mock(hints)
    return _consolidar(det)


# ---------------------------------------------------------------- fotos SIMULADAS
# Vista superior esquemática (frente arriba). Cajas: zona -> (x0, y0, x1, y1).
_LAYOUT = {
    "defensa_delantera": (230, 40, 470, 75), "faro_izq": (205, 80, 255, 110), "faro_der": (445, 80, 495, 110),
    "cofre": (260, 80, 440, 200), "salpicadera_izq": (200, 115, 255, 200), "salpicadera_der": (445, 115, 500, 200),
    "espejo_izq": (150, 210, 195, 240), "espejo_der": (505, 210, 550, 240),
    "parabrisas": (260, 205, 440, 260), "toldo": (260, 265, 440, 420),
    "puerta_delantera_izq": (200, 205, 255, 330), "puerta_delantera_der": (445, 205, 500, 330),
    "puerta_trasera_izq": (200, 335, 255, 460), "puerta_trasera_der": (445, 335, 500, 460),
    "cajuela": (260, 425, 440, 550), "calavera_izq": (205, 525, 255, 550), "calavera_der": (445, 525, 495, 550),
    "defensa_trasera": (230, 555, 470, 590),
}

_MUESTRAS: list[tuple[str, list[tuple[str, str]]]] = [
    ("FOTO-001.png", [("defensa_trasera", "abolladura")]),
    ("FOTO-002.png", [("puerta_delantera_izq", "rayon"), ("espejo_izq", "estrellado")]),
    ("FOTO-003.png", [("cofre", "reparacion"), ("faro_der", "estrellado"), ("defensa_delantera", "reemplazo")]),
    ("FOTO-004.png", [("parabrisas", "estrellado")]),
    ("FOTO-005.png", [("salpicadera_der", "abolladura"), ("puerta_trasera_der", "rayon"), ("calavera_der", "reemplazo")]),
    ("FOTO-006.png", []),  # sin daños
]


def _render(danos: list[tuple[str, str]], path: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (700, 640), "white")
    dr = ImageDraw.Draw(img)
    f_s, f_m, f_l = (ImageFont.load_default(size=s) for s in (11, 16, 30))
    dr.text((20, 10), f"INSPECCION VISUAL - {path.stem}", fill="black", font=f_m)
    dr.rounded_rectangle([195, 35, 505, 595], radius=40, outline="black", width=3)
    marcadas = dict(danos)
    for zona, (x0, y0, x1, y1) in _LAYOUT.items():
        tipo = marcadas.get(zona)
        dr.rectangle([x0, y0, x1, y1], outline="gray", width=1, fill=(255, 190, 190) if tipo else None)
        if tipo:
            dr.line([x0, y0, x1, y1], fill=(200, 0, 0), width=3)
            dr.line([x0, y1, x1, y0], fill=(200, 0, 0), width=3)
    for i, (zona, tipo) in enumerate(danos):
        dr.text((20, 40 + 20 * i), f"{zona}: {tipo}", fill=(160, 0, 0), font=f_s)
    dr.text((480, 600), "SIMULADO", fill=(220, 30, 30), font=f_l)
    img.save(path, format="PNG")


def generate_samples(out_dir: Path = FOTOS_DIR) -> dict[str, Any]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    gt: dict[str, Any] = {
        "nota": "Fotos esquemáticas SIMULADAS para la demo de KAVAK AUTOGUARD AI.",
        "fotos": {},
    }
    for nombre, danos in _MUESTRAS:
        _render(danos, out_dir / nombre)
        gt["fotos"][nombre] = {"danos": [{"zona": z, "tipo": t} for z, t in danos]}
    (out_dir / GROUND_TRUTH).write_text(json.dumps(gt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return gt


def evaluate(fotos_dir: Path = FOTOS_DIR) -> dict[str, Any]:
    """Recall y precisión de (zona, tipo) por foto contra el ground truth."""
    gt = _load_ground_truth(fotos_dir)
    tp = fn = fp = 0
    por_foto = {}
    for nombre, d in gt["fotos"].items():
        esperado = {(x["zona"], x["tipo"]) for x in d["danos"]}
        obtenido = {(x.zona, x.tipo) for x in inspect([(fotos_dir / nombre).read_bytes()], hints=[nombre])}
        tp_i, fn_i, fp_i = len(esperado & obtenido), len(esperado - obtenido), len(obtenido - esperado)
        tp, fn, fp = tp + tp_i, fn + fn_i, fp + fp_i
        por_foto[nombre] = {"recall": tp_i / len(esperado) if esperado else 1.0, "falsos_positivos": fp_i}
    return {
        "modo": "mock" if llm.is_mock() else "llm",
        "n_fotos": len(gt["fotos"]),
        "recall": tp / (tp + fn) if tp + fn else 1.0,
        "precision": tp / (tp + fp) if tp + fp else 1.0,
        "por_foto": por_foto,
    }


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Agente visual de daños (datos SIMULADOS)")
    ap.add_argument("--eval", action="store_true")
    ap.add_argument("--generate", action="store_true")
    args = ap.parse_args(argv)
    if args.generate:
        gt = generate_samples()
        print(f"Generadas {len(gt['fotos'])} fotos SIMULADAS en {FOTOS_DIR}")
    if args.eval or not args.generate:
        r = evaluate()
        print(f"Modo: {r['modo']}  ·  fotos: {r['n_fotos']}  ·  recall {r['recall']:.1%}  ·  precisión {r['precision']:.1%}")
        for nombre, m in r["por_foto"].items():
            print(f"  {nombre}: recall {m['recall']:.0%}  FP {m['falsos_positivos']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
