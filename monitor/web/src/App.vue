<template>
  <div class="app-shell">
    <template v-if="authenticated">
      <el-container>
        <el-header class="app-header">
          <div class="header-left">
            <h1 class="app-title">🖥️ 服务器监控平台</h1>
          </div>
          <div class="header-right">
            <el-tag effect="dark" size="small" type="success">已登录</el-tag>
            <el-tag :type="connected ? 'success' : 'danger'" effect="dark" size="small">
              {{ connected ? '已连接' : '未连接' }}
            </el-tag>
            <span class="update-time">更新于 {{ lastUpdate }}</span>
            <el-button size="small" type="danger" plain @click="handleLogout">退出</el-button>
          </div>
        </el-header>
        <el-main class="app-main">
          <Dashboard :key="dashboardKey" />
        </el-main>
      </el-container>
    </template>

    <template v-else>
      <div class="login-page">
        <div class="login-panel">
          <div class="login-badge"></div>
          <h1>登录</h1>
          <p>请输入密码</p>

          <el-form
            ref="loginFormRef"
            :model="loginForm"
            :rules="loginRules"
            class="login-form"
            @submit.prevent="handleLogin"
          >
            <el-form-item prop="password">
              <el-input
                v-model="loginForm.password"
                type="password"
                placeholder="密码"
                autocomplete="current-password"
                show-password
                @keyup.enter="handleLogin"
              />
            </el-form-item>
            <el-button
              :loading="loginLoading"
              type="primary"
              native-type="submit"
              class="login-button"
              @click="handleLogin"
            >
              登录
            </el-button>
          </el-form>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import Dashboard from './views/Dashboard.vue'
import { getMe, login, logout } from './api/index.js'

const authenticated = ref(false)
const connected = ref(false)
const lastUpdate = ref('--:--:--')
const dashboardKey = ref(0)
const loginLoading = ref(false)
const loginFormRef = ref()
let timer = null

const loginForm = reactive({
  password: '',
})

const loginRules = {
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

const checkAuth = async () => {
  try {
    const resp = await getMe()
    authenticated.value = resp.data.authenticated === true
    connected.value = true
    lastUpdate.value = new Date().toLocaleTimeString('zh-CN')
  } catch {
    authenticated.value = false
    connected.value = false
  }
}

const handleLogin = async () => {
  if (!loginFormRef.value) return
  await loginFormRef.value.validate(async (valid) => {
    if (!valid) return
    loginLoading.value = true
    try {
      await login(loginForm.password)
      authenticated.value = true
      dashboardKey.value += 1
      ElMessage.success('登录成功')
      await checkAuth()
    } catch (error) {
      const message = error?.response?.data?.detail || '登录失败'
      ElMessage.error(message)
    } finally {
      loginLoading.value = false
    }
  })
}

const handleLogout = async () => {
  try {
    await logout()
  } catch {
    // 忽略退出接口异常，前端仍然清理本地状态
  }
  authenticated.value = false
  connected.value = false
  lastUpdate.value = '--:--:--'
  dashboardKey.value += 1
}

onMounted(() => {
  checkAuth()
  timer = setInterval(checkAuth, 30000)
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
  background:
    radial-gradient(circle at top left, rgba(64, 158, 255, 0.10), transparent 28%),
    radial-gradient(circle at bottom right, rgba(103, 194, 58, 0.08), transparent 26%),
    linear-gradient(180deg, #f8fbff 0%, #eef4fb 100%);
  color: #1f2937;
}

.app-shell {
  min-height: 100vh;
}

.app-header {
  background: linear-gradient(135deg, #214c7d 0%, #2f6ea9 55%, #4b86c6 100%);
  color: white;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  box-shadow: 0 10px 30px rgba(2, 6, 23, 0.35);
}

.app-title {
  font-size: 20px;
  font-weight: 700;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.update-time {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.72);
}

.app-main {
  padding: 20px;
  max-width: 1400px;
  margin: 0 auto;
}

.login-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 24px;
}

.login-panel {
  width: min(460px, 100%);
  background: rgba(255, 255, 255, 0.82);
  border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: 24px;
  padding: 32px;
  color: #1f2937;
  box-shadow: 0 24px 80px rgba(15, 23, 42, 0.14);
  backdrop-filter: blur(16px);
}

.login-badge {
  display: inline-block;
  padding: 6px 12px;
  margin-bottom: 18px;
  border-radius: 999px;
  background: rgba(59, 130, 246, 0.10);
  color: #1d4ed8;
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.login-panel h1 {
  font-size: 28px;
  line-height: 1.2;
  margin-bottom: 12px;
}

.login-panel p {
  color: #64748b;
  line-height: 1.7;
  margin-bottom: 24px;
}

.login-form .el-input__wrapper {
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid rgba(148, 163, 184, 0.24);
  box-shadow: none;
}

.login-form .el-input__inner {
  color: #1f2937;
}

.login-button {
  width: 100%;
  height: 44px;
  font-size: 15px;
}
</style>
