<template>
  <el-card shadow="never" class="gpu-ranking">
    <template #header>
      <div class="ranking-header">
        <span>GPU 使用率排行</span>
        <el-radio-group v-model="hours" size="small" @change="fetchData">
          <el-radio-button :value="1">1 小时</el-radio-button>
          <el-radio-button :value="6">6 小时</el-radio-button>
          <el-radio-button :value="24">24 小时</el-radio-button>
        </el-radio-group>
      </div>
    </template>

    <div v-if="loading" class="loading-wrapper">
      <el-skeleton :rows="5" animated />
    </div>

    <el-table v-else :data="ranking" stripe size="small" max-height="300" style="width: 100%">
      <el-table-column label="#" width="40" align="center">
        <template #default="{ row }">
          <span :class="rankClass(row.rank)">{{ row.rank }}</span>
        </template>
      </el-table-column>
      <el-table-column label="服务器" prop="hostname" min-width="120">
        <template #default="{ row }">
          <el-link type="primary" @click="$emit('select', row.hostname)">{{ row.hostname }}</el-link>
        </template>
      </el-table-column>
      <el-table-column label="平均 GPU%" width="120">
        <template #default="{ row }">
          <el-progress
            :percentage="row.avg_util"
            :stroke-width="6"
            :color="utilColor(row.avg_util)"
            :format="(p) => p + '%'"
          />
        </template>
      </el-table-column>
    </el-table>

    <el-empty v-if="!loading && ranking.length === 0" description="暂无 GPU 数据" :image-size="60" />
  </el-card>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { getGpuRanking, REFRESH } from '../api/index.js'

defineEmits(['select'])

const ranking = ref([])
const hours = ref(1)
const loading = ref(true)
let timer = null

const fetchData = async () => {
  try {
    const res = await getGpuRanking(hours.value)
    ranking.value = res.data
  } catch (e) {
    console.error('获取 GPU 排行失败:', e)
  } finally {
    loading.value = false
  }
}

const rankClass = (rank) => {
  if (rank === 1) return 'rank-gold'
  if (rank === 2) return 'rank-silver'
  if (rank === 3) return 'rank-bronze'
  return ''
}

const utilColor = (pct) => {
  if (pct >= 90) return '#f56c6c'
  if (pct >= 70) return '#e6a23c'
  return '#67c23a'
}

onMounted(() => {
  fetchData()
  timer = setInterval(fetchData, REFRESH.GPU)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<style scoped>
.ranking-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.loading-wrapper {
  padding: 10px 0;
}

.rank-gold { color: #e6a23c; font-weight: 700; }
.rank-silver { color: #909399; font-weight: 600; }
.rank-bronze { color: #cd7f32; font-weight: 600; }
</style>
