import { fileURLToPath, URL } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  base: "/admin/",
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://127.0.0.1:19453",
      "/admin/api": "http://127.0.0.1:19453",
    },
  },
  build: {
    outDir: fileURLToPath(new URL("../python-backend/app/admin_static", import.meta.url)),
    emptyOutDir: true,
    sourcemap: false,
    // Ant Design contains internal module cycles. Size-based forced splitting can
    // reorder their initialization and leave the production page completely blank.
    chunkSizeWarningLimit: 1_200,
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    globals: true,
    css: true,
    pool: "threads",
    maxWorkers: 1,
    fileParallelism: false,
  },
});
