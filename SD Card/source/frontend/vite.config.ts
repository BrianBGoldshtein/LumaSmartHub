import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    target: "es2022",
    sourcemap: true,
    assetsInlineLimit: 4096,
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8742",
    },
  },
});
