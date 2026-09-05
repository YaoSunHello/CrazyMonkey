import react from "@vitejs/plugin-react";
import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";

export default defineConfig(({ mode }) => {
  const backendOrigin = loadEnv(mode, ".", "").CRAZYMONKEY_BACKEND_ORIGIN || "http://127.0.0.1:8000";
  return {
    plugins: [react()],
    server: {
      port: 4173,
      strictPort: true,
      proxy: {
        "/api": backendOrigin,
        "/health": backendOrigin,
      },
    },
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: "./src/test/setup.ts",
      css: true,
      // The interaction-heavy review tests can exceed Vitest's 5 s default on
      // busy hackathon laptops even though the same browser flow is responsive.
      testTimeout: 15_000,
    },
  };
});
