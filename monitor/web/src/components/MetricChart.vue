<template>
  <div ref="chartRef" class="metric-chart"></div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  data: { type: Array, default: () => [] },
  field: { type: String, required: true },
  color: { type: String, default: '#409eff' },
  unit: { type: String, default: '' },
  extraFields: { type: Array, default: () => [] },
})

const chartRef = ref(null)
let chart = null

const buildOption = () => {
  if (!props.data?.length) return null

  const timestamps = props.data.map(d => {
    const t = new Date(d.timestamp)
    return `${t.getMonth() + 1}/${t.getDate()} ${t.getHours().toString().padStart(2, '0')}:${t.getMinutes().toString().padStart(2, '0')}`
  })

  const series = []

  // 主字段
  series.push({
    name: props.field,
    type: 'line',
    data: props.data.map(d => d[props.field]),
    smooth: true,
    symbol: 'none',
    lineStyle: { width: 2, color: props.color },
    areaStyle: {
      color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
        { offset: 0, color: props.color + '40' },
        { offset: 1, color: props.color + '05' },
      ]),
    },
  })

  // 额外字段（不同颜色的线）
  const extraColors = ['#e6a23c', '#f56c6c', '#909399']
  props.extraFields.forEach((f, i) => {
    series.push({
      name: f,
      type: 'line',
      data: props.data.map(d => d[f]),
      smooth: true,
      symbol: 'none',
      lineStyle: { width: 1.5, color: extraColors[i % extraColors.length], type: 'dashed' },
    })
  })

  return {
    tooltip: {
      trigger: 'axis',
      formatter: (params) => {
        let html = `<b>${params[0].axisValue}</b><br/>`
        params.forEach(p => {
          html += `${p.marker} ${p.seriesName}: ${p.value}${props.unit}<br/>`
        })
        return html
      },
    },
    grid: { top: 10, right: 20, bottom: 30, left: 50 },
    xAxis: {
      type: 'category',
      data: timestamps,
      axisLabel: {
        fontSize: 10,
        interval: Math.max(Math.floor(timestamps.length / 6), 0),
      },
    },
    yAxis: {
      type: 'value',
      axisLabel: { fontSize: 10 },
    },
    series,
  }
}

const renderChart = () => {
  if (!chart) return
  const option = buildOption()
  if (option) {
    chart.setOption(option, true)
  } else {
    chart.clear()
  }
}

let resizeObserver = null

onMounted(() => {
  if (chartRef.value) {
    chart = echarts.init(chartRef.value)
    renderChart()
    resizeObserver = new ResizeObserver(() => chart?.resize())
    resizeObserver.observe(chartRef.value)
  }
})

watch(() => [props.data, props.field], renderChart, { deep: true })

onUnmounted(() => {
  resizeObserver?.disconnect()
  chart?.dispose()
})
</script>

<style scoped>
.metric-chart {
  width: 100%;
  height: 200px;
}
</style>
