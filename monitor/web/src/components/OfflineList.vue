<template>
  <el-card shadow="never" class="offline-list">
    <template #header>
      <div class="list-header">
        <span>离线记录</span>
        <el-radio-group v-model="days" size="small" @change="fetchData">
          <el-radio-button :value="1">今天</el-radio-button>
          <el-radio-button :value="7">7 天</el-radio-button>
          <el-radio-button :value="30">30 天</el-radio-button>
        </el-radio-group>
      </div>
    </template>

    <div v-if="loading" class="loading-wrapper">
      <el-skeleton :rows="4" animated />
    </div>

    <el-table v-else :data="events" stripe size="small" max-height="400" style="width: 100%">
      <el-table-column label="服务器" prop="hostname" width="120">
        <template #default="{ row }">
          <el-link type="primary" @click="$emit('select', row.hostname)">{{ row.hostname }}</el-link>
        </template>
      </el-table-column>
      <el-table-column label="离线时间" min-width="200">
        <template #default="{ row }">
          {{ formatTime(row.offline_from) }} →
          <span v-if="row.offline_to">{{ formatTime(row.offline_to) }}</span>
          <el-tag v-else type="danger" size="small">至今</el-tag>
        </template>
      </el-table-column>
    </el-table>

    <el-empty v-if="!loading && events.length === 0" description="暂无离线记录" :image-size="60" />
  </el-card>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { getOfflineEvents, REFRESH } from '../api/index.js'

defineEmits(['select'])

const events = ref([])
const days = ref(7)
const loading = ref(true)
let timer = null

const fetchData = async () => {
  try {
    const res = await getOfflineEvents(days.value)
    events.value = res.data
  } catch (e) {
    console.error('获取离线记录失败:', e)
  } finally {
    loading.value = false
  }
}

const formatTime = (ts) => {
  if (!ts) return '--'
  return new Date(ts).toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  })
}

onMounted(() => {
  fetchData()
  timer = setInterval(fetchData, REFRESH.OFFLINE)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<style scoped>
.list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.loading-wrapper {
  padding: 10px 0;
}
</style>
