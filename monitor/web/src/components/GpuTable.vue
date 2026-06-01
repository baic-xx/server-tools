<template>
  <el-table :data="gpus" stripe size="small" style="width: 100%">
    <el-table-column prop="gpu_id" label="GPU" width="70" />
    <el-table-column label="计算使用率" width="140">
      <template #default="{ row }">
        <el-progress
          :percentage="row.compute_util"
          :stroke-width="6"
          :color="utilColor(row.compute_util)"
        />
      </template>
    </el-table-column>
    <el-table-column label="显存使用率" width="140">
      <template #default="{ row }">
        <el-progress
          :percentage="row.mem_util"
          :stroke-width="6"
          :color="utilColor(row.mem_util)"
        />
      </template>
    </el-table-column>
    <el-table-column label="显存" width="160">
      <template #default="{ row }">
        {{ row.mem_used_mb }} / {{ row.mem_total_mb }} MB
      </template>
    </el-table-column>
    <el-table-column label="温度" width="100">
      <template #default="{ row }">
        <span :style="{ color: row.temp_c > 80 ? '#f56c6c' : row.temp_c > 60 ? '#e6a23c' : '#67c23a', fontWeight: row.temp_c > 80 ? '600' : 'normal' }">
          {{ row.temp_c }}°C
        </span>
      </template>
    </el-table-column>
    <el-table-column label="功耗" width="100">
      <template #default="{ row }">
        {{ row.power_w.toFixed(0) }} W
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup>
defineProps({
  gpus: { type: Array, required: true },
})

const utilColor = (pct) => {
  if (pct >= 90) return '#f56c6c'
  if (pct >= 70) return '#e6a23c'
  return '#67c23a'
}
</script>
