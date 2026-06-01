<template>
  <el-card
    shadow="hover"
    class="server-card"
    :class="{ offline: !server.online }"
    @click="$emit('click')"
  >
    <div class="card-header">
      <span class="hostname">{{ server.hostname }}</span>
      <el-tag :type="server.online ? 'success' : 'danger'" size="small" effect="dark">
        {{ server.online ? '在线' : '离线' }}
      </el-tag>
    </div>

    <div class="card-info">
      <div class="info-row">
        <span class="label">IP</span>
        <span class="value">{{ server.ip }}</span>
      </div>
      <div class="info-row">
        <span class="label">系统</span>
        <span class="value">{{ server.os }}</span>
      </div>
      <div class="info-row">
        <span class="label">CPU</span>
        <span class="value">{{ server.cpu_count }} 核</span>
      </div>
      <div class="info-row" v-if="server.gpu_count > 0">
        <span class="label">GPU</span>
        <span class="value">{{ server.gpu_count }} 卡</span>
      </div>
    </div>

    <div class="card-metrics" v-if="server.latest_cpu != null">
      <div class="metric">
        <span class="metric-label">CPU</span>
        <el-progress
          :percentage="server.latest_cpu"
          :stroke-width="8"
          :color="percentageColor(server.latest_cpu)"
        />
      </div>
      <div class="metric">
        <span class="metric-label">内存</span>
        <el-progress
          :percentage="server.latest_mem"
          :stroke-width="8"
          :color="percentageColor(server.latest_mem)"
        />
      </div>
    </div>

    <!-- GPU 概况 -->
    <div class="card-gpus" v-if="server.latest_gpus?.length">
      <div class="gpu-item" v-for="gpu in server.latest_gpus" :key="gpu.gpu_id">
        <span class="gpu-id">GPU {{ gpu.gpu_id }}</span>
        <span class="gpu-util">{{ gpu.compute_util }}%</span>
        <span class="gpu-temp" :class="{ hot: gpu.temp_c > 80 }">{{ gpu.temp_c }}°C</span>
      </div>
    </div>
  </el-card>
</template>

<script setup>
defineProps({
  server: { type: Object, required: true },
})

defineEmits(['click'])

const percentageColor = (pct) => {
  if (pct >= 90) return '#f56c6c'
  if (pct >= 70) return '#e6a23c'
  return '#67c23a'
}
</script>

<style scoped>
.server-card {
  cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s;
  margin-bottom: 16px;
}

.server-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.server-card.offline {
  opacity: 0.7;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.hostname {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.card-info {
  margin-bottom: 12px;
}

.info-row {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  padding: 2px 0;
}

.info-row .label {
  color: #909399;
}

.info-row .value {
  color: #606266;
}

.card-metrics {
  margin-bottom: 8px;
}

.metric {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.metric-label {
  font-size: 12px;
  color: #909399;
  width: 32px;
}

.metric .el-progress {
  flex: 1;
}

.card-gpus {
  border-top: 1px solid #ebeef5;
  padding-top: 8px;
}

.gpu-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  padding: 2px 0;
}

.gpu-id {
  color: #909399;
  min-width: 48px;
}

.gpu-util {
  color: #606266;
  min-width: 40px;
}

.gpu-temp {
  color: #67c23a;
}

.gpu-temp.hot {
  color: #f56c6c;
  font-weight: 600;
}
</style>
