<template>
  <div class="dashboard">
    <!-- 总览统计 -->
    <el-row :gutter="16" class="stats-row">
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-value">{{ stats.total_servers }}</div>
          <div class="stat-label">服务器总数</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card stat-online">
          <div class="stat-value">{{ stats.online_servers }}</div>
          <div class="stat-label">🟢 在线</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card stat-offline">
          <div class="stat-value">{{ stats.offline_servers }}</div>
          <div class="stat-label">🔴 离线</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card stat-gpu">
          <div class="stat-value">{{ stats.total_gpus }}</div>
          <div class="stat-label">🎮 GPU 总数</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 服务器卡片列表 -->
    <div v-if="loading" class="loading-wrapper">
      <el-skeleton :rows="5" animated />
    </div>

    <el-row v-else :gutter="16" class="server-grid">
      <el-col v-for="server in servers" :key="server.hostname" :xs="24" :sm="12" :md="8" :lg="6">
        <ServerCard
          :server="server"
          @click="openDetail(server.hostname)"
        />
      </el-col>
    </el-row>

    <el-empty v-if="!loading && servers.length === 0" description="暂无服务器数据，请先在客户端运行监控脚本" />

    <!-- 服务器详情对话框 -->
    <el-dialog
      v-model="detailVisible"
      :title="detailHostname"
      width="90%"
      top="5vh"
      destroy-on-close
    >
      <ServerDetail v-if="detailVisible" :hostname="detailHostname" />
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { getServers, getOverview } from '../api/index.js'
import ServerCard from '../components/ServerCard.vue'
import ServerDetail from './ServerDetail.vue'

const servers = ref([])
const stats = ref({
  total_servers: 0,
  online_servers: 0,
  offline_servers: 0,
  total_gpus: 0,
})
const loading = ref(true)
const detailVisible = ref(false)
const detailHostname = ref('')
let timer = null

const fetchData = async () => {
  try {
    const [serversRes, statsRes] = await Promise.all([
      getServers(),
      getOverview(),
    ])
    servers.value = serversRes.data
    stats.value = statsRes.data
  } catch (e) {
    console.error('获取数据失败:', e)
  } finally {
    loading.value = false
  }
}

const openDetail = (hostname) => {
  detailHostname.value = hostname
  detailVisible.value = true
}

onMounted(() => {
  fetchData()
  timer = setInterval(fetchData, 30000) // 每 30 秒刷新
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<style scoped>
.stats-row {
  margin-bottom: 20px;
}

.stat-card {
  text-align: center;
  padding: 12px 0;
}

.stat-value {
  font-size: 36px;
  font-weight: 700;
  color: #303133;
}

.stat-label {
  font-size: 14px;
  color: #909399;
  margin-top: 4px;
}

.stat-online .stat-value {
  color: #67c23a;
}

.stat-offline .stat-value {
  color: #f56c6c;
}

.stat-gpu .stat-value {
  color: #409eff;
}

.server-grid {
  row-gap: 16px;
}

.loading-wrapper {
  padding: 40px 0;
}
</style>
