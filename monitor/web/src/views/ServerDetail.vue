<template>
  <div class="server-detail" v-loading="loading">
    <template v-if="!loading">
      <!-- 基本信息 -->
      <el-descriptions :column="3" border size="default" class="info-section">
        <el-descriptions-item label="主机名">{{ server.hostname }}</el-descriptions-item>
        <el-descriptions-item label="IP 地址">{{ server.ip }}</el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="server.online ? 'success' : 'danger'" size="small">
            {{ server.online ? '在线' : '离线' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="操作系统">{{ server.os }}</el-descriptions-item>
        <el-descriptions-item label="CPU 核数">{{ server.cpu_count }}</el-descriptions-item>
        <el-descriptions-item label="GPU">
          {{ server.gpu_count }} 卡
          <span v-if="server.gpu_models?.length">({{ server.gpu_models.join(', ') }})</span>
        </el-descriptions-item>
        <el-descriptions-item label="注册时间">{{ formatTime(server.registered_at) }}</el-descriptions-item>
        <el-descriptions-item label="最后活跃">{{ formatTime(server.last_seen) }}</el-descriptions-item>
      </el-descriptions>

      <!-- 时间范围选择 -->
      <div class="time-range">
        <el-radio-group v-model="hours" size="small" @change="fetchMetrics">
          <el-radio-button :value="1">1 小时</el-radio-button>
          <el-radio-button :value="6">6 小时</el-radio-button>
          <el-radio-button :value="24">24 小时</el-radio-button>
          <el-radio-button :value="168">7 天</el-radio-button>
        </el-radio-group>
      </div>

      <!-- 指标图表 -->
      <el-row :gutter="16" class="charts-row">
        <el-col :span="12">
          <el-card shadow="never">
            <template #header>CPU 使用率</template>
            <MetricChart :data="metrics" field="cpu_pct" color="#409eff" unit="%" />
          </el-card>
        </el-col>
        <el-col :span="12">
          <el-card shadow="never">
            <template #header>内存使用率</template>
            <MetricChart :data="metrics" field="mem_pct" color="#67c23a" unit="%" />
          </el-card>
        </el-col>
      </el-row>

      <el-row :gutter="16" class="charts-row">
        <el-col :span="12">
          <el-card shadow="never">
            <template #header>系统负载</template>
            <MetricChart :data="metrics" field="load_1m" color="#e6a23c" :extra-fields="['load_5m', 'load_15m']" />
          </el-card>
        </el-col>
        <el-col :span="12">
          <el-card shadow="never">
            <template #header>磁盘使用率</template>
            <MetricChart :data="metrics" field="disk_pct" color="#f56c6c" unit="%" />
          </el-card>
        </el-col>
      </el-row>

      <!-- GPU 详情 -->
      <template v-if="latestMetric?.gpus?.length">
        <el-card shadow="never" class="gpu-section">
          <template #header>🎮 GPU 详情</template>
          <GpuTable :gpus="latestMetric.gpus" />
        </el-card>

        <el-row :gutter="16" class="charts-row">
          <el-col :span="12" v-for="(gpu, idx) in latestMetric.gpus" :key="gpu.gpu_id">
            <el-card shadow="never">
              <template #header>GPU {{ gpu.gpu_id }} 温度 & 使用率</template>
              <MetricChart
                :data="gpuMetrics(idx)"
                field="compute_util"
                color="#409eff"
                unit="%"
                :extra-fields="['temp_c']"
              />
            </el-card>
          </el-col>
        </el-row>
      </template>
    </template>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { getServer, getMetrics, getLatestMetrics } from '../api/index.js'
import MetricChart from '../components/MetricChart.vue'
import GpuTable from '../components/GpuTable.vue'

const props = defineProps({
  hostname: { type: String, required: true },
})

const server = ref({})
const metrics = ref([])
const latestMetric = ref(null)
const hours = ref(24)
const loading = ref(true)
let timer = null

const fetchMetrics = async () => {
  try {
    const [metricsRes] = await Promise.all([
      getMetrics(props.hostname, hours.value),
    ])
    metrics.value = metricsRes.data
  } catch (e) {
    console.error('获取指标失败:', e)
  }
}

const fetchData = async () => {
  try {
    const [serverRes, latestRes] = await Promise.all([
      getServer(props.hostname),
      getLatestMetrics(props.hostname).catch(() => ({ data: null })),
    ])
    server.value = serverRes.data
    latestMetric.value = latestRes.data
  } catch (e) {
    console.error('获取数据失败:', e)
  }
}

const init = async () => {
  loading.value = true
  await Promise.all([fetchData(), fetchMetrics()])
  loading.value = false
}

const gpuMetrics = (gpuIdx) => {
  return metrics.value
    .filter(m => m.gpus?.[gpuIdx])
    .map(m => ({ timestamp: m.timestamp, compute_util: m.gpus[gpuIdx].compute_util, temp_c: m.gpus[gpuIdx].temp_c }))
}

const formatTime = (ts) => {
  if (!ts) return '--'
  return new Date(ts).toLocaleString('zh-CN')
}

onMounted(() => {
  init()
  timer = setInterval(() => {
    fetchData()
    fetchMetrics()
  }, 30000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<style scoped>
.info-section {
  margin-bottom: 20px;
}

.time-range {
  margin-bottom: 20px;
  text-align: right;
}

.charts-row {
  margin-bottom: 16px;
}

.gpu-section {
  margin-bottom: 16px;
}
</style>
