import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(process.cwd(), "./src"),
    },
  },
  build: {
    // Fail the build if a chunk balloons unexpectedly (bundle-size guard).
    chunkSizeWarningLimit: 600,
    // Split heavy, cache-stable vendor code into its own long-lived chunk so
    // app updates don't force users to re-download React / jsPDF.
    rollupOptions: {
      output: {
        // Written as a function, not an object. Vite 8 / Rolldown dropped the
        // object form ({ chunkName: [packages] }) and fails the build with
        // "TypeError: manualChunks is not a function". The function form works
        // in every Vite version, so it is the portable choice.
        manualChunks(id) {
          if (!id.includes("node_modules")) return;
          // Anchored to the package directory so a path merely containing
          // "react" (e.g. a plugin) can't land in the wrong chunk.
          if (/[\\/]node_modules[\\/](react|react-dom|scheduler)[\\/]/.test(id)) {
            return "react";
          }
          if (/[\\/]node_modules[\\/]jspdf[\\/]/.test(id)) {
            return "pdf";
          }
        },
      },
    },
  },
  server: {
    port: 5173,
  },
  preview: {
    port: 4173,
  },
});