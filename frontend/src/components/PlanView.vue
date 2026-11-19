<template>
  <div class="plan-view">
    <el-card shadow="never">
      <div class="meta">
        <el-tag :type="statusType" size="large">{{ statusText }}</el-tag>
        <span>记录 #{{ record.id }}</span>
        <span>反思重试 {{ record.retry_count }} 次</span>
        <span class="time">{{ fmtTime(record.created_at) }}</span>
      </div>
      <el-alert
        v-if="record.review_feedback"
        type="warning"
        :closable="false"
        class="feedback"
        :title="record.status === 'success' ? '审查反馈（包含质量建议）' : '审查反馈（未通过原因）'"
      >
        <pre class="feedback-text">{{ record.review_feedback }}</pre>
      </el-alert>
      <el-empty
        v-if="!plan"
        description="本次未产出食谱（审查失败或预算不可行）"
        :image-size="80"
      />
    </el-card>

    <template v-if="plan">
      <el-row :gutter="16" class="totals">
        <el-col :span="8">
          <el-card shadow="never">
            <el-statistic title="总成本（元）" :value="plan.total_cost" :precision="2" />
          </el-card>
        </el-col>
        <el-col :span="8">
          <el-card shadow="never">
            <el-statistic title="总热量（kcal）" :value="plan.total_kcal" :precision="1" />
          </el-card>
        </el-col>
        <el-col :span="8">
          <el-card shadow="never">
            <el-statistic title="总蛋白质（g）" :value="plan.total_protein" :precision="1" />
          </el-card>
        </el-col>
      </el-row>

      <el-row :gutter="16" class="charts">
        <el-col :xs="24" :md="10">
          <el-card shadow="never"><div ref="pieRef" class="chart" /></el-card>
        </el-col>
        <el-col :xs="24" :md="14">
          <el-card shadow="never"><div ref="barRef" class="chart" /></el-card>
        </el-col>
      </el-row>

      <el-card v-for="meal in plan.meals" :key="meal.name" shadow="never" class="meal">
        <template #header><el-tag>{{ meal.name }}</el-tag></template>
        <div v-for="dish in meal.dishes" :key="dish.name" class="dish">
          <div class="dish-name">{{ dish.name }}</div>
          <el-table :data="dish.ingredients" size="small" border>
            <el-table-column prop="name" label="食材" min-width="120" />
            <el-table-column prop="amount_g" label="用量 (g)" width="90" />
            <el-table-column label="成本 (元)" width="95">
              <template #default="{ row }">{{ row.cost ?? '—' }}</template>
            </el-table-column>
            <el-table-column label="热量 (kcal)" width="105">
              <template #default="{ row }">{{ row.kcal ?? '—' }}</template>
            </el-table-column>
            <el-table-column label="蛋白 (g)" width="90">
              <template #default="{ row }">{{ row.protein ?? '—' }}</template>
            </el-table-column>
          </el-table>
        </div>
      </el-card>

      <el-card v-if="plan.notes" shadow="never" class="notes">
        <template #header>营养师备注</template>
        {{ plan.notes }}
      </el-card>
    </template>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  record: { type: Object, required: true },
})

const plan = computed(() => props.record.final_plan)
const statusText = computed(
  () => ({ success: '生成成功', failed: '生成失败', pending: '进行中' }[props.record.status] || props.record.status)
)
const statusType = computed(
  () => ({ success: 'success', failed: 'danger', pending: 'warning' }[props.record.status] || 'info')
)
const fmtTime = (t) => String(t || '').replace('T', ' ').slice(0, 19)

const pieRef = ref(null)
const barRef = ref(null)
let pieChart = null
let barChart = null

// 每餐汇总：食材上的 cost/kcal/protein 是后端 decorate_plan 算好的
const mealStats = computed(() => {
  if (!plan.value) return []
  return plan.value.meals.map((meal) => {
    let cost = 0
    let kcal = 0
    let protein = 0
    for (const dish of meal.dishes) {
      for (const ing of dish.ingredients) {
        cost += ing.cost || 0
        kcal += ing.kcal || 0
        protein += ing.protein || 0
      }
    }
    return {
      name: meal.name,
      cost: +cost.toFixed(2),
      kcal: +kcal.toFixed(1),
      protein: +protein.toFixed(1),
    }
  })
})

function renderCharts() {
  // 记录切换时 DOM 可能重建，统一销毁重画，避免图表挂在旧节点上
  pieChart?.dispose()
  barChart?.dispose()
  pieChart = null
  barChart = null
  if (!plan.value || !pieRef.value || !barRef.value) return

  const stats = mealStats.value
  pieChart = echarts.init(pieRef.value)
  pieChart.setOption({
    title: { text: '各餐成本占比', left: 'center', textStyle: { fontSize: 14 } },
    tooltip: { trigger: 'item', formatter: '{b}: {c} 元 ({d}%)' },
    series: [
      {
        type: 'pie',
        radius: ['35%', '65%'],
        data: stats.map((s) => ({ name: s.name, value: s.cost })),
        label: { formatter: '{b}\n{c} 元' },
      },
    ],
  })

  barChart = echarts.init(barRef.value)
  barChart.setOption({
    title: { text: '各餐热量与蛋白质', left: 'center', textStyle: { fontSize: 14 } },
    tooltip: { trigger: 'axis' },
    legend: { bottom: 0 },
    grid: { left: 55, right: 55, top: 50, bottom: 40 },
    xAxis: { type: 'category', data: stats.map((s) => s.name) },
    yAxis: [
      { type: 'value', name: 'kcal' },
      { type: 'value', name: '蛋白 g' },
    ],
    series: [
      { name: '热量', type: 'bar', data: stats.map((s) => s.kcal), itemStyle: { color: '#67c23a' } },
      { name: '蛋白质', type: 'bar', yAxisIndex: 1, data: stats.map((s) => s.protein), itemStyle: { color: '#409eff' } },
    ],
  })
}

function resize() {
  pieChart?.resize()
  barChart?.resize()
}

onMounted(() => {
  nextTick(renderCharts)
  window.addEventListener('resize', resize)
})
watch(() => props.record, () => nextTick(renderCharts))
onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  pieChart?.dispose()
  barChart?.dispose()
})
</script>

<style scoped>
.meta {
  display: flex;
  align-items: center;
  gap: 16px;
  font-size: 14px;
  color: #606266;
}
.meta .time {
  margin-left: auto;
  color: #909399;
  font-size: 12px;
}
.feedback {
  margin-top: 12px;
}
.feedback-text {
  margin: 4px 0 0;
  white-space: pre-wrap;
  font-family: inherit;
  font-size: 13px;
}
.totals {
  margin-top: 16px;
}
.charts {
  margin-top: 16px;
}
.chart {
  height: 280px;
  width: 100%;
}
.meal {
  margin-top: 16px;
}
.dish + .dish {
  margin-top: 12px;
}
.dish-name {
  font-weight: 600;
  margin-bottom: 6px;
  color: #303133;
}
.notes {
  margin-top: 16px;
  color: #606266;
}
</style>