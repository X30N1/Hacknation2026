import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Backend FastAPI (osoba 1) nasłuchuje na :8000. W trybie mock (VITE_API_MOCK=1) proxy nie jest używane.
// Backend nie ma prefiksu /api (ścieżki jak w backend/docs/APIDOC.md), więc proxy go obcina.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
