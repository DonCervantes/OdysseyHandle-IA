/** Tokens del sistema de diseño (ver src/index.css). Estilo cálido y claro, inspirado en la referencia. */
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: "rgb(var(--paper) / <alpha-value>)",
        cream: "rgb(var(--cream) / <alpha-value>)",
        panel: "rgb(var(--panel) / <alpha-value>)",
        line: "rgb(var(--line) / <alpha-value>)",
        ink: "rgb(var(--ink) / <alpha-value>)",
        muted: "rgb(var(--muted) / <alpha-value>)",
        faint: "rgb(var(--faint) / <alpha-value>)",
        taupe: "rgb(var(--taupe) / <alpha-value>)",
        sand: "rgb(var(--sand) / <alpha-value>)",
        ok: "rgb(var(--ok) / <alpha-value>)",
        warn: "rgb(var(--warn) / <alpha-value>)",
        alta: "rgb(var(--alta) / <alpha-value>)",
        info: "rgb(var(--info) / <alpha-value>)",
      },
      fontFamily: {
        sans: ["Outfit", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      borderRadius: { xl2: "14px" },
      boxShadow: {
        soft: "0 1px 2px rgba(40, 32, 20, 0.04), 0 8px 24px -12px rgba(40, 32, 20, 0.12)",
        frame: "0 30px 80px -40px rgba(60, 45, 25, 0.35)",
      },
      maxWidth: { page: "1200px" },
    },
  },
  plugins: [],
};
