import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The dev server proxies /api to the FastAPI backend so frontend and API share
// an origin in development — no day-to-day CORS configuration required.
const API_TARGET = process.env.VITE_API_TARGET ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Bind both loopback families: Vite 8 defaults to IPv6-only, which makes
    // http://127.0.0.1:5173 unreachable on machines resolving to IPv4 first.
    host: "127.0.0.1",
    proxy: {
      "/api": {
        target: API_TARGET,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
    rollupOptions: {
      output: {
        // Monaco is large and rarely changes; splitting it keeps the app chunk
        // small and cacheable across deploys.
        manualChunks(id) {
          if (id.includes("monaco-editor")) return "monaco";
          if (id.includes("react-dom") || id.includes("/react/") || id.includes("react-router")) {
            return "react";
          }
          return undefined;
        },
      },
    },
  },
});
