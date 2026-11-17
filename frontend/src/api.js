import axios from 'axios'

// 相对路径：开发走 Vite 代理，生产走 Nginx 转发，两种环境同一份代码。
// 后端最坏情况（150s 超时 × SDK 重试 1 次）约 300s，这里留 320s。
const http = axios.create({ baseURL: '', timeout: 320000 })

export function createDietPlan(payload) {
  return http.post('/api/diet-plans', payload).then((r) => r.data)
}

export function getDietPlan(id) {
  return http.get(`/api/diet-plans/${id}`).then((r) => r.data)
}

export function checkHealth() {
  return http.get('/health').then((r) => r.data)
}