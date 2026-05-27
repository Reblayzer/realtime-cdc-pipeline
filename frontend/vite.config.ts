import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Vite dev server: in compose we expose port 5173 directly.
// In production we serve a static build via nginx (see Dockerfile).
export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    // During dev, hit the backend through Vite's proxy so the browser doesn't
    // need to know about CORS. In production (nginx), nginx does the proxy.
    proxy: {
      "/api": {
        target: "http://backend:8000",
        changeOrigin: true,
      },
    },
  },
});
