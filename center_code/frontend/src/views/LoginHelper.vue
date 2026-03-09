<template>
  <div class="login-helper-container">
    <el-card>
      <template #header>
        <h2>账号登录助手</h2>
      </template>

      <div v-if="!accountId" class="error-message">
        <el-alert type="error" :closable="false">
          <template #title>错误：缺少账号ID参数</template>
        </el-alert>
      </div>

      <div v-else>
        <!-- 步骤 1: 获取二维码 / 启动中 -->
        <div v-if="currentStep === 1" class="step">
          <h3>正在启动浏览器...</h3>
          <el-progress :percentage="browserStartProgress" status="striped" striped-flow :duration="10" />
        </div>

        <!-- 步骤 2: 等待登录 -->
        <div v-if="currentStep === 2" class="step">
          <!-- 二维码加载中 -->
          <div v-if="!qrcodeImage && loadingQrcode" style="text-align: center; padding: 40px 0;">
            <el-icon :size="40" class="is-loading" style="margin-bottom: 16px;">
              <Loading />
            </el-icon>
            <p style="color: #909399;">正在加载二维码...</p>
          </div>

          <!-- 二维码展示 -->
          <div v-if="qrcodeImage" class="qrcode-container">
            <el-image
              :src="qrcodeImage"
              style="width: 260px; height: 260px; border: 1px solid #ddd; border-radius: 8px;"
              fit="contain"
            />
            <p class="qr-hint">请使用 APP 扫描上方二维码完成登录</p>
            <el-button size="small" @click="refreshQrcode" :loading="loadingQrcode" style="margin-top: 4px;">
              刷新二维码
            </el-button>
          </div>

          <!-- 状态提示（仅在二维码加载完成后显示） -->
          <div v-if="qrcodeImage" style="margin-top: 16px;">
            <el-alert v-if="loginStatus === 'waiting'" type="info" :closable="false" title="等待扫码..." />
            <el-alert v-else-if="loginStatus === 'scanning'" type="warning" :closable="false" title="已扫码，请在手机上确认登录" />
            <el-alert v-else-if="loginStatus === 'sms_required'" type="info" :closable="false"
              title="检测到手机号验证码登录，请在后端浏览器中完成验证" />
            <el-alert v-else-if="loginStatus === 'failed'" type="error" :closable="false"
              :title="statusMessage || '登录失败，请重试'">
              <template #default>
                <el-button size="small" @click="refreshQrcode" style="margin-top: 6px;">重新获取二维码</el-button>
              </template>
            </el-alert>
          </div>
        </div>

        <!-- 步骤 3: 完成 -->
        <div v-if="currentStep === 3" class="step">
          <el-result icon="success" title="登录完成" sub-title="Cookies 已成功保存！">
            <template #extra>
              <el-button type="primary" @click="closeWindow">关闭窗口</el-button>
            </template>
          </el-result>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import api from '../api'

const route = useRoute()
const accountId = ref(null)
const currentStep = ref(1)
const loadingQrcode = ref(false)
const qrcodeImage = ref(null)
const loginStatus = ref('waiting')
const statusMessage = ref('')
const submitting = ref(false)
const browserStartProgress = ref(0)

let statusPollTimer = null
let progressTimer = null

onMounted(() => {
  accountId.value = route.query.account_id ? parseInt(route.query.account_id) : null
  if (!accountId.value) {
    ElMessage.error('缺少账号ID参数')
    return
  }
  startProgressAnimation()
  startSession()
})

onUnmounted(() => {
  stopStatusPoll()
  stopProgressAnimation()
  if (accountId.value) {
    api.login.cancel({ account_id: accountId.value }).catch(() => {})
  }
})

const startProgressAnimation = () => {
  browserStartProgress.value = 0
  progressTimer = setInterval(() => {
    if (browserStartProgress.value < 90) {
      // 前90%快速增长，最后10%留给真实加载完成
      const increment = Math.random() * 15 + 5
      browserStartProgress.value = Math.min(90, browserStartProgress.value + increment)
    }
  }, 300)
}

const stopProgressAnimation = () => {
  if (progressTimer) {
    clearInterval(progressTimer)
    progressTimer = null
  }
}

const startSession = async () => {
  loadingQrcode.value = true
  try {
    const res = await api.login.getQrcode(accountId.value)
    if (res.code !== 200) {
      ElMessage.error(res.message || '启动浏览器失败')
      stopProgressAnimation()
      return
    }
    const data = res.data || {}
    loginStatus.value = data.status || 'waiting'
    if (data.qrcode) {
      qrcodeImage.value = `data:image/png;base64,${data.qrcode}`
    }
    browserStartProgress.value = 100
    stopProgressAnimation()
    currentStep.value = 2
    startStatusPoll()
    if (loginStatus.value === 'sms_required') {
      ElMessage.info('检测到手机号验证码登录，请在浏览器中完成验证')
    } else if (data.qrcode) {
      ElMessage.success('二维码获取成功，请扫码登录')
    }
  } catch (e) {
    ElMessage.error('启动失败：' + e.message)
    stopProgressAnimation()
  } finally {
    loadingQrcode.value = false
  }
}

const refreshQrcode = async () => {
  stopStatusPoll()
  stopProgressAnimation()
  loginStatus.value = 'waiting'
  qrcodeImage.value = null
  currentStep.value = 1
  startProgressAnimation()
  await startSession()
}

const startStatusPoll = () => {
  stopStatusPoll()
  statusPollTimer = setInterval(checkLoginStatus, 3000)
}

const stopStatusPoll = () => {
  if (statusPollTimer) {
    clearInterval(statusPollTimer)
    statusPollTimer = null
  }
}

const checkLoginStatus = async () => {
  if (!accountId.value) return
  try {
    const res = await api.login.getStatus(accountId.value)
    if (res.code === 200 && res.data) {
      loginStatus.value = res.data.status
      statusMessage.value = res.data.message
      if (res.data.status === 'logged_in') {
        stopStatusPoll()
        await completeLogin()
      } else if (res.data.status === 'failed') {
        stopStatusPoll()
      }
    }
  } catch {}
}

const completeLogin = async () => {
  if (submitting.value) return
  submitting.value = true
  try {
    const res = await api.login.complete({ account_id: accountId.value })
    if (res.code === 200) {
      currentStep.value = 3
      ElMessage.success('登录完成，cookies 已保存！')
      if (window.opener) {
        window.opener.postMessage({ type: 'login_success', account_id: accountId.value }, '*')
      }
    } else {
      ElMessage.error(res.message || '保存 cookies 失败')
      loginStatus.value = 'failed'
      statusMessage.value = res.message
    }
  } catch (e) {
    ElMessage.error(e.message || '保存 cookies 失败')
    loginStatus.value = 'failed'
  } finally {
    submitting.value = false
  }
}

const closeWindow = () => window.close()
</script>

<style scoped>
.login-helper-container {
  padding: 20px;
  max-width: 500px;
  margin: 0 auto;
}
.step {
  padding: 16px 0;
}
.step h3 {
  color: #409eff;
  margin-bottom: 16px;
}
.qrcode-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 20px;
  background: #f9f9f9;
  border-radius: 8px;
}
.qr-hint {
  margin-top: 10px;
  color: #666;
  font-size: 13px;
}
.error-message {
  margin: 20px 0;
}
</style>
