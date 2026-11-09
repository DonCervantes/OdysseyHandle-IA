# Cotas del Gate 2 (T-23) — scripts de medición, NO es código del producto

Correr desde la raíz del repo con `PYTHONPATH=.` (modo mock, sin red):

- `bound.py SEED` — regret del estático vs oráculo calibrado (costo esperado real × cuantil 0.6) en la
  secuencia de 60×200 pólizas. Mejora máxima posible: 44.3% (seed 42), 43.7% (1), 44.8% (7), 44.1% (123).
- `ceiling.py SEED` — descenso por coordenadas ideal con la estructura VERDADERA, entrenando con todas vs
  solo las vendidas: con solo vendidas llega a +0.6% del oráculo ⇒ la censura por ventas no es el límite.
- `ideal_online.py SEED` — aprendiz online ideal (conoce la estructura, reajusta todo cada K=3 lotes con
  las ventas train, sin holdout/δ/ε): 40.6% (42), 39.3% (1), 40.3% (7), 39.7% (123). Usa `ceiling_lib.py`.
