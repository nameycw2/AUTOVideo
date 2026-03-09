<template>
  <div class="login-helper-container">
    <el-card>
      <template #header>
        <h2>🎬 抖音账号登录助手</h2>
      </template>

      <div v-if="!accountId" class="error-message">
        <el-alert type="error" :closable="false">
          <template #title>错误：缺少账号ID参数</template>
        </el-alert>
      </div>

      <div v-else>
        <!-- 步骤 1: 获取二维码 -->
        <div class="step" :class="{ hidden: currentStep < 1 }">
          <h3>步骤 1: 获取登录二维码</h3>
          <p>点击下面的按钮，系统将自动打开浏览器并获取登录二维码。</p>
          <el-button 
            type="primary" 
            @click="getQrcode" 
            :loading="loadingQrcode"
            :disabled="qrcodeLoaded"
          >
            {{ qrcodeLoaded ? '二维码已加载' : (loadingQrcode ? '正在获取二维码...' : '获取二维码') }}
          </el-button>
          
          <!-- 显示二维码 -->
          <div v-if="qrcodeImage" class="qrcode-container" style="margin-top: 20px;">
            <el-image
              :src="qrcodeImage"
              style="width: 300px; height: 300px; border: 1px solid #ddd; border-radius: 8px;"
              fit="contain"
            />
            <p style="margin-top: 10px; color: #666;">
              <el-icon><InfoFilled /></el-icon>
              请使用抖音APP扫描上方二维码完成登录
            </p>
          </div>
          
          <el-alert 
            v-if="qrcodeError" 
            type="error" 
            :closable="false" 
            style="margin-top: 10px;"
            :title="qrcodeError"
          />
        </div>

        <!-- 步骤 2: 等待扫码登录 -->
        <div class="step" :class="{ hidden: currentStep < 2 }">
          <h3>步骤 2: 等待扫码登录</h3>
          <div v-if="loginStatus === 'waiting'">
            <el-alert type="info" :closable="false" style="margin: 10px 0;">
              <template #title>
                <el-icon><Loading /></el-icon>
                等待用户扫码...
              </template>
            </el-alert>
          </div>
          <div v-else-if="loginStatus === 'scanning'">
            <el-alert type="warning" :closable="false" style="margin: 10px 0;">
              <template #title>
                <el-icon><Loading /></el-icon>
                已扫描，等待用户确认登录...
              </template>
            </el-alert>
          </div>
          <div v-else-if="loginStatus === 'sms_required'">
            <el-alert type="info" :closable="false" style="margin: 10px 0;">
              <template #title>
                <el-icon><Loading /></el-icon>
                检测到手机号验证码登录，请在浏览器中完成验证...
              </template>
            </el-alert>
          </div>
          <div v-else-if="loginStatus === 'logged_in'">
            <el-alert type="success" :closable="false" style="margin: 10px 0;">
              <template #title>
                <el-icon><Check /></el-icon>
                登录成功！正在保存cookies...
              </template>
            </el-alert>
          </div>
          <div v-else-if="loginStatus === 'failed'">
            <el-alert type="error" :closable="false" style="margin: 10px 0;">
              <template #title>
                登录失败：{{ statusMessage }}
              </template>
            </el-alert>
            <el-button type="primary" @click="getQrcode" style="margin-top: 10px;">
              重新获取二维码
            </el-button>
          </div>
        </div>


        <!-- 步骤 3: 登录完成 -->
        <div class="step" :class="{ hidden: currentStep < 3 }">
          <el-result icon="success" title="登录完成" sub-title="Cookies 已成功保存到服务器！">
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
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Loading, Check, InfoFilled } from '@element-plus/icons-vue'
import api from '../api'

const route = useRoute()
const accountId = ref(null)
const currentStep = ref(1)
const loadingQrcode = ref(false)
const qrcodeImage = ref(null)
const qrcodeError = ref(null)
const qrcodeLoaded = ref(false)
const loginStatus = ref('waiting') // waiting, scanning, sms_required, logged_in, failed
const statusMessage = ref('')
const submitting = ref(false)
const submitStatus = ref(null)
let statusPollTimer = null


onMounted(() => {
  // 从 URL 参数获取 account_id
  accountId.value = route.query.account_id ? parseInt(route.query.account_id) : null
  
  if (!accountId.value) {
    ElMessage.error('缺少账号ID参数')
  } else {
    // 自动获取二维码
    getQrcode()
  }
})

onUnmounted(() => {
  // 清理定时器
  if (statusPollTimer) {
    clearInterval(statusPollTimer)
    statusPollTimer = null
  }
  
  // 取消登录会话
  if (accountId.value) {
    api.login.cancel({ account_id: accountId.value }).catch(err => {
      console.warn('取消登录会话失败:', err)
    })
  }
})

// 获取二维码
const getQrcode = async () => {
  if (!accountId.value) {
    ElMessage.error('缺少账号ID参数')
    return
  }
  
  loadingQrcode.value = true
  qrcodeError.value = null
  qrcodeImage.value = null
  
  try {
    const response = await api.login.getQrcode(accountId.value)
    
    if (response.code === 200 && response.data) {
      if (response.data.qrcode) {
        qrcodeImage.value = `data:image/png;base64,${response.data.qrcode}`
        qrcodeLoaded.value = true
      }
      loginStatus.value = response.data.status || 'waiting'
      currentStep.value = 2
      
      // 开始轮询登录状态
      startPollingStatus()
      
      if (loginStatus.value === 'sms_required') {
        ElMessage.info('检测到手机号验证码登录，请在浏览器中完成验证')
      } else {
        ElMessage.success('二维码获取成功，请扫码登录')
      }
    } else {
      qrcodeError.value = response.message || '获取二维码失败'
      ElMessage.error(qrcodeError.value)
    }
  } catch (error) {
    qrcodeError.value = error.message || '获取二维码失败'
    ElMessage.error(qrcodeError.value)
    console.error('获取二维码失败:', error)
  } finally {
    loadingQrcode.value = false
  }
}

// 开始轮询登录状态
const startPollingStatus = () => {
  // 清除之前的定时器
  if (statusPollTimer) {
    clearInterval(statusPollTimer)
  }
  
  // 立即检查一次
  checkLoginStatus()
  
  // 每 5 秒检查一次（间隔不宜过短，避免后端频繁读页面导致二维码页被刷新/失效）
  statusPollTimer = setInterval(() => {
    checkLoginStatus()
  }, 5000)
}

// 检查登录状态
const checkLoginStatus = async () => {
  if (!accountId.value) {
    return
  }
  
  try {
    const response = await api.login.getStatus(accountId.value)
    
    if (response.code === 200 && response.data) {
      const data = response.data
      loginStatus.value = data.status
      statusMessage.value = data.message
      
      if (data.status === 'logged_in') {
        // 登录成功，停止轮询
        if (statusPollTimer) {
          clearInterval(statusPollTimer)
          statusPollTimer = null
        }
        
        // 自动完成登录并保存cookies
        await completeLogin()
      } else if (data.status === 'failed') {
        // 登录失败，停止轮询
        if (statusPollTimer) {
          clearInterval(statusPollTimer)
          statusPollTimer = null
        }
      }
    }
  } catch (error) {
    console.error('检查登录状态失败:', error)
  }
}

// 完成登录并保存cookies
const completeLogin = async () => {
  if (!accountId.value) {
    return
  }
  
  submitting.value = true
  
  try {
    const response = await api.login.complete({ account_id: accountId.value })
    
    if (response.code === 200) {
      currentStep.value = 3
      ElMessage.success('登录完成，cookies已保存！')
      
      // 通知父窗口（如果存在）
      if (window.opener) {
        window.opener.postMessage({
          type: 'login_success',
          account_id: accountId.value
        }, '*')
      }
    } else {
      ElMessage.error(response.message || '保存cookies失败')
      loginStatus.value = 'failed'
      statusMessage.value = response.message || '保存cookies失败'
    }
  } catch (error) {
    ElMessage.error(error.message || '保存cookies失败')
    loginStatus.value = 'failed'
    statusMessage.value = error.message || '保存cookies失败'
    console.error('完成登录失败:', error)
  } finally {
    submitting.value = false
  }
}

const closeWindow = () => {
  window.close()
}
</script>

<style scoped>
.login-helper-container {
  padding: 20px;
  max-width: 800px;
  margin: 0 auto;
}

.step {
  margin-bottom: 30px;
  padding: 20px;
  background: #f5f5f5;
  border-radius: 8px;
  border-left: 4px solid #409eff;
}

.step.hidden {
  display: none;
}

.step h3 {
  color: #409eff;
  margin-bottom: 15px;
  font-size: 18px;
}

.step p {
  color: #666;
  line-height: 1.6;
  margin-bottom: 10px;
}

.step .tip {
  color: #999;
  font-size: 12px;
}

.code-block {
  position: relative;
  background: #2d2d2d;
  color: #f8f8f2;
  padding: 15px;
  border-radius: 5px;
  font-family: 'Courier New', monospace;
  font-size: 12px;
  overflow-x: auto;
  margin: 15px 0;
}

.code-block pre {
  margin: 0;
  white-space: pre-wrap;
  word-wrap: break-word;
}

.copy-btn {
  position: absolute;
  top: 10px;
  right: 10px;
}

.error-message {
  margin: 20px 0;
}

.qrcode-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 20px;
  background: #f5f5f5;
  border-radius: 8px;
}
</style>
