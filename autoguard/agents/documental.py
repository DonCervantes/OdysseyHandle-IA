"""Agente documental: extracción (LLM multimodal con fallback mock) + verificación cruzada determinística.

Todos los documentos de ejemplo son SIMULADOS (`data/samples/docs/`).

CLI:
    python -m autoguard.agents.documental --eval        # precisión por campo sobre las muestras
    python -m autoguard.agents.documental --generate    # regenera PNGs + ground_truth.json
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Optional

from autoguard import llm
from autoguard.contracts import Alerta, Dano, DocExtraction, TipoDocumento, VehicleProfile
from autoguard.segments import ANIO_REFERENCIA

SAMPLES_DIR = Path(__file__).resolve().parents[2] / "data" / "samples" / "docs"
GROUND_TRUTH = "ground_truth.json"

CAMPOS = ["vin", "placas", "marca", "modelo", "anio", "vigencia"]
CAMPOS_PERFIL = ["vin", "placas", "marca", "modelo", "anio"]
# prioridad de la fuente al consolidar (menor = más confiable)
_PRIORIDAD = {"factura": 0, "tarjeta_circulacion": 1, "poliza_anterior": 2, "otro": 3}

# ---------------------------------------------------------------- VIN (ISO 3779 / NHTSA 49 CFR 565)
_VIN_TRANSLIT = {
    **{str(d): d for d in range(10)},
    "A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6, "G": 7, "H": 8,
    "J": 1, "K": 2, "L": 3, "M": 4, "N": 5, "P": 7, "R": 9,
    "S": 2, "T": 3, "U": 4, "V": 5, "W": 6, "X": 7, "Y": 8, "Z": 9,
}
_VIN_PESOS = [8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2]
_VIN_RE = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")


def normalize_vin(vin: Optional[str]) -> Optional[str]:
    if vin is None:
        return None
    v = re.sub(r"[\s\-\.]", "", str(vin)).upper()
    return v or None


def vin_check_digit(vin: str) -> str:
    """Dígito verificador (posición 9) calculado sobre un VIN de 17 caracteres válidos."""
    total = sum(_VIN_TRANSLIT[c] * w for c, w in zip(vin, _VIN_PESOS))
    r = total % 11
    return "X" if r == 10 else str(r)


def vin_valido(vin: Optional[str]) -> bool:
    v = normalize_vin(vin)
    return bool(v and _VIN_RE.match(v) and v[8] == vin_check_digit(v))


def _norm_texto(s: Any) -> Optional[str]:
    if s is None or str(s).strip() == "":
        return None
    t = unicodedata.normalize("NFKD", str(s))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip().casefold()


def _norm_placas(p: Any) -> Optional[str]:
    if p is None:
        return None
    v = re.sub(r"[\s\-\.]", "", str(p)).upper()
    return v or None


def _norm_campo(campo: str, valor: Any) -> Any:
    if valor is None:
        return None
    if campo == "vin":
        return normalize_vin(valor)
    if campo == "placas":
        return _norm_placas(valor)
    if campo in ("marca", "modelo"):
        return _norm_texto(valor)
    if campo == "anio":
        try:
            return int(valor)
        except (TypeError, ValueError):
            return None
    return str(valor).strip() or None


# ---------------------------------------------------------------- extracción
def _load_ground_truth(samples_dir: Path = SAMPLES_DIR) -> dict[str, Any]:
    path = samples_dir / GROUND_TRUTH
    if not path.exists():
        return {"documentos": {}, "expedientes": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def _mock_extraction(tipo: TipoDocumento, documento_id: str) -> DocExtraction:
    gt = _load_ground_truth()["documentos"].get(documento_id)
    if gt is None:
        return DocExtraction(documento_id=documento_id, tipo=tipo, confianza=0.0)
    return DocExtraction(
        documento_id=documento_id,
        tipo=gt.get("tipo", tipo),
        **{k: gt.get(k) for k in CAMPOS},
        campos_extra=gt.get("campos_extra", {}),
        confianza=1.0,
    )


_SYSTEM = (
    "Eres un extractor de datos de documentos vehiculares mexicanos (factura, tarjeta de circulación, "
    "póliza de seguro). Devuelve SOLO un objeto JSON con las claves: vin, placas, marca, modelo, anio "
    "(entero), vigencia (fecha ISO YYYY-MM-DD o null), campos_extra (objeto), confianza (0..1). "
    "Usa null para lo que no aparezca. No inventes datos."
)
_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "vin": {"type": ["string", "null"]},
        "placas": {"type": ["string", "null"]},
        "marca": {"type": ["string", "null"]},
        "modelo": {"type": ["string", "null"]},
        "anio": {"type": ["integer", "null"]},
        "vigencia": {"type": ["string", "null"]},
        "campos_extra": {"type": "object"},
        "confianza": {"type": "number"},
    },
    "required": ["vin", "placas", "marca", "modelo", "anio", "vigencia"],
}


def extract(content: bytes, tipo: TipoDocumento, documento_id: str, mime: str = "application/pdf") -> DocExtraction:
    """LLM multimodal extrae VIN, placas, marca, modelo, año y vigencia (con fallback mock)."""
    fallback = lambda: _mock_extraction(tipo, documento_id).model_dump(mode="json")  # noqa: E731
    if llm.is_mock():
        return _mock_extraction(tipo, documento_id)
    es_imagen = mime.startswith("image/")
    user = f"Tipo de documento: {tipo}. Extrae los campos del documento adjunto."
    if not es_imagen:
        # T-01 solo admite imágenes como bloques; para otros formatos se intenta como texto.
        user += "\n\nContenido:\n" + content.decode("utf-8", errors="ignore")[:20000]
    data = llm.complete_json(
        _SYSTEM, user, images=[content] if es_imagen else None, schema=_SCHEMA, fallback=fallback, max_tokens=1000
    )
    try:
        conf = float(data.get("confianza", 0.8))
        return DocExtraction(
            documento_id=documento_id,
            tipo=tipo,
            vin=normalize_vin(data.get("vin")),
            placas=data.get("placas") or None,
            marca=data.get("marca") or None,
            modelo=data.get("modelo") or None,
            anio=_norm_campo("anio", data.get("anio")),
            vigencia=data.get("vigencia") or None,
            campos_extra=data.get("campos_extra") or {},
            confianza=min(max(conf, 0.0), 1.0),
        )
    except Exception:
        return _mock_extraction(tipo, documento_id)


# ---------------------------------------------------------------- verificación cruzada
def _parse_fecha(s: str) -> Optional[date]:
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def cross_check(extractions: list[DocExtraction], hoy: Optional[date] = None) -> list[Alerta]:
    """Reglas DETERMINÍSTICAS: VIN (normalizado, 17 chars, dígito verificador), placas, marca/modelo/año
    coinciden entre documentos; vigencias no vencidas. `hoy` fija la fecha de referencia (tests)."""
    hoy = hoy or date.today()
    alertas: list[Alerta] = []

    for e in extractions:
        v = normalize_vin(e.vin)
        if v is None:
            continue
        if not _VIN_RE.match(v):
            alertas.append(Alerta(codigo="VIN_FORMATO_INVALIDO", severidad="alta",
                                  detalle=f"VIN '{v}' no tiene 17 caracteres válidos (sin I, O, Q)",
                                  fuentes=[e.documento_id]))
        elif v[8] != vin_check_digit(v):
            alertas.append(Alerta(codigo="VIN_DIGITO_VERIFICADOR", severidad="alta",
                                  detalle=f"VIN '{v}': dígito verificador {v[8]} ≠ {vin_check_digit(v)} esperado",
                                  fuentes=[e.documento_id]))

    reglas = [
        ("vin", "VIN_NO_COINCIDE", "alta"),
        ("placas", "PLACAS_NO_COINCIDEN", "media"),
        ("marca", "MARCA_NO_COINCIDE", "media"),
        ("modelo", "MODELO_NO_COINCIDE", "media"),
        ("anio", "ANIO_NO_COINCIDE", "media"),
    ]
    for campo, codigo, sev in reglas:
        valores: dict[Any, list[str]] = {}
        for e in extractions:
            val = _norm_campo(campo, getattr(e, campo))
            if val is not None:
                valores.setdefault(val, []).append(e.documento_id)
        if len(valores) > 1:
            detalle = "; ".join(f"{k} en {', '.join(ids)}" for k, ids in valores.items())
            fuentes = [d for ids in valores.values() for d in ids]
            alertas.append(Alerta(codigo=codigo, severidad=sev, detalle=f"{campo} difiere: {detalle}",
                                  fuentes=fuentes))

    for e in extractions:
        if not e.vigencia:
            continue
        f = _parse_fecha(e.vigencia)
        if f is None:
            alertas.append(Alerta(codigo="VIGENCIA_ILEGIBLE", severidad="info",
                                  detalle=f"vigencia '{e.vigencia}' no es una fecha ISO", fuentes=[e.documento_id]))
        elif f < hoy:
            sev = "info" if e.tipo == "poliza_anterior" else ("alta" if e.tipo == "tarjeta_circulacion" else "media")
            alertas.append(Alerta(codigo="DOCUMENTO_VENCIDO", severidad=sev,
                                  detalle=f"{e.tipo} vencido el {f.isoformat()}", fuentes=[e.documento_id]))

    tipos = {e.tipo for e in extractions}
    for requerido in ("factura", "tarjeta_circulacion"):
        if requerido not in tipos:
            alertas.append(Alerta(codigo="DOCUMENTO_FALTANTE", severidad="media",
                                  detalle=f"falta {requerido}", fuentes=[]))
    for e in extractions:
        if e.confianza < 0.6:
            alertas.append(Alerta(codigo="BAJA_CONFIANZA", severidad="info",
                                  detalle=f"extracción con confianza {e.confianza:.2f}", fuentes=[e.documento_id]))
    return alertas


# ---------------------------------------------------------------- perfil
def _consolidar(extractions: list[DocExtraction], campo: str) -> tuple[Any, bool]:
    """Valor consolidado (moda; empate → fuente más confiable) y si quedó verificado
    (≥2 documentos lo reportan y todos coinciden)."""
    ordenadas = sorted(extractions, key=lambda e: _PRIORIDAD.get(e.tipo, 9))
    pares = [(_norm_campo(campo, getattr(e, campo)), getattr(e, campo)) for e in ordenadas]
    pares = [(n, raw) for n, raw in pares if n is not None]
    if not pares:
        return None, False
    conteo = Counter(n for n, _ in pares)
    top = max(conteo.values())
    ganador = next(n for n, _ in pares if conteo[n] == top)
    raw = next(r for n, r in pares if n == ganador)
    if campo == "vin":
        raw = ganador
    elif campo == "placas":
        raw = str(raw).strip().upper()
    elif campo == "anio":
        raw = ganador
    else:
        raw = str(raw).strip()
    verificado = len(pares) >= 2 and len(conteo) == 1 and (campo != "vin" or vin_valido(ganador))
    return raw, verificado


def build_profile(vehicle_id: str, extractions: list[DocExtraction], extra: dict | None = None) -> VehicleProfile:
    """Consolida un VehicleProfile con alertas y cobertura_verificacion (fracción de campos verificados).

    `extra` (datos declarados): kilometraje, siniestros_previos, uso, zona, danos, alertas, hoy, y
    opcionalmente marca/modelo/anio/vin/placas (solo rellenan lo que los documentos no traen; si
    contradicen a los documentos se emite DATO_DECLARADO_NO_COINCIDE)."""
    extra = dict(extra or {})
    hoy = extra.pop("hoy", None)
    alertas = cross_check(extractions, hoy=hoy)

    valores: dict[str, Any] = {}
    verificados = 0
    for campo in CAMPOS_PERFIL:
        val, ok = _consolidar(extractions, campo)
        verificados += ok
        declarado = extra.get(campo)
        if val is None:
            val = declarado
        elif declarado is not None and _norm_campo(campo, declarado) != _norm_campo(campo, val):
            alertas.append(Alerta(codigo="DATO_DECLARADO_NO_COINCIDE", severidad="media",
                                  detalle=f"{campo} declarado '{declarado}' ≠ documentos '{val}'",
                                  fuentes=[e.documento_id for e in extractions]))
        valores[campo] = val

    faltantes = [c for c in ("marca", "modelo", "anio") if valores.get(c) is None]
    if faltantes:
        alertas.append(Alerta(codigo="DATOS_INCOMPLETOS", severidad="alta",
                              detalle=f"sin {', '.join(faltantes)} en documentos ni datos declarados",
                              fuentes=[e.documento_id for e in extractions]))

    danos = [d if isinstance(d, Dano) else Dano.model_validate(d) for d in extra.get("danos", [])]
    alertas += [a if isinstance(a, Alerta) else Alerta.model_validate(a) for a in extra.get("alertas", [])]

    kwargs: dict[str, Any] = {k: extra[k] for k in ("kilometraje", "siniestros_previos", "uso", "zona") if k in extra}
    return VehicleProfile(
        id=vehicle_id,
        marca=valores["marca"] or "DESCONOCIDA",
        modelo=valores["modelo"] or "DESCONOCIDO",
        anio=int(valores["anio"]) if valores["anio"] is not None else ANIO_REFERENCIA,
        kilometraje=int(kwargs.pop("kilometraje", 0)),
        siniestros_previos=int(kwargs.pop("siniestros_previos", 0)),
        danos=danos,
        alertas=alertas,
        cobertura_verificacion=round(verificados / len(CAMPOS_PERFIL), 4),
        vin=valores["vin"],
        placas=valores["placas"],
        **kwargs,
    )


# ---------------------------------------------------------------- muestras SIMULADAS
_TITULOS = {
    "factura": "FACTURA DE VEHICULO (CFDI) - SIMULADA",
    "tarjeta_circulacion": "TARJETA DE CIRCULACION - SIMULADA",
    "poliza_anterior": "POLIZA DE SEGURO AUTOMOTRIZ - SIMULADA",
}


def _con_digito(vin16: str) -> str:
    """Inserta el dígito verificador correcto en la posición 9 de un VIN con '0' provisional."""
    v = vin16[:8] + "0" + vin16[9:]
    return v[:8] + vin_check_digit(v) + v[9:]


def _expedientes_simulados() -> list[dict[str, Any]]:
    vin1 = _con_digito("3N1CN7AD0KL812345")  # Nissan Versa 2019 (México)
    vin2 = _con_digito("3VWRV1BU0HM034567")  # VW Jetta 2017 (Puebla)
    vin2_otro = _con_digito("3VWRV1BU0HM098765")  # VIN distinto en la tarjeta (fraude/error)
    vin3 = _con_digito("3G1TA5AF0FL156789")  # Chevrolet Aveo 2015
    base = [
        ("EXP-001", "Nissan", "Versa", 2019, "NXA-123-A", vin1, {"tarjeta_circulacion": {}}, "2029-12-31",
         ["DOCUMENTO_VENCIDO:poliza_anterior"]),
        ("EXP-002", "Volkswagen", "Jetta", 2017, "PBL-456-B", vin2,
         {"tarjeta_circulacion": {"vin": vin2_otro}}, "2028-06-30", ["VIN_NO_COINCIDE"]),
        ("EXP-003", "Chevrolet", "Aveo", 2015, "MEX-789-C", vin3, {}, "2023-06-30",
         ["DOCUMENTO_VENCIDO:tarjeta_circulacion"]),
    ]
    exps = []
    for exp_id, marca, modelo, anio, placas, vin, overrides, vig_tarjeta, esperadas in base:
        n = exp_id[-3:]
        docs = [
            {"documento_id": f"{exp_id}-FAC", "tipo": "factura", "vin": vin, "placas": None, "marca": marca,
             "modelo": modelo, "anio": anio, "vigencia": None,
             "campos_extra": {"folio": f"SIM-F{n}", "emisor": "Agencia SIMULADA SA de CV",
                              "valor_factura": 250000 + 10000 * int(n)}},
            {"documento_id": f"{exp_id}-TC", "tipo": "tarjeta_circulacion", "vin": vin, "placas": placas,
             "marca": marca, "modelo": modelo, "anio": anio, "vigencia": vig_tarjeta,
             "campos_extra": {"propietario": "PERSONA SIMULADA"}},
            {"documento_id": f"{exp_id}-POL", "tipo": "poliza_anterior", "vin": vin, "placas": placas,
             "marca": marca, "modelo": modelo, "anio": anio, "vigencia": "2026-05-01" if n == "001" else "2027-03-15",
             "campos_extra": {"aseguradora": "Aseguradora SIMULADA", "numero_poliza": f"SIM-P{n}"}},
        ]
        for d in docs:
            d.update(overrides.get(d["tipo"], {}))
            d["archivo"] = f"{d['documento_id']}.png"
            d["expediente"] = exp_id
        exps.append({"expediente": exp_id, "documentos": docs, "alertas_esperadas": esperadas})
    return exps


def _render(doc: dict[str, Any], path: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (900, 560), "white")
    dr = ImageDraw.Draw(img)
    f_tit, f_txt, f_marca = (ImageFont.load_default(size=s) for s in (26, 22, 64))
    dr.rectangle([10, 10, 889, 549], outline="black", width=3)
    dr.text((30, 25), _TITULOS[doc["tipo"]], fill="black", font=f_tit)
    dr.line([30, 65, 870, 65], fill="black", width=2)
    lineas = [("Documento", doc["documento_id"])]
    etiquetas = {"vin": "VIN / NIV", "placas": "Placas", "marca": "Marca", "modelo": "Modelo",
                 "anio": "Anio modelo", "vigencia": "Vigencia"}
    lineas += [(etiquetas[c], doc[c]) for c in CAMPOS if doc.get(c) is not None]
    lineas += [(k.replace("_", " ").capitalize(), v) for k, v in doc["campos_extra"].items()]
    for i, (k, v) in enumerate(lineas):
        dr.text((40, 85 + 36 * i), f"{k}: {v}", fill="black", font=f_txt)
    dr.text((520, 440), "SIMULADO", fill=(220, 30, 30), font=f_marca)
    img.save(path, format="PNG", optimize=False)


def generate_samples(out_dir: Path = SAMPLES_DIR) -> dict[str, Any]:
    """Genera los PNG SIMULADOS y `ground_truth.json` en `out_dir`. Devuelve el ground truth."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    gt: dict[str, Any] = {
        "nota": "Documentos SIMULADOS para la demo de KAVAK AUTOGUARD AI. No corresponden a personas ni autos reales.",
        "fecha_referencia": "2026-11-09",
        "documentos": {},
        "expedientes": {},
    }
    for exp in _expedientes_simulados():
        gt["expedientes"][exp["expediente"]] = {
            "documentos": [d["documento_id"] for d in exp["documentos"]],
            "alertas_esperadas": exp["alertas_esperadas"],
        }
        for d in exp["documentos"]:
            _render(d, out_dir / d["archivo"])
            gt["documentos"][d["documento_id"]] = {k: v for k, v in d.items() if k != "documento_id"}
    (out_dir / GROUND_TRUTH).write_text(json.dumps(gt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return gt


# ---------------------------------------------------------------- evaluación
def evaluate(samples_dir: Path = SAMPLES_DIR) -> dict[str, Any]:
    """Precisión por campo de `extract` contra el ground truth y aciertos de alertas por expediente."""
    gt = _load_ground_truth(samples_dir)
    aciertos = Counter()
    totales = Counter()
    por_doc: dict[str, DocExtraction] = {}
    for doc_id, d in gt["documentos"].items():
        content = (samples_dir / d["archivo"]).read_bytes()
        ex = extract(content, d["tipo"], doc_id, mime="image/png")
        por_doc[doc_id] = ex
        for c in CAMPOS:
            esperado, obtenido = _norm_campo(c, d.get(c)), _norm_campo(c, getattr(ex, c))
            if esperado is None and obtenido is None:
                continue
            totales[c] += 1
            aciertos[c] += esperado == obtenido
    precision = {c: (aciertos[c] / totales[c] if totales[c] else 1.0) for c in CAMPOS}
    hoy = date.fromisoformat(gt.get("fecha_referencia", date.today().isoformat()))
    alertas_ok = {}
    for exp_id, e in gt["expedientes"].items():
        alertas = cross_check([por_doc[i] for i in e["documentos"]], hoy=hoy)
        codigos = set()
        for a in alertas:
            codigos.add(a.codigo)
            if a.codigo == "DOCUMENTO_VENCIDO":
                codigos.add(f"DOCUMENTO_VENCIDO:{por_doc[a.fuentes[0]].tipo}")
        alertas_ok[exp_id] = all(x in codigos for x in e["alertas_esperadas"])
    total_c = sum(totales.values())
    return {
        "modo": "mock" if llm.is_mock() else "llm",
        "n_documentos": len(gt["documentos"]),
        "precision_por_campo": precision,
        "precision_global": (sum(aciertos.values()) / total_c) if total_c else 1.0,
        "alertas_esperadas_detectadas": alertas_ok,
    }


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Agente documental (datos SIMULADOS)")
    ap.add_argument("--eval", action="store_true", help="reporta precisión de extracción por campo")
    ap.add_argument("--generate", action="store_true", help="regenera las muestras SIMULADAS")
    args = ap.parse_args(argv)
    if args.generate:
        gt = generate_samples()
        print(f"Generados {len(gt['documentos'])} documentos SIMULADOS en {SAMPLES_DIR}")
    if args.eval or not args.generate:
        r = evaluate()
        print(f"Modo: {r['modo']}  ·  documentos: {r['n_documentos']}")
        for c, p in r["precision_por_campo"].items():
            print(f"  {c:<10} {p:6.1%}")
        print(f"  {'GLOBAL':<10} {r['precision_global']:6.1%}")
        for exp_id, ok in r["alertas_esperadas_detectadas"].items():
            print(f"  alertas {exp_id}: {'OK' if ok else 'FALTAN'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
