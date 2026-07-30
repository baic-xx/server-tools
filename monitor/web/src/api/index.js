import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 10000,
  withCredentials: true,
})

// ─── 前端刷新间隔（毫秒）───
export const REFRESH = {
  DASHBOARD: 5 * 60 * 1000,    // 服务器卡片、统计概览：5 分钟
  GPU: 5 * 60 * 1000,           // GPU 曲线、排行：5 分钟
  OFFLINE: 5 * 60 * 1000,      // 离线记录：5 分钟
  DETAIL: 30 * 1000,            // 服务器详情页：30 秒
}

// ─── 服务器相关 ───

/** 获取当前登录态 */
export const getMe = () => api.get('/auth/me')

/** 登录 */
export const login = (password) => api.post('/auth/login', { password })

/** 登出 */
export const logout = () => api.post('/auth/logout')

/** 获取所有服务器列表 */
export const getServers = () => api.get('/servers')

/** 获取单台服务器详情 */
export const getServer = (hostname) => api.get(`/servers/${hostname}`)

/** 获取服务器历史监控数据 */
export const getMetrics = (hostname, hours = 24) =>
  api.get(`/servers/${hostname}/metrics`, { params: { hours } })

/** 获取服务器最新监控数据 */
export const getLatestMetrics = (hostname) =>
  api.get(`/servers/${hostname}/metrics/latest`)

/** 获取总览统计 */
export const getOverview = () => api.get('/stats/overview')

/** 获取离线记录 */
export const getOfflineEvents = (days = 7) =>
  api.get('/offline-events', { params: { days } })

/** 获取 GPU 使用率排行 */
export const getGpuRanking = (hours = 6) =>
  api.get('/gpu-ranking', { params: { hours } })

/** 获取 GPU 总体平均使用率曲线 */
export const getGpuOverall = (hours = 12) =>
  api.get('/gpu-overall', { params: { hours } })

export default api
