<template>
  <el-container class="page">
    <el-header class="header">
      <div class="brand">
        <span class="logo">NutriAgent</span>
        <span class="slogan">多约束智能膳食规划 · 生成 → 审查 → 反思重试</span>
      </div>
      <el-tag :type="backendOk ? 'success' : 'danger'" size="small">
        {{ backendOk ? '后端已连接' : '后端未连接' }}
      </el-tag>
    </el-header>

    <el-main>
      <el-row :gutter="20">
        <!-- 左：表单 + 历史 -->
        <el-col :xs="24" :md="9" :lg="7">
          <el-card shadow="never">
            <template #header>身体数据与约束</template>
            <el-form
              ref="formRef"
              :model="form"
              :rules="rules"
              label-width="90px"
            >
              <el-form-item label="年龄" prop="age">
                <el-input-number v-model="form.age" :min="1" :max="100" />
              </el-form-item>
              <el-form-item label="性别" prop="gender">
                <el-radio-group v-model="form.gender">
                  <el-radio-button value="male">男</el-radio-button>
                  <el-radio-button value="female">女</el-radio-button>
                </el-radio-group>
              </el-form-item>
              <el-form-item label="身高 cm" prop="height">
                <el-input-number v-model="form.height" :min="51" :max="250" :precision="1" />
              </el-form-item>
              <el-form-item label="体重 kg" prop="weight">
                <el-input-number v-model="form.weight" :min="11" :max="200" :precision="1" />
              </el-form-item>
              <el-form-item label="目标" prop="goal">
                <el-radio-group v-model="form.goal">
                  <el-radio-button value="lose">减脂</el-radio-button>
                  <el-radio-button value="maintain">维持</el-radio-button>
                  <el-radio-button value="gain">增肌</el-radio-button>
                </el-radio-group>
              </el-form-item>
              <el-form-item label="每日预算" prop="daily_budget">
                <el-input-number v-model="form.daily_budget" :min="0.5" :max="500" :step="5" :precision="1" />
                <span class="unit">元</span>
              </el-form-item>
              <el-form-item label="过敏原" prop="allergies">
                <el-select
                  v-model="form.allergies"
                  multiple filterable allow-create default-first-option
                  placeholder="可多选，也可输入自定义"
                >
                  <el-option v-for="a in allergenOptions" :key="a" :label="a" :value="a" />
                </el-select>
              </el-form-item>
              <el-form-item label="忌口" prop="dislikes">
                <el-select
                  v-model="form.dislikes"
                  multiple filterable allow-create default-first-option
                  placeholder="如：香菜、辣椒（写入提示词）"
                >
                  <el-option v-for="d in dislikeOptions" :key="d" :label="d" :value="d" />
                </el-select>
              </el-form-item>
              <el-form-item>
                <el-button type="primary" :loading="loading" @click="submit">
                  {{ loading ? '生成中，模型审查可能需要几十秒' : '生成一日三餐' }}
                </el-button>
              </el-form-item>
            </el-form>
          </el-card>

          <el-card shadow="never" class="history-card">
            <template #header>
              <div class="history-header">
                <span>历史记录</span>
                <el-input
                  v-model="queryId"
                  placeholder="按 ID 查询"
                  size="small"
                  style="width: 140px"
                  @keyup.enter="loadById"
                >
                  <template #append>
                    <el-button size="small" @click="loadById">查</el-button>
                  </template>
                </el-input>
              </div>
            </template>
            <el-empty v-if="!history.length" description="暂无记录" :image-size="60" />
            <ul v-else class="history-list">
              <li
                v-for="h in history"
                :key="h.id"
                :class="{ active: record && record.id === h.id }"
                @click="loadRecord(h.id)"
              >
                <span>#{{ h.id }}</span>
                <el-tag size="small" :type="statusType(h.status)">{{ statusText(h.status) }}</el-tag>
                <span v-if="h.total_cost != null" class="cost">{{ h.total_cost }} 元</span>
                <span class="time">{{ h.created_at }}</span>
              </li>
            </ul>
          </el-card>
        </el-col>

        <!-- 右：结果 -->
        <el-col :xs="24" :md="15" :lg="17">
          <el-alert
            v-if="error"
            :title="error.title"
            :description="error.detail"
            :type="error.type"
            show-icon
            class="error-alert"
            @close="error = null"
          />
          <el-card v-if="loading" shadow="never">
            <el-skeleton :rows="8" animated />
          </el-card>
          <PlanView v-else-if="record" :record="record" />
          <el-card v-else shadow="never">
            <el-empty description="填写左侧表单，生成合规的一日三餐。试试把预算改成 0.5 元，看系统如何拦截（422）" />
          </el-card>
        </el-col>
      </el-row>
    </el-main>
  </el-container>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { checkHealth, createDietPlan, getDietPlan } from './api'
import PlanView from './components/PlanView.vue'

const formRef = ref()
const loading = ref(false)
const record = ref(null)
const error = ref(null)
const backendOk = ref(false)
const queryId = ref('')
const history = ref(JSON.parse(localStorage.getItem('nutri_history') || '[]'))

const form = reactive({
  age: 25,
  gender: 'male',
  height: 175,
  weight: 70,
  goal: 'maintain',
  daily_budget: 30,
  allergies: [],
  dislikes: [],
})

const rules = {
  age: [{ required: true, message: '请输入年龄', trigger: 'blur' }],
  height: [{ required: true, message: '请输入身高', trigger: 'blur' }],
  weight: [{ required: true, message: '请输入体重', trigger: 'blur' }],
  daily_budget: [{ required: true, message: '请输入预算', trigger: 'blur' }],
}

const allergenOptions = ['花生', '牛奶', '鸡蛋', '海鲜', '大豆', '小麦', '坚果']
const dislikeOptions = ['香菜', '辣椒', '羊肉', '内脏', '生冷']

const statusText = (s) => ({ success: '成功', failed: '失败', pending: '进行中' }[s] || s)
const statusType = (s) => ({ success: 'success', failed: 'danger', pending: 'warning' }[s] || 'info')
const fmtTime = (t) => String(t || '').replace('T', ' ').slice(0, 19)

function saveHistory(rec) {
  const item = {
    id: rec.id,
    status: rec.status,
    created_at: fmtTime(rec.created_at),
    total_cost: rec.final_plan?.total_cost ?? null,
  }
  history.value = [item, ...history.value.filter((h) => h.id !== rec.id)].slice(0, 20)
  localStorage.setItem('nutri_history', JSON.stringify(history.value))
}

function extractError(e) {
  if (e.response) {
    const detail = e.response.data?.detail
    const text = typeof detail === 'string' ? detail : JSON.stringify(detail)
    const status = e.response.status
    if (status === 422) return { type: 'warning', title: '请求被拦截（422）', detail: text }
    if (status === 502) return { type: 'error', title: '模型调用失败（502）', detail: text }
    return { type: 'error', title: `请求失败（${status}）`, detail: text }
  }
  return { type: 'error', title: '无法连接后端', detail: '请确认后端已在 127.0.0.1:8000 启动' }
}

async function submit() {
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  loading.value = true
  error.value = null
  try {
    const rec = await createDietPlan({ ...form })
    record.value = rec
    saveHistory(rec)
    if (rec.status === 'success') {
      ElMessage.success(`生成成功，反思重试 ${rec.retry_count} 次`)
    } else {
      ElMessage.warning('多次重试后仍未通过审查，已记录失败原因')
    }
  } catch (e) {
    record.value = null
    error.value = extractError(e)
  } finally {
    loading.value = false
  }
}

async function loadRecord(id) {
  loading.value = true
  error.value = null
  try {
    const rec = await getDietPlan(id)
    record.value = rec
    saveHistory(rec)
  } catch (e) {
    error.value = extractError(e)
  } finally {
    loading.value = false
  }
}

function loadById() {
  const id = Number(queryId.value)
  if (!Number.isInteger(id) || id <= 0) {
    ElMessage.warning('请输入正整数 ID')
    return
  }
  loadRecord(id)
}

onMounted(async () => {
  try {
    await checkHealth()
    backendOk.value = true
  } catch {
    backendOk.value = false
  }
})
</script>

<style scoped>
.page {
  min-height: 100vh;
  background: #f5f7fa;
}
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
}
.brand {
  display: flex;
  align-items: baseline;
  gap: 12px;
}
.logo {
  font-size: 20px;
  font-weight: 700;
  color: #409eff;
}
.slogan {
  font-size: 12px;
  color: #909399;
}
.unit {
  margin-left: 8px;
  color: #909399;
}
.history-card {
  margin-top: 16px;
}
.history-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.history-list {
  list-style: none;
  margin: 0;
  padding: 0;
  max-height: 260px;
  overflow-y: auto;
}
.history-list li {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
}
.history-list li:hover {
  background: #ecf5ff;
}
.history-list li.active {
  background: #d9ecff;
}
.history-list .cost {
  color: #e6a23c;
}
.history-list .time {
  margin-left: auto;
  color: #c0c4cc;
  font-size: 12px;
}
.error-alert {
  margin-bottom: 16px;
}
</style>