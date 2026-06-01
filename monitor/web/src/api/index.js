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

export default api
