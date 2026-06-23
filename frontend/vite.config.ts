import { defineConfig, lazyPlugins } from "vite-plus";
import react from "@vitejs/plugin-react";

export default defineConfig({
  fmt: {},
  lint: {
    jsPlugins: [{ name: "vite-plus", specifier: "vite-plus/oxlint-plugin" }],
    rules: { "vite-plus/prefer-vite-plus-imports": "error" },
    options: { typeAware: true, typeCheck: true },
  },
  plugins: lazyPlugins(() => [react()]),
  server: {
    port: 5173,
    proxy: {
      "/ask": "http://127.0.0.1:8010",
      "/health": "http://127.0.0.1:8010",
      "/auth": "http://127.0.0.1:8010",
      "/dashboard/stats": "http://127.0.0.1:8010",
      "/dashboard/entities": "http://127.0.0.1:8010",
      "/dashboard/relations": "http://127.0.0.1:8010",
      "/dashboard/chunks": "http://127.0.0.1:8010",
      "/dashboard/graph-data": "http://127.0.0.1:8010",
      "/dashboard/settings": "http://127.0.0.1:8010",
      "/dashboard/eval-models": "http://127.0.0.1:8010",
      "/dashboard/eval-questions": "http://127.0.0.1:8010",
      "/dashboard/eval/run": "http://127.0.0.1:8010",
      "/dashboard/eval/runs": "http://127.0.0.1:8010",
      "/dashboard/returns": "http://127.0.0.1:8010",
      "/dashboard/aliases": "http://127.0.0.1:8010",
    },
  },
});
