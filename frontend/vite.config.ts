import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Frontend local: la API FastAPI corre aparte (por defecto http://localhost:8000, ver VITE_API_URL).
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: false },
});
