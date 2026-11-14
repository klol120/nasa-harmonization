import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// base "./" keeps the build portable (GitHub Pages subpath or opened from a local folder).
export default defineConfig({
  base: "./",
  plugins: [react()],
  server: { port: 5173 },
  build: {
    chunkSizeWarningLimit: 1100,
    rollupOptions: {
      output: {
        // Big libraries in their own cached chunks.
        manualChunks: { maplibre: ["maplibre-gl"], echarts: ["echarts", "zrender"], react: ["react", "react-dom"] },
      },
    },
  },
});
