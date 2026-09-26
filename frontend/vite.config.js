import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// В разработке запросы /api проксируются на бэкенд (по умолчанию localhost:8000),
// поэтому фронтенд и API работают с одного адреса без настройки CORS.
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      '/api': process.env.VITE_API_TARGET || 'http://localhost:8000',
    },
  },
})
