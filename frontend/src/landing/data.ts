// Resultados medidos reales del prototipo (modo mock, 60 lotes × 200 pólizas, semillas fijas).
// Fuente: corridas del experimento de ablación del RSI. Montos en MXN de pérdida asimétrica acumulada.

export interface CorridaRegret {
  seed: number;
  estatico: number;
  parametros: number;
  rsi: number;
}

export const CORRIDAS: CorridaRegret[] = [
  { seed: 42, estatico: 51_310_000, parametros: 44_010_000, rsi: 36_730_000 },
  { seed: 1, estatico: 51_180_000, parametros: 42_610_000, rsi: 37_930_000 },
  { seed: 7, estatico: 50_980_000, parametros: 43_500_000, rsi: 37_000_000 },
  { seed: 123, estatico: 51_050_000, parametros: 42_050_000, rsi: 36_160_000 },
];

/** Cambio relativo frente a reglas fijas (negativo = menos pérdida). */
export const delta = (v: number, base: number) => v / base - 1;

export const RANGO_RSI = (() => {
  const ds = CORRIDAS.map((c) => delta(c.rsi, c.estatico));
  return { mejor: Math.min(...ds), peor: Math.max(...ds) };
})();

export const RANGO_PARAM = (() => {
  const ds = CORRIDAS.map((c) => delta(c.parametros, c.estatico));
  return { mejor: Math.min(...ds), peor: Math.max(...ds) };
})();
