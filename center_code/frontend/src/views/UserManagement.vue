<template>
  <div class="user-management-page">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <h3>用户管理</h3>
          <el-button v-if="canCreate" type="primary" @click="openCreate">
            <el-icon><Plus /></el-icon>
            新建用户
          </el-button>
        </div>
      </template>

      <el-table :data="list" v-loading="loading" stripe style="width: 100%;">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="username" label="用户名" min-width="120" />
        <el-table-column prop="email" label="邮箱" min-width="180" />
        <el-table-column prop="role" label="角色" width="120">
          <template #default="{ row }">
            <el-tag v-if="row.role === 'super_admin'" type="danger">超级管理员</el-tag>
            <el-tag v-else-if="row.role === 'parent'" type="warning">母账号</el-tag>
            <el-tag v-else type="info">子账号</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="parent_username" label="归属母账号" width="130">
          <template #default="{ row }">
            {{ row.parent_username || '-' }}
          </template>
        </el-table-column>
        <el-table-column v-if="isSuperAdmin" prop="child_count" label="子账号数" width="110" align="center">
          <template #default="{ row }">
            <span v-if="row.role === 'parent'">
              {{ row.child_count != null ? row.child_count : 0 }} / {{ row.max_children != null ? row.max_children : '不限' }}
            </span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="175">
          <template #default="{ row }">
            {{ row.created_at ? formatTime(row.created_at) : '-' }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openEdit(row)">编辑</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 新建用户 -->
    <el-dialog v-model="createVisible" title="新建用户" width="480px" @close="resetCreateForm">
      <el-form :model="createForm" label-width="90px">
        <el-form-item label="用户名" required>
          <el-input v-model="createForm.username" placeholder="至少2个字符" />
        </el-form-item>
        <el-form-item label="邮箱" required>
          <el-input v-model="createForm.email" placeholder="登录/找回密码用" />
        </el-form-item>
        <el-form-item label="密码" required>
          <el-input v-model="createForm.password" type="password" placeholder="至少8位" show-password />
        </el-form-item>
        <el-form-item v-if="isSuperAdmin" label="角色" required>
          <el-radio-group v-model="createForm.role">
            <el-radio value="parent">母账号</el-radio>
            <el-radio value="child">子账号</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="createForm.role === 'child' && isSuperAdmin" label="归属母账号" required>
          <el-select v-model="createForm.parent_id" placeholder="选择母账号" style="width: 100%;">
            <el-option v-for="p in parents" :key="p.id" :label="parentOptionLabel(p)" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="createForm.role === 'parent' && isSuperAdmin" label="子账号数量上限">
          <el-input-number v-model="createForm.max_children" :min="0" :max="9999" placeholder="留空不限制" style="width: 100%;" :controls="true" />
          <div class="form-tip">留空表示不限制该母账号下属子账号数量</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="createSubmitting" @click="submitCreate">确定</el-button>
      </template>
    </el-dialog>

    <!-- 编辑用户（改密码/邮箱；超管可设母账号子账号上限） -->
    <el-dialog v-model="editVisible" title="编辑用户" width="440px" @close="resetEditForm">
      <el-form :model="editForm" label-width="120px">
        <el-form-item label="用户名">
          <span>{{ editForm.username }}</span>
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="editForm.email" placeholder="邮箱" />
        </el-form-item>
        <el-form-item label="新密码">
          <el-input v-model="editForm.password" type="password" placeholder="留空则不修改" show-password />
        </el-form-item>
        <el-form-item v-if="isSuperAdmin && editForm.role === 'parent'" label="子账号数量上限">
          <el-input-number v-model="editForm.max_children" :min="0" :max="9999" placeholder="留空不限制" style="width: 100%;" :controls="true" />
          <div class="form-tip">当前已有 {{ editForm.child_count != null ? editForm.child_count : 0 }} 个子账号，上限不能低于该值</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="editSubmitting" @click="submitEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { useAuthStore } from '../stores/auth'
import api from '../api'

const authStore = useAuthStore()
const loading = ref(false)
const list = ref([])
const myRole = ref('')

const canCreate = computed(() => authStore.canManageUsers())
const isSuperAdmin = computed(() => authStore.role === 'super_admin')

const parents = ref([])
const createVisible = ref(false)
const createForm = ref({ username: '', email: '', password: '', role: 'child', parent_id: null, max_children: null })
const createSubmitting = ref(false)

const editVisible = ref(false)
const editForm = ref({ id: null, username: '', email: '', password: '', role: '', max_children: null, child_count: null })
const editSubmitting = ref(false)

function formatTime (t) {
  if (!t) return '-'
  const d = new Date(t)
  return d.toLocaleString('zh-CN')
}

async function loadList () {
  loading.value = true
  try {
    const res = await api.users.list()
    if (res && res.code === 200 && res.data) {
      list.value = res.data.list || []
      myRole.value = res.data.my_role || ''
    }
  } catch (e) {
    ElMessage.error(e?.message || '加载用户列表失败')
  } finally {
    loading.value = false
  }
}

async function loadParents () {
  if (authStore.role !== 'super_admin') return
  try {
    const res = await api.users.parents()
    if (res && res.code === 200 && res.data) {
      parents.value = res.data.list || []
    }
  } catch (e) {
    parents.value = []
  }
}

function parentOptionLabel (p) {
  const cap = p.max_children != null ? p.max_children : '不限'
  return `${p.username}（${p.child_count ?? 0}/${cap}）`
}

function openCreate () {
  createForm.value = { username: '', email: '', password: '', role: 'child', parent_id: null, max_children: null }
  if (authStore.role === 'super_admin') loadParents()
  createVisible.value = true
}

function resetCreateForm () {
  createForm.value = { username: '', email: '', password: '', role: 'child', parent_id: null, max_children: null }
}

async function submitCreate () {
  const { username, email, password, role, parent_id } = createForm.value
  if (!username || username.length < 2) {
    ElMessage.warning('用户名至少2个字符')
    return
  }
  if (!email || !email.includes('@')) {
    ElMessage.warning('请输入有效邮箱')
    return
  }
  if (!password || password.length < 8) {
    ElMessage.warning('密码至少8位')
    return
  }
  if (role === 'child' && authStore.role === 'super_admin' && (parent_id == null || parent_id === '')) {
    ElMessage.warning('请选择归属母账号')
    return
  }
  createSubmitting.value = true
  try {
    const payload = { username, email, password, role }
    if (role === 'child' && authStore.role === 'super_admin') payload.parent_id = parent_id
    if (role === 'parent' && authStore.role === 'super_admin' && createForm.value.max_children != null && createForm.value.max_children !== '') payload.max_children = createForm.value.max_children
    const res = await api.users.create(payload)
    if (res && res.code === 201) {
      ElMessage.success('创建成功')
      createVisible.value = false
      loadList()
    } else {
      ElMessage.error(res?.message || '创建失败')
    }
  } catch (e) {
    ElMessage.error(e?.message || '创建失败')
  } finally {
    createSubmitting.value = false
  }
}

function openEdit (row) {
  editForm.value = {
    id: row.id,
    username: row.username,
    email: row.email,
    password: '',
    role: row.role,
    max_children: row.max_children != null ? row.max_children : null,
    child_count: row.child_count != null ? row.child_count : 0
  }
  editVisible.value = true
}

function resetEditForm () {
  editForm.value = { id: null, username: '', email: '', password: '', role: '', max_children: null, child_count: null }
}

async function submitEdit () {
  const { id, email, password, role, max_children } = editForm.value
  const payload = {}
  if (email) payload.email = email
  if (password && password.length >= 8) payload.password = password
  if (isSuperAdmin && role === 'parent' && max_children !== undefined) payload.max_children = max_children == null || max_children === '' ? null : max_children
  if (Object.keys(payload).length === 0) {
    ElMessage.info('未修改任何项')
    return
  }
  editSubmitting.value = true
  try {
    const res = await api.users.update(id, payload)
    if (res && res.code === 200) {
      ElMessage.success('保存成功')
      editVisible.value = false
      loadList()
    } else {
      ElMessage.error(res?.message || '保存失败')
    }
  } catch (e) {
    ElMessage.error(e?.message || '保存失败')
  } finally {
    editSubmitting.value = false
  }
}

onMounted(() => {
  loadList()
})
</script>

<style scoped>
.user-management-page { padding: 16px; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.card-header h3 { margin: 0; font-size: 18px; }
.form-tip { font-size: 12px; color: var(--el-text-color-secondary); margin-top: 4px; }
</style>
