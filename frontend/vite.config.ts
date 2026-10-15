import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
  },
  build: {
    // dist/ is the live IIS site root and also holds IIS-managed files
    // (web.config, aspnet_client). Never wipe it on build — only overwrite
    // index.html and the assets/ folder below.
    emptyOutDir: false,
  },
});
