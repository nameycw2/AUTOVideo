import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '../api'

const TOKEN_KEY = 'auth_token'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem(TOKEN_KEY) || '')
  const isLoggedIn = ref(!!token.value)
  const username = ref('')
  const email = ref('')
  const avatarUrl = ref('')
  const role = ref('')
  const parentId = ref(null)
  const isCheckingLogin = ref(false)

  const setToken = (value) => {
    token.value = value
    if (value) {
      localStorage.setItem(TOKEN_KEY, value)
      isLoggedIn.value = true
    } else {
      localStorage.removeItem(TOKEN_KEY)
      isLoggedIn.value = false
    }
  }

  const checkLogin = async () => {
    if (!token.value) {
      isLoggedIn.value = false
      return false
    }

    if (isCheckingLogin.value) {
      return isLoggedIn.value
    }

    isCheckingLogin.value = true
    try {
      const res = await api.auth.checkLogin()
      // 兼容响应被包一层的情况（如代理返回 { data: { code, message, data } }）
      const body = (res && res.data && typeof res.data === 'object' && (res.data.code !== undefined || (res.data.data && res.data.data.logged_in !== undefined)))
        ? res.data
        : res
      if (body && body.code === 200 && body.data && body.data.logged_in) {
        isLoggedIn.value = true
        username.value = body.data.username || ''
        email.value = body.data.email || ''
        avatarUrl.value = body.data.avatar_url || ''
        role.value = body.data.role || ''
        parentId.value = body.data.parent_id != null ? body.data.parent_id : null
        return true
      }

      setToken('')
      username.value = ''
      email.value = ''
      avatarUrl.value = ''
      role.value = ''
      parentId.value = null
      return false
    } catch (error) {
      setToken('')
      username.value = ''
      email.value = ''
      avatarUrl.value = ''
      return false
    } finally {
      isCheckingLogin.value = false
    }
  }

  const login = async (payload) => {
    try {
      const res = await api.auth.login(payload)
      const data = res?.data
      const tokenValue = (data && data.token) || res?.token
      if (tokenValue && (res?.code === 200 || res?.code === 201)) {
        setToken(String(tokenValue))
        username.value = (data && data.username) ?? payload?.username ?? payload?.email ?? ''
        email.value = (data && data.email) ?? payload?.email ?? ''
        avatarUrl.value = (data && data.avatar_url) ?? ''
        role.value = (data && data.role) ?? ''
        parentId.value = data && data.parent_id != null ? data.parent_id : null
        return { success: true }
      }
      return { success: false, message: res?.message || '登录失败' }
    } catch (error) {
      const msg = error?.message || error?.data?.message || '登录失败'
      return { success: false, message: msg }
    }
  }

  const register = async (payload) => {
    try {
      const res = await api.auth.register(payload)
      if (res.code === 201) {
        return { success: true }
      }
      return { success: false, message: res.message || 'Register failed' }
    } catch (error) {
      return { success: false, message: error.message || 'Register failed' }
    }
  }

  const logout = async () => {
    try {
      await api.auth.logout()
    } catch (error) {
      console.error('Logout error:', error)
    } finally {
      setToken('')
      username.value = ''
      email.value = ''
      avatarUrl.value = ''
      role.value = ''
      parentId.value = null
    }
  }

  const canManageUsers = () => {
    return role.value === 'super_admin' || role.value === 'parent'
  }

  return {
    token,
    isLoggedIn,
    username,
    email,
    avatarUrl,
    role,
    parentId,
    isCheckingLogin,
    setToken,
    canManageUsers,
    checkLogin,
    login,
    register,
    logout
  }
})
