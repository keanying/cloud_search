import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 5173,
    proxy: {
      // 后端端口由 run.py --dev 通过 CS_API_PORT 传入（默认 8000）
      '/api': { target: `http://127.0.0.1:${process.env.CS_API_PORT || 8000}`, changeOrigin: true },
    },
  },
})
