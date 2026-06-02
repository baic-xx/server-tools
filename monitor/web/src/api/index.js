import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 10000,
})

// ─── 服务器相关 ───

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

export default api
