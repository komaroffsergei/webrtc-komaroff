import { defineConfig } from "vite";

const CORE_TARGET =
  process.env.CORE_ORIGIN ??
  process.env.VITE_CORE_ORIGIN ??
  "http://localhost:8000";

export default defineConfig({
  root: ".",
  build: {
    outDir: "dist",
    sourcemap: true,
  },
  server: {
    port: 5173,
    host: "0.0.0.0",
    proxy: {
      "/core": {
        target: CORE_TARGET,
        changeOrigin: true,
      },
      "/offer": {
        target: CORE_TARGET,
        changeOrigin: true,
      },
      "/message": {
        target: CORE_TARGET,
        changeOrigin: true,
      },
      "/events": {
        target: CORE_TARGET,
        changeOrigin: true,
        ws: false,
      },
    },
  },
});
