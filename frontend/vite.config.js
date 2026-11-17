import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 开发时把 /api 和 /health 代理到后端，浏览器不跨域；
// 生产部署时由 Nginx 做同样的转发，前端代码不用改。
// 后端地址可用环境变量 BACKEND_URL 覆盖（默认 127.0.0.1:8000）。
const target = process.env.BACKEND_URL || 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target, changeOrigin: true },
      '/health': { target, changeOrigin: true },
    },
  },
})