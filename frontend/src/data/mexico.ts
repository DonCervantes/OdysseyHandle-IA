// Cifras públicas de México usadas en la narrativa. CADA cifra lleva su fuente (url) y fecha.
// No agregar cifras sin fuente verificable. Todas se revisaron abriendo la URL citada (nov 2026):
// el número aparece en la página. Orden: del problema a la oportunidad.

export interface Dato {
  id: string;
  valor: string;        // cómo se muestra (p.ej. "7 de cada 10")
  titulo: string;       // qué es, en una frase corta
  detalle: string;      // contexto en una o dos frases
  fuente: string;       // nombre del medio u organismo
  url: string;
  fecha: string;        // fecha de publicación de la fuente, "jul 2026"
  origen?: string;      // organismo que generó el dato, si la fuente es un medio (p.ej. "AMIS")
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
    origen: "INEGI y AMIS",
  },
  {
    id: "informalidad",
    valor: "10%",
    titulo: "de la compraventa de usados pasa por el mercado formal",
    detalle: "El mercado formal representa apenas 10%; la gran mayoría de las operaciones ocurre fuera de él, sobre todo entre particulares.",
    fuente: "Expansión",
    url: "https://expansion.mx/empresas/2026/10/28/autos-chinos-mercado-seminuevos-mexico-kavak",
    fecha: "oct 2026",
    origen: "The CIU y Kavak",
  },
  {
    id: "robos",
    valor: "139 al día",
    titulo: "autos asegurados robados",
    detalle: "Entre julio de 2025 y junio de 2026 se robaron 50,891 autos asegurados.",
    fuente: "Animal Político",
    url: "https://grupoanimal.mx/hablemos-de/mexico-mas-vehiculos-pocos-seguros-qualitas-record",
    fecha: "jul 2026",
    origen: "AMIS",
  },
  {
    id: "robo-violencia",
    valor: "53%",
    titulo: "de los robos de autos asegurados fue con violencia",
    detalle: "Promedio nacional en el último año (53.04%), frente a 57.9% un año antes.",
    fuente: "La Razón",
    url: "https://www.razon.com.mx/negocios/2026/07/16/robo-de-vehiculos-baja-162-en-el-ultimo-ano/",
    fecha: "jul 2026",
    origen: "AMIS",
  },
  {
    id: "recuperacion",
    valor: "45%",
    titulo: "de los autos asegurados robados se recupera",
    detalle: "Tasa nacional de febrero de 2025 a enero de 2026: unos 24,143 vehículos. Más de la mitad no aparece.",
    fuente: "Expansión",
    url: "https://expansion.mx/empresas/2026/07/13/autos-mas-robados-en-mexico-2026",
    fecha: "jul 2026",
    origen: "AMIS",
  },
  {
    id: "colisiones",
    valor: "566,820",
    titulo: "colisiones con autos asegurados",
    detalle: "Registradas entre enero y noviembre de 2025.",
    fuente: "Animal Político",
    url: "https://grupoanimal.mx/hablemos-de/mexico-mas-vehiculos-pocos-seguros-qualitas-record",
    fecha: "jul 2026",
    origen: "AMIS",
  },
  {
    id: "montachoques",
    valor: "+5% a 10%",
    titulo: "más fraudes de “montachoques”",
    detalle: "Es una estimación de la AMIS para el primer semestre de 2026, no una cifra precisa: no hay registro oficial. Los delincuentes buscan autos sin seguro.",
    fuente: "Expansión",
    url: "https://expansion.mx/economia/2026/07/15/suben-10-los-montachoques-en-2026-y-aseguradoras-piden-tipificar-el-delito-en-todo-el-pais",
    fecha: "jul 2026",
    origen: "AMIS",
  },
  {
    id: "poliza-basica",
    valor: "$3,000 a $7,000",
    titulo: "al año cuesta una póliza básica de daños a terceros",
    detalle: "Según el modelo del vehículo y la zona donde circula.",
    fuente: "El Imparcial",
    url: "https://www.elimparcial.com/dinero/2026/06/09/los-accidentes-viales-en-mexico-podrian-aumentar-hasta-20-por-el-mundial-2026-debido-al-alza-en-la-movilidad-un-riesgo-patrimonial-ante-el-dato-de-que-el-73-de-los-autos-circula-sin-seguro/",
    fecha: "jun 2026",
    origen: "Condusef",
  },
  {
    id: "mercado-usados",
    valor: "4.67 millones",
    titulo: "compraventas de autos usados previstas en 2026",
    detalle: "Un 66.8% más que los 2.8 millones de 2016; la previsión llega a 5.42 millones en 2030.",
    fuente: "Expansión",
    url: "https://expansion.mx/empresas/2026/10/28/autos-chinos-mercado-seminuevos-mexico-kavak",
    fecha: "oct 2026",
  },
  {
    id: "seminuevos-financiados",
    valor: "153,009",
    titulo: "seminuevos vendidos con crédito en 2025",
    detalle: "Récord anual, 3.4% más que en 2024. Cada crédito necesita una valuación y un seguro confiables.",
    fuente: "Milenio",
    url: "https://amp.milenio.com/negocios/cuantos-autos-seminuevos-se-financiaron-en-mexico-en-2025",
    fecha: "mar 2026",
    origen: "AMDA",
  },
];
