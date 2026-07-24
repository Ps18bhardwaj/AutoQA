import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    port: 5173,
    proxy: {
      // API calls to the FastAPI backend during dev.
      "/api": {
        target: "http://localhost:8003",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
      },
      // Streamed screenshots are served root-relative at /runs/... (no rewrite).
      "/runs": {
        target: "http://localhost:8003",
        changeOrigin: true,
      },
    },
  },
});
