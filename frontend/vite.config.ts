import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 4173,
    strictPort: true,
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
});
