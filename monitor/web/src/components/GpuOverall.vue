<template>
  <el-card shadow="never" class="gpu-overall">
    <template #header>
      <div class="chart-header">
        <span>总 GPU 使用率</span>
        <el-radio-group v-model="hours" size="small" @change="fetchData">
          <el-radio-button :value="12">12 小时</el-radio-button>
          <el-radio-button :value="24">24 小时</el-radio-button>
        </el-radio-group>
      </div>
    </template>

    <div ref="chartRef" class="gpu-chart"></div>

    <el-empty v-if="!loading && data.length === 0" description="暂无 GPU 数据" :image-size="40" />
  </el-card>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'
import * as echarts from 'echarts'
import { getGpuOverall, REFRESH } from '../api/index.js'

const chartRef = ref(null)
const data = ref([])
const hours = ref(12)
const loading = ref(true)
let chart = null
let timer = null
let resizeObserver = null

const fetchData = async () => {
  try {
    const res = await getGpuOverall(hours.value)
    data.value = res.data
  } catch (e) {
    console.error('获取 GPU 总览失败:', e)
  } finally {
    loading.value = false
  }
}

const renderChart = () => {
  if (!chart || !data.value.length) return

  const timestamps = data.value.map(d => {
    const t = new Date(d.timestamp)
    return `${(t.getMonth() + 1).toString().padStart(2, '0')}/${t.getDate().toString().padStart(2, '0')} ${t.getHours().toString().padStart(2, '0')}:${t.getMinutes().toString().padStart(2, '0')}`
  })
  const values = data.value.map(d => d.avg_util)

  chart.setOption({
    tooltip: {
      trigger: 'axis',
      formatter: (params) => `${params[0].axisValue}<br/>${params[0].marker} 平均 GPU: ${params[0].value}%`,
    },
    grid: { top: 10, right: 15, bottom: 25, left: 40 },
    xAxis: {
      type: 'category',
      data: timestamps,
      axisLabel: {
        fontSize: 10,
        interval: Math.max(Math.floor(timestamps.length / 4), 0),
      },
    },
    yAxis: {
      type: 'value',
      max: 100,
      axisLabel: { fontSize: 10, formatter: '{value}%' },
    },
    series: [{
      type: 'line',
      data: values,
      smooth: true,
      symbol: 'none',
      lineStyle: { width: 2, color: '#409eff' },
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: 'rgba(64,158,255,0.25)' },
          { offset: 1, color: 'rgba(64,158,255,0.02)' },
        ]),
      },
    }],
  }, true)
}

onMounted(async () => {
  await fetchData()
  if (chartRef.value) {
    chart = echarts.init(chartRef.value)
    renderChart()
    resizeObserver = new ResizeObserver(() => chart?.resize())
    resizeObserver.observe(chartRef.value)
  }
  timer = setInterval(fetchData, REFRESH.GPU)
})

watch(data, renderChart)

onUnmounted(() => {
  if (timer) clearInterval(timer)
  resizeObserver?.disconnect()
  chart?.dispose()
})
</script>

<style scoped>
.chart-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.gpu-chart {
  width: 100%;
  height: 160px;
}
</style>
