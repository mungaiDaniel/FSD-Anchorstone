import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      // Proxy API requests to Flask backend during development
      "/api": {
        target: "http://localhost:4455",
        changeOrigin: true,
        secure: false,
      },
    },
  },
  build: {
    sourcemap: false, // No source maps in production
    rollupOptions: {
      output: {
        manualChunks: {
          // Split vendor chunks for better caching
          "chart-vendor": ["chart.js", "react-chartjs-2"],
          "table-vendor": ["@tanstack/react-table"],
          "form-vendor": ["react-hook-form", "@hookform/resolvers", "zod"],
        },
      },
    },
  },
});
