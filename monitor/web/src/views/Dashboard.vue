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

    <!-- 主体：左侧服务器卡片 + 右侧 GPU/离线 -->
    <div class="main-layout">
      <div class="main-left">
        <div v-if="loading" class="loading-wrapper">
          <el-skeleton :rows="5" animated />
        </div>
        <template v-else>
          <div v-for="group in groupedServers" :key="group.name" class="user-group">
            <div class="group-header" @click="toggleGroup(group.name)">
              <span class="collapse-arrow" :class="{ collapsed: collapsedGroups.has(group.name) }">▶</span>
              <span class="group-name">{{ group.name }}</span>
              <el-tag size="small" type="info" class="group-count">{{ group.servers.length }} 台</el-tag>
              <span class="group-online">{{ group.onlineCount }} 在线</span>
            </div>
            <div v-show="!collapsedGroups.has(group.name)" class="server-grid">
              <ServerCard v-for="server in group.servers" :key="server.hostname" :server="server" @click="openDetail(server.hostname)" />
            </div>
          </div>
          <div v-if="unassignedServers.length" class="user-group">
            <div class="group-header">
              <span class="group-name">未分配</span>
              <el-tag size="small" type="info" class="group-count">{{ unassignedServers.length }} 台</el-tag>
            </div>
            <div class="server-grid">
              <ServerCard v-for="server in unassignedServers" :key="server.hostname" :server="server" @click="openDetail(server.hostname)" />
            </div>
          </div>
        </template>
        <el-empty v-if="!loading && servers.length === 0" description="暂无服务器数据，请先在客户端运行监控脚本" />
      </div>
      <div class="main-right">
        <GpuOverall />
        <div style="height: 16px"></div>
        <GpuRanking @select="openDetail" />
        <div style="height: 16px"></div>
        <OfflineList @select="openDetail" />
      </div>
    </div>

    <!-- 服务器详情对话框 -->
    <el-dialog v-model="detailVisible" :title="detailHostname" width="90%" top="5vh" destroy-on-close>
      <ServerDetail v-if="detailVisible" :hostname="detailHostname" />
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { getServers, getOverview, REFRESH } from '../api/index.js'
import ServerCard from '../components/ServerCard.vue'
import ServerDetail from './ServerDetail.vue'
import OfflineList from '../components/OfflineList.vue'
import GpuRanking from '../components/GpuRanking.vue'
import GpuOverall from '../components/GpuOverall.vue'

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
const collapsedGroups = ref(new Set())
let timer = null

/** 按归属人分组 */
const groupedServers = computed(() => {
  const userMap = new Map() // userName -> [server, ...]
  const assigned = new Set()

  for (const s of servers.value) {
    if (s.users?.length) {
      for (const u of s.users) {
        if (!userMap.has(u)) userMap.set(u, [])
        userMap.get(u).push(s)
        assigned.add(s.hostname)
      }
    }
  }

  const groups = []
  for (const [name, svrs] of userMap) {
    groups.push({
      name,
      servers: svrs,
      onlineCount: svrs.filter(s => s.online).length,
    })
  }
  return groups
})

/** 没有归属人的服务器 */
const unassignedServers = computed(() => {
  const assigned = new Set()
  for (const s of servers.value) {
    if (s.users?.length) {
      for (const u of s.users) assigned.add(s.hostname)
    }
  }
  return servers.value.filter(s => !assigned.has(s.hostname))
})

const toggleGroup = (name) => {
  const next = new Set(collapsedGroups.value)
  if (next.has(name)) {
    next.delete(name)
  } else {
    next.add(name)
  }
  collapsedGroups.value = next
}

const fetchData = async () => {
  try {
    const [serversRes, statsRes] = await Promise.all([
      getServers(),
      getOverview(),
    ])
    servers.value = serversRes.data
    stats.value = statsRes.data
    // 首次加载时所有分组默认折叠
    if (collapsedGroups.value.size === 0) {
      for (const g of groupedServers.value) {
        collapsedGroups.value.add(g.name)
      }
      collapsedGroups.value = new Set(collapsedGroups.value)
    }
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
  timer = setInterval(fetchData, REFRESH.DASHBOARD)
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

.user-group {
  margin-bottom: 16px;
}

.group-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  margin-bottom: 12px;
  background: #f5f7fa;
  border-radius: 6px;
  cursor: pointer;
  user-select: none;
  transition: background 0.2s;
}

.group-header:hover {
  background: #ecf0f5;
}

.collapse-arrow {
  font-size: 11px;
  transition: transform 0.2s;
  color: #909399;
  display: inline-block;
}

.collapse-arrow.collapsed {
  transform: rotate(0deg);
}

.collapse-arrow:not(.collapsed) {
  transform: rotate(90deg);
}

.group-name {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.group-count {
  margin-left: 4px;
}

.group-online {
  font-size: 12px;
  color: #67c23a;
}

.server-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.loading-wrapper {
  padding: 40px 0;
}

.main-layout {
  display: grid;
  grid-template-columns: 3fr 1fr;
  gap: 16px;
}

.main-left {
  min-width: 0;
}

.main-right {
  min-width: 0;
}
</style>
