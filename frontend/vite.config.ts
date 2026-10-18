/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  // One .env file at the project root is shared by backend and frontend.
  envDir: "..",
  plugins: [react(), tailwindcss()],
  server: {
    // 5174 so this app can run next to another Vite app on the default 5173.
    port: 5174,
    strictPort: true,
    host: true,
    // File-change events don't cross the Docker-on-Windows boundary, so poll there.
    watch: process.env.VITE_USE_POLLING === "true" ? { usePolling: true, interval: 300 } : undefined,
  },
  build: {
    rollupOptions: {
      output: {
        // Separate, cacheable bundles for the big libraries.
        manualChunks: {
          react: ["react", "react-dom", "react-router"],
          firebase: ["firebase/app", "firebase/auth"],
          charts: ["lightweight-charts"],
        },
      },
    },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
