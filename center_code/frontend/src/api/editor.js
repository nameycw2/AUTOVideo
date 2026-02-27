import { apiClient } from './index'

/**
 * 视频剪辑 API
 */
export const editVideo = (data) => {
  return apiClient.post('/editor/edit', data)
}

export const editVideoAsync = (data) => {
  return apiClient.post('/editor/edit_async', data)
}

export const getTasks = (params) => {
  return apiClient.get('/tasks', { params })
}

export const getTask = (taskId) => {
  return apiClient.get(`/tasks/${taskId}`)
}

export const deleteTask = (taskId, deleteOutput = false) => {
  return apiClient.post(`/tasks/${taskId}/delete`, { delete_output: deleteOutput })
}

// 新增: 应用 AI 滤镜
// 对应后端接口: /api/video-editor/ai/filter
export const applyFilter = (data) => {
  return apiClient.post('/video-editor/ai/filter', data)
}

// 新增: 提交 IMS 云剪辑任务 (字幕特效)
export const submitImsTask = (data) => {
  return apiClient.post('/editor/submit_ims', data)
}