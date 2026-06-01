<template>
  <div class="app-container">
    <el-container>
      <el-header class="app-header">
        <div class="header-left">
          <h1 class="app-title">🖥️ 服务器监控平台</h1>
        </div>
        <div class="header-right">
          <el-tag :type="connected ? 'success' : 'danger'" effect="dark" size="small">
            {{ connected ? '已连接' : '未连接' }}
          </el-tag>
          <span class="update-time">更新于 {{ lastUpdate }}</span>
        </div>
      </el-header>
      <el-main class="app-main">
        <Dashboard />
      </el-main>
    </el-container>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import Dashboard from './views/Dashboard.vue'

const connected = ref(false)
const lastUpdate = ref('--:--:--')
let timer = null

const checkConnection = async () => {
  try {
    const resp = await fetch('/api/stats/overview')
    connected.value = resp.ok
    lastUpdate.value = new Date().toLocaleTimeString('zh-CN')
  } catch {
    connected.value = false
  }
}

onMounted(() => {
  checkConnection()
  timer = setInterval(checkConnection, 30000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC',
    'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
  background: #f0f2f5;
}

.app-container {
  min-height: 100vh;
}

.app-header {
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
  color: white;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
}

.app-title {
  font-size: 20px;
  font-weight: 600;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.update-time {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.7);
}

.app-main {
  padding: 20px;
  max-width: 1400px;
  margin: 0 auto;
}
</style>
