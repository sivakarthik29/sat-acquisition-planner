import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In development the UI runs on :5173 and proxies /api to the backend on :8000.
// `npm run build` writes into the backend package so one process serves both.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://localhost:8000' } },
  build: { outDir: '../backend/app/static', emptyOutDir: true },
})
