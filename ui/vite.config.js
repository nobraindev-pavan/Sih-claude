import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The API and the built UI are served from one origin in production, so the
// dev server proxies /api instead of us explaining CORS on stage.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true } },
  },
  build: { outDir: 'dist', emptyOutDir: true },
})
