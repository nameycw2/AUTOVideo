<template>
  <div class="auth-page">
    <div class="auth-card">
      <div class="brand">
        <div class="brand-mark">AUTO</div>
        <div class="brand-title">矩阵宝</div>
        <div class="brand-subtitle">请先登录继续</div>
      </div>

      <div class="mode-toggle">
        <el-radio-group v-model="form.mode">
          <el-radio-button label="password">密码登录</el-radio-button>
          <el-radio-button label="code">邮箱验证码登录</el-radio-button>
        </el-radio-group>
      </div>

      <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
        <el-form-item v-if="form.mode === 'password'" label="用户名或邮箱" prop="loginId">
          <el-input v-model="form.loginId" placeholder="用户名或邮箱" />
        </el-form-item>
        <el-form-item v-if="form.mode === 'password'" label="密码" prop="password">
          <el-input v-model="form.password" type="password" show-password placeholder="请输入密码" />
        </el-form-item>
        <div v-if="form.mode === 'password'" class="forgot-password-link">
          <router-link to="/reset-password">忘记密码？</router-link>
        </div>

        <el-form-item v-if="form.mode === 'code'" label="邮箱" prop="email">
          <el-input v-model="form.email" placeholder="you@example.com" />
        </el-form-item>
        <el-form-item v-if="form.mode === 'code'" label="验证码" prop="code">
          <div class="code-row">
            <el-input v-model="form.code" placeholder="6位验证码" />
            <el-button :disabled="countdown > 0" @click="sendCode">
              {{ countdown > 0 ? `重新发送 (${countdown}s)` : '发送验证码' }}
            </el-button>
          </div>
        </el-form-item>

        <el-button type="primary" class="full-button" :loading="loading" @click="handleLogin">
          登录
        </el-button>
      </el-form>

      <div class="auth-footer">
        <span>没有账号？</span>
        <router-link to="/register">去注册</router-link>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../stores/auth'
import api from '../api'

const router = useRouter()
const authStore = useAuthStore()
const formRef = ref(null)
const loading = ref(false)

const form = reactive({
  mode: 'password',
  loginId: '',
  password: '',
  email: '',
  code: ''
})

const rules = {
  loginId: [
    { required: true, message: '用户名或邮箱不能为空', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '密码不能为空', trigger: 'blur' }
  ],
  email: [
    { required: true, message: '邮箱不能为空', trigger: 'blur' },
    { type: 'email', message: '邮箱格式不正确', trigger: 'blur' }
  ],
  code: [
    { required: true, message: '验证码不能为空', trigger: 'blur' }
  ]
}

const countdown = ref(0)
let timer = null

onBeforeUnmount(() => {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
})

const sendCode = async () => {
  if (!form.email) {
    ElMessage.error('请先输入邮箱')
    return
  }

  try {
    await api.auth.sendCode(form.email)
    ElMessage.success('验证码已发送')
    countdown.value = 60
    timer = setInterval(() => {
      if (countdown.value <= 1) {
        clearInterval(timer)
        countdown.value = 0
        return
      }
      countdown.value -= 1
    }, 1000)
  } catch (error) {
    ElMessage.error(error.message || '发送验证码失败')
  }
}

const handleLogin = async () => {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    loading.value = true
    const payload = form.mode === 'code'
      ? { mode: 'code', email: form.email, code: form.code }
      : { mode: 'password', username: form.loginId, password: form.password }
    try {
      const res = await api.auth.login(payload)
      // 兼容响应被包一层的情况（如代理返回 { data: { code, message, data, token } }）
      // 只有当res.data包含code字段时，才说明被代理包了一层，否则直接使用res
      let body = res
      if (res && res.data && typeof res.data === 'object' && res.data.code !== undefined) {
        // res.data有code字段，说明被包了一层，使用res.data
        body = res.data
      }
      // 否则body就是res本身（标准响应格式）
      
      const code = body && body.code
      const message = (body && body.message) || ''
      // 尝试多种方式提取token：body.data.token > body.token
      const token = (body && body.data && body.data.token) || (body && body.token)
      
      // console.log('登录响应:', { res, body, code, message, token, hasToken: !!token }) // 调试日志
      
      // 如果有token且状态码是200/201，登录成功
      if (token && (code === 200 || code === 201)) {
        authStore.setToken(String(token))
        // 从body.data或body中提取用户信息
        const userData = body.data || body
        authStore.username = userData.username ?? payload.username ?? payload.email ?? ''
        authStore.email = userData.email ?? payload.email ?? ''
        authStore.avatarUrl = userData.avatar_url ?? ''
        authStore.role = userData.role ?? ''
        authStore.parentId = userData.parent_id != null ? userData.parent_id : null
        router.replace('/')
        return
      }
      
      // 如果状态码是200/201但message包含成功信息，也认为是成功
      if (body && (code === 200 || code === 201) && /login\s*success|登录成功/i.test(message)) {
        ElMessage.success(message || '登录成功')
        // 如果没有token但有成功消息，可能是响应格式问题
        if (!token) {
          console.error('登录成功但未获取到token，响应格式:', body)
          ElMessage.warning('登录成功，但未获取到token，请刷新页面重试')
        }
      } else {
        // 如果code是200/201但没有token和成功消息，可能是响应格式问题
        if (code === 200 || code === 201) {
          console.error('登录响应格式异常:', body)
          ElMessage.error(message || '登录失败：响应格式异常，请查看控制台')
        } else {
          ElMessage.error(message || '登录失败')
        }
      }
    } catch (err) {
      const msg = err?.message || err?.data?.message || '登录失败'
      ElMessage.error(msg)
    } finally {
      loading.value = false
    }
  })
}
</script>

<style scoped>
.auth-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: radial-gradient(circle at top, #eef4ff 0%, #f8fafc 40%, #ffffff 100%);
  padding: 24px;
}

.auth-card {
  width: 100%;
  max-width: 420px;
  background: #ffffff;
  border-radius: 16px;
  padding: 32px;
  box-shadow: 0 20px 40px rgba(15, 23, 42, 0.12);
}

.brand {
  text-align: center;
  margin-bottom: 24px;
}

.brand-mark {
  display: inline-block;
  padding: 6px 12px;
  border-radius: 999px;
  background: #111827;
  color: #ffffff;
  font-weight: 700;
  letter-spacing: 1px;
  font-size: 12px;
}

.brand-title {
  margin-top: 12px;
  font-size: 22px;
  font-weight: 700;
  color: #111827;
}

.brand-subtitle {
  margin-top: 6px;
  font-size: 13px;
  color: #6b7280;
}

.full-button {
  width: 100%;
  margin-top: 8px;
}

.mode-toggle {
  display: flex;
  justify-content: center;
  margin-bottom: 16px;
}

.code-row {
  display: flex;
  gap: 8px;
}

.code-row .el-button {
  width: 140px;
}
.auth-footer {
  margin-top: 16px;
  text-align: center;
  font-size: 13px;
  color: #6b7280;
}

.forgot-password-link {
  text-align: right;
  margin-bottom: 8px;
  font-size: 13px;
}

.forgot-password-link a {
  color: #2563eb;
}

.auth-footer a {
  margin-left: 6px;
  color: #2563eb;
}
</style>
