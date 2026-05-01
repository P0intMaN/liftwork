import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
const API_TARGET = process.env.LIFTWORK_API_URL ?? "http://localhost:7878";
// https://vite.dev/config/
export default defineConfig({
    plugins: [react()],
    resolve: {
        alias: {
            "@": path.resolve(__dirname, "./src"),
        },
    },
    server: {
        port: 5173,
        strictPort: true,
        // Proxy API + SSE so the browser stays same-origin in dev. CORS is also
        // enabled on the API for direct cross-origin calls during cypress / e2e.
        proxy: {
            "/api": {
                target: API_TARGET,
                changeOrigin: true,
                rewrite: (p) => p.replace(/^\/api/, ""),
                // SSE needs HTTP/1.1 keep-alive, which the default proxy supports.
            },
        },
    },
    build: {
        outDir: "dist",
        sourcemap: true,
    },
});
