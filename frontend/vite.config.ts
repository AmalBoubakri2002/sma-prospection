import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        // Indispensable pour /api/v1/notifications/ws : sans ce flag, le proxy
        // Vite ne transmet pas l'upgrade WebSocket et la connexion échoue en dev.
        ws: true,
      },
    },
  },
});
