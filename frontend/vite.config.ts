import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In development the API runs on the host (docker compose publishes 8001).
const api = "http://127.0.0.1:8001";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": api,
      "/health": api,
      "/metrics": api,
      "/docs": api,
      "/openapi.json": api,
    },
  },
});
