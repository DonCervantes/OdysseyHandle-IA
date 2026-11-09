// Cifras públicas de México usadas en la narrativa. CADA cifra lleva su fuente (url) y fecha.
// No agregar cifras sin fuente verificable. Las de abajo vienen del plan del proyecto
// (KAVAK_AUTOGUARD_AI_Plan_de_trabajo.md), ya revisadas por el equipo.

export interface Dato {
  id: string;
  valor: string;        // cómo se muestra (p.ej. "7 de cada 10")
  titulo: string;       // qué es, en una frase corta
  detalle: string;      // contexto en una o dos frases
  fuente: string;       // nombre del medio u organismo
  url: string;
  fecha: string;        // "jul 2026"
}

export const DATOS_MEXICO: Dato[] = [
  {
    id: "sin-seguro",
    valor: "7 de cada 10",
    titulo: "vehículos circulan sin seguro",
    detalle: "De 58.2 millones de vehículos registrados (INEGI, 2023), la AMIS estima que solo 30% tiene póliza.",
    fuente: "Animal Político",
    url: "https://grupoanimal.mx/hablemos-de/mexico-mas-vehiculos-pocos-seguros-qualitas-record",
    fecha: "jul 2026",
  },
  {
    id: "robos",
    valor: "139 al día",
    titulo: "autos asegurados robados",
    detalle: "Entre julio de 2025 y junio de 2026 se robaron 50,891 autos asegurados.",
    fuente: "Animal Político",
    url: "https://grupoanimal.mx/hablemos-de/mexico-mas-vehiculos-pocos-seguros-qualitas-record",
    fecha: "jul 2026",
  },
  {
    id: "colisiones",
    valor: "566,820",
    titulo: "colisiones con autos asegurados",
    detalle: "Registradas entre enero y noviembre de 2025.",
    fuente: "Animal Político",
    url: "https://grupoanimal.mx/hablemos-de/mexico-mas-vehiculos-pocos-seguros-qualitas-record",
    fecha: "jul 2026",
  },
  {
    id: "montachoques",
    valor: "+5% a 10%",
    titulo: "más fraudes de “montachoques”",
    detalle: "Alza reportada por la AMIS en el primer semestre de 2026; los delincuentes buscan autos sin seguro.",
    fuente: "Expansión",
    url: "https://expansion.mx/economia/2026/07/15/suben-10-los-montachoques-en-2026-y-aseguradoras-piden-tipificar-el-delito-en-todo-el-pais",
    fecha: "jul 2026",
  },
];
