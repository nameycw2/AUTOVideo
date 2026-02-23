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
      if (res && res.code === 200 && res.data && res.data.logged_in) {
        isLoggedIn.value = true
        username.value = res.data.username || ''
        email.value = res.data.email || ''
        avatarUrl.value = res.data.avatar_url || ''
        role.value = res.data.role || ''
        parentId.value = res.data.parent_id != null ? res.data.parent_id : null
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
      const tokenValue = res?.data?.token
      if (tokenValue) {
        setToken(tokenValue)
        username.value = res.data.username || payload.username || payload.email || ''
        email.value = res.data.email || payload.email || ''
        avatarUrl.value = res.data.avatar_url || ''
        role.value = res.data.role || ''
        parentId.value = res.data.parent_id != null ? res.data.parent_id : null
        return { success: true }
      }
      return { success: false, message: res?.message || 'Login failed' }
    } catch (error) {
      return { success: false, message: error.message || 'Login failed' }
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
    canManageUsers,
    checkLogin,
    login,
    register,
    logout
  }
})
