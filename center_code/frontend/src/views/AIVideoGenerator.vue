<template>
  <div class="ai-video-generator">
    <div class="page-header">
      <h1 class="page-title">AI 视频生成</h1>
      <p class="page-subtitle">一键生成高清短视频，支持多种 LLM 和 TTS 服务</p>
    </div>

    <div class="cards-container">
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">📝 文案设置</h3>
        </div>
        <div class="card-body">
          <div class="form-group">
            <label class="form-label">视频主题 <span class="required">*</span></label>
            <input 
              v-model="config.video_subject" 
              class="form-input" 
              placeholder="例如：生命的意义是什么"
            />
            <p class="form-hint">输入视频主题，AI 将自动生成脚本</p>
          </div>
          

          
          <div class="form-group">
            <label class="form-label">视频脚本</label>
            <textarea 
              v-model="config.video_script" 
              class="form-textarea" 
              rows="4"
              placeholder="留空则自动生成脚本"
            ></textarea>
            <p class="form-hint">可手动输入脚本，留空则自动生成</p>
          </div>

          <button 
            class="btn btn-primary btn-block" 
            @click="generateScript" 
            :disabled="isGeneratingScript || !config.video_subject"
          >
            <span v-if="isGeneratingScript" class="loading-spinner"></span>
            {{ isGeneratingScript ? '生成中...' : '生成脚本' }}
          </button>
          
          <div class="form-group">
            <label class="form-label">视频关键词</label>
            <input 
              v-model="config.video_keywords" 
              class="form-input" 
              placeholder="例如：life,city"
            />
            <p class="form-hint">用于生成素材搜索关键词，多个可用逗号分隔</p>
          </div>

          <button 
            class="btn btn-secondary btn-block" 
            @click="generateTerms" 
            :disabled="isGeneratingTerms || !config.video_subject"
          >
            <span v-if="isGeneratingTerms" class="loading-spinner"></span>
            {{ isGeneratingTerms ? '生成中...' : '生成关键词' }}
          </button>
          
          <div v-if="taskResult?.script" class="result-box">
            <div class="result-header">
              <span>生成的脚本</span>
              <button class="btn-copy" @click="copyScript">复制</button>
            </div>
            <div class="result-content">{{ taskResult.script }}</div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <h3 class="card-title">🎬 视频设置</h3>
        </div>
        <div class="card-body">
          <div class="form-group">
            <label class="form-label">素材来源</label>
            <select v-model="config.video_source" class="form-select">
              <option value="pexels">Pexels  （在线素材）</option>
              <option value="local">本地上传</option>
            </select>
          </div>
          

          
          <div class="form-group" v-if="config.video_source === 'local'">
            <label class="form-label">上传本地素材</label>
            <div class="upload-area" @click="triggerUpload" @dragover.prevent @drop.prevent="handleDrop">
              <input 
                ref="fileInput" 
                type="file" 
                multiple 
                accept="video/*,image/*" 
                style="display: none" 
                @change="handleFileSelect"
              />
              <div class="upload-placeholder" v-if="!localFiles.length">
                <span class="upload-icon">📁</span>
                <span>点击或拖拽上传视频/图片素材</span>
              </div>
              <div class="upload-files" v-else>
                <div class="file-item" v-for="(file, index) in localFiles" :key="index">
                  <span class="file-name">{{ file.name }}</span>
                  <span class="file-size">{{ formatFileSize(file.size) }}</span>
                  <button class="file-remove" @click.stop="removeFile(index)">✕</button>
                </div>
              </div>
            </div>
            <div v-if="localFiles.length" class="upload-actions">
              <button class="btn btn-secondary" type="button" @click="triggerUpload">
                + 添加素材
              </button>
              <button class="btn btn-secondary" type="button" @click="clearLocalFiles">
                清空全部素材
              </button>
            </div>
            <p class="form-hint">支持视频(mp4/mov)和图片(jpg/png)，将按脚本顺序使用</p>
          </div>
          
          <div class="form-row">
            <div class="form-group">
              <label class="form-label">视频比例</label>
              <select v-model="config.video_aspect" class="form-select">
                <option value="9:16">竖屏 9:16</option>
                <option value="16:9">横屏 16:9</option>
                <option value="1:1">方形 1:1</option>
              </select>
            </div>
            <div class="form-group">
              <label class="form-label">生成数量</label>
              <input v-model.number="config.video_count" type="number" min="1" max="5" class="form-input" />
            </div>
          </div>
          
          <div class="form-row">
            <div class="form-group">
              <label class="form-label">拼接模式</label>
              <select v-model="config.video_concat_mode" class="form-select">
                <option value="random">随机拼接</option>
                <option value="sequential">顺序拼接</option>
              </select>
            </div>
            <div class="form-group">
              <label class="form-label">片段时长(秒)</label>
              <input v-model.number="config.video_clip_duration" type="number" min="2" max="10" class="form-input" />
            </div>
          </div>
          
          <div class="form-group">
            <label class="form-label">转场效果</label>
            <select v-model="config.video_transition_mode" class="form-select">
              <option value="">无</option>
              <option value="fade">淡入淡出</option>
              <option value="slide">滑动</option>
            </select>
          </div>
          
          <div class="form-group">
            <label class="form-label">背景音乐</label>
            <select v-model="config.bgm_type" class="form-select">
              <option value="">无</option>
              <option value="random">随机</option>
            </select>
          </div>
          
          <div class="form-group" v-if="config.bgm_type">
            <label class="form-label">音乐音量: {{ Math.round(config.bgm_volume * 100) }}%</label>
            <input 
              v-model.number="config.bgm_volume" 
              type="range" 
              min="0" 
              max="1" 
              step="0.1" 
              class="form-range"
            />
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <h3 class="card-title">🎙️ 语音与字幕</h3>
        </div>
        <div class="card-body">
          <div class="form-group">
            <label class="form-label">音色</label>
            <select v-model="config.voice_name" class="form-select">
              <option v-for="voice in voices" :key="voice.id" :value="voice.id">
                {{ voice.name }}
              </option>
            </select>
          </div>
          
          <div class="form-group">
            <label class="form-label">语速: {{ config.voice_rate }}x</label>
            <input 
              v-model.number="config.voice_rate" 
              type="range" 
              min="0.5" 
              max="2" 
              step="0.1" 
              class="form-range"
            />
          </div>
          
          <div class="form-group">
            <label class="form-checkbox">
              <input v-model="config.subtitle_enabled" type="checkbox" />
              <span class="checkbox-label">启用字幕</span>
            </label>
          </div>
          
          <template v-if="config.subtitle_enabled">
            <div class="form-group">
              <label class="form-label">字幕位置</label>
              <select v-model="config.subtitle_position" class="form-select">
                <option value="bottom">底部</option>
                <option value="center">居中</option>
                <option value="top">顶部</option>
              </select>
            </div>
            
            <div class="form-group">
              <label class="form-label">字体大小: {{ config.font_size }}px</label>
              <input 
                v-model.number="config.font_size" 
                type="range" 
                min="30" 
                max="100" 
                step="5" 
                class="form-range"
              />
            </div>
            
            <div class="form-row">
              <div class="form-group">
                <label class="form-label">字体颜色</label>
                <input v-model="config.text_fore_color" type="color" class="form-color" />
              </div>
              <div class="form-group">
                <label class="form-label">字体描边颜色</label>
                <input v-model="config.stroke_color" type="color" class="form-color" />
              </div>
            </div>
            
            <div class="form-group">
              <label class="form-label">字体描边大小: {{ config.stroke_width }}px</label>
              <input 
                v-model.number="config.stroke_width" 
                type="range" 
                min="0" 
                max="5" 
                step="0.5" 
                class="form-range"
              />
            </div>
          </template>
        </div>
      </div>
    </div>

    <div class="action-bar">
      <button 
        class="btn btn-primary btn-lg" 
        @click="generateVideo" 
        :disabled="isGenerating || !config.video_subject"
      >
        <span v-if="isGenerating" class="loading-spinner"></span>
        {{ isGenerating ? '生成中...' : '开始生成视频' }}
      </button>
      <button class="btn btn-secondary btn-lg" @click="resetConfig">
        重置设置
      </button>
    </div>

    <div v-if="taskResult" class="result-panel">
      <div class="result-panel-header">
        <h3 class="result-panel-title">生成结果</h3>
      </div>
      <div class="result-panel-body">
        <div class="progress-section" v-if="taskResult.state === 'processing'">
          <div class="progress-bar">
            <div class="progress-fill" :style="{ width: taskResult.progress + '%' }"></div>
          </div>
          <span class="progress-text">{{ taskResult.progress }}%</span>
        </div>
        
        <div v-if="taskResult.terms && taskResult.terms.length" class="result-section">
          <h4 class="result-label">搜索关键词</h4>
          <div class="terms-list">
            <span v-for="term in taskResult.terms" :key="term" class="term-tag">{{ term }}</span>
          </div>
        </div>
        
        <div v-if="taskResult.videos && taskResult.videos.length" class="result-section">
          <h4 class="result-label">生成的视频</h4>
          <div class="videos-grid">
            <div v-for="(video, index) in taskResult.videos" :key="index" class="video-item">
              <video :src="video" controls class="video-player"></video>
              <a :href="video" download class="download-link">下载视频</a>
            </div>
          </div>
        </div>
        
        <div v-if="taskResult.error" class="error-section">
          <div class="error-icon">⚠️</div>
          <div class="error-message">{{ taskResult.error }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted } from 'vue'
import api, { apiClient } from '../api'

export default {
  name: 'AIVideoGenerator',
  setup() {
    const providers = ref([])
    const voices = ref([])
    const videoSources = ref([])
    const isGenerating = ref(false)
    const isGeneratingScript = ref(false)
    const isGeneratingTerms = ref(false)
    const taskResult = ref(null)
    const localFiles = ref([])
    const fileInput = ref(null)
    
    const config = ref({
      video_subject: '',
      video_script: '',
      video_keywords: '',
      video_aspect: '9:16',
      video_count: 1,
      video_concat_mode: 'random',
      video_clip_duration: 5,
      video_source: 'pexels',
      video_transition_mode: '',
      
      llm_provider: 'deepseek',
      
      voice_name: 'longanyang',
      voice_rate: 1.0,
      voice_volume: 1.0,
      
      subtitle_enabled: true,
      subtitle_position: 'bottom',
      font_size: 60,
      text_fore_color: '#FFFFFF',
      stroke_color: '#000000',
            stroke_width: 0.0,
      
      bgm_type: 'random',
      bgm_volume: 0.2,
    })
    
    const currentProvider = computed(() => {
      return providers.value.find(p => p.id === config.value.llm_provider)
    })
    
    const currentVideoSource = computed(() => {
      return videoSources.value.find(s => s.id === config.value.video_source)
    })
    
    const triggerUpload = () => {
      fileInput.value?.click()
    }
    
    const handleFileSelect = (e) => {
      const files = Array.from(e.target.files || [])
      localFiles.value = [...localFiles.value, ...files]
    }
    
    const handleDrop = (e) => {
      const files = Array.from(e.dataTransfer.files || [])
      localFiles.value = [...localFiles.value, ...files]
    }
    
    const removeFile = (index) => {
      localFiles.value.splice(index, 1)
    }

    const clearLocalFiles = () => {
      localFiles.value = []
      if (fileInput.value) {
        fileInput.value.value = ''
      }
    }
    
    const formatFileSize = (bytes) => {
      if (bytes < 1024) return bytes + ' B'
      if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
      return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
    }
    
    const fetchProviders = async () => {
      try {
        const res = await apiClient.get('/money-printer/providers')
        if (res.code === 200) {
          providers.value = res.data
        }
      } catch (e) {
        console.error('获取 LLM 提供商失败:', e)
      }
    }
    
    const fetchVoices = async () => {
      try {
        const res = await apiClient.get('/money-printer/voices', {
          params: { language: 'zh' }
        })
        if (res.code === 200) {
          voices.value = res.data
        }
      } catch (e) {
        console.error('获取音色列表失败:', e)
      }
    }
    
    const fetchVideoSources = async () => {
      try {
        const res = await apiClient.get('/money-printer/video-sources')
        if (res.code === 200) {
          videoSources.value = res.data
        }
      } catch (e) {
        console.error('获取视频来源失败:', e)
      }
    }
    
    const onProviderChange = () => {
      config.value.api_key = ''
    }
    
    const generateScript = async () => {
      if (!config.value.video_subject) {
        alert('请输入视频主题')
        return
      }
      
      isGeneratingScript.value = true
      
      try {
        const payload = {
          video_subject: config.value.video_subject,
          llm_provider: config.value.llm_provider,
        }
        
        const res = await apiClient.post('/money-printer/script/generate', payload)
        
        if (res.code === 200) {
          config.value.video_script = res.data.script
          if (!taskResult.value) {
            taskResult.value = {}
          }
          taskResult.value.script = res.data.script
        } else {
          alert(res.message || '生成脚本失败')
        }
      } catch (e) {
        console.error('生成脚本失败:', e)
        alert(e.message || '生成脚本失败')
      } finally {
        isGeneratingScript.value = false
      }
    }

    const generateTerms = async () => {
      if (!config.value.video_subject) {
        alert('请输入视频主题')
        return
      }
      
      isGeneratingTerms.value = true
      
      try {
        const payload = {
          video_subject: config.value.video_subject,
          video_script: config.value.video_script,
          llm_provider: config.value.llm_provider,
          keywords: config.value.video_keywords,
        }
        
        const res = await apiClient.post('/money-printer/terms/generate', payload)
        
        if (res.code === 200) {
          config.value.video_keywords = (res.data.terms || []).join(', ')
        } else {
          alert(res.message || '生成关键词失败')
        }
      } catch (e) {
        console.error('生成关键词失败:', e)
        alert(e.message || '生成关键词失败')
      } finally {
        isGeneratingTerms.value = false
      }
    }
    
    const copyScript = () => {
      if (taskResult.value?.script) {
        navigator.clipboard.writeText(taskResult.value.script)
        alert('已复制到剪贴板')
      }
    }
    
    const generateVideo = async () => {
      if (!config.value.video_subject) {
        alert('请输入视频主题')
        return
      }
      
      if (config.value.video_source === 'local' && !localFiles.value.length) {
        alert('请上传本地素材')
        return
      }
      
      isGenerating.value = true
      taskResult.value = { state: 'processing', progress: 0 }
      
      try {
        let videoMaterials = null
        
        if (config.value.video_source === 'local' && localFiles.value.length) {
          taskResult.value = { state: 'processing', progress: 0, message: '正在上传素材...' }
          
          const uploadedPaths = []
          for (const file of localFiles.value) {
            const formData = new FormData()
            formData.append('file', file)
            
            const uploadRes = await apiClient.post('/money-printer/upload', formData, {
              headers: { 'Content-Type': 'multipart/form-data' }
            })
            
            if (uploadRes.code === 200) {
              uploadedPaths.push(uploadRes.data.path)
            }
          }
          
          videoMaterials = uploadedPaths
        }
        
        taskResult.value = { state: 'processing', progress: 0, message: '正在生成视频...' }
        
        const payload = {
          ...config.value,
          video_materials: videoMaterials
        }
        
        const res = await apiClient.post('/money-printer/video/full', payload)
        
        if (res.code === 200) {
          taskResult.value = res.data
        } else {
          taskResult.value = {
            state: 'failed',
            error: res.message || '生成失败'
          }
        }
      } catch (e) {
        console.error('生成视频失败:', e)
        taskResult.value = {
          state: 'failed',
          error: e.message || '生成失败'
        }
      } finally {
        isGenerating.value = false
      }
    }
    
    const resetConfig = () => {
      config.value = {
        video_subject: '',
        video_script: '',
        video_keywords: '',
        video_aspect: '9:16',
        video_count: 1,
        video_concat_mode: 'random',
        video_clip_duration: 5,
        video_source: 'pexels',
        video_transition_mode: '',
        
        llm_provider: 'deepseek',
        
        voice_name: 'longanyang',
        voice_rate: 1.0,
        voice_volume: 1.0,
        
        subtitle_enabled: true,
        subtitle_position: 'bottom',
        font_size: 60,
        text_fore_color: '#FFFFFF',
        stroke_color: '#000000',
                stroke_width: 0.0,
        
        bgm_type: 'random',
        bgm_volume: 0.2,
      }
      taskResult.value = null
    }
    
    onMounted(() => {
      fetchProviders()
      fetchVoices()
    })
    
    return {
      config,
      providers,
      voices,
      videoSources,
      currentProvider,
      currentVideoSource,
      isGenerating,
      isGeneratingScript,
      isGeneratingTerms,
      taskResult,
      localFiles,
      fileInput,
      onProviderChange,
      generateScript,
      generateTerms,
      copyScript,
      generateVideo,
      resetConfig,
      triggerUpload,
      handleFileSelect,
      handleDrop,
      removeFile,
      clearLocalFiles,
      formatFileSize,
    }
  }
}
</script>

<style scoped>
.ai-video-generator {
  padding: 20px;
  max-width: 1400px;
  margin: 0 auto;
}

.page-header {
  margin-bottom: 24px;
}

.page-title {
  font-size: 24px;
  font-weight: 600;
  color: #1a1a2e;
  margin: 0 0 4px 0;
}

.page-subtitle {
  font-size: 14px;
  color: #666;
  margin: 0;
}

.cards-container {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
  margin-bottom: 20px;
}

.card {
  background: #fff;
  border: 1px solid #e8e8e8;
  border-radius: 8px;
  overflow: hidden;
}

.card-header {
  padding: 16px 20px;
  border-bottom: 1px solid #f0f0f0;
  background: #fafafa;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-title {
  font-size: 15px;
  font-weight: 600;
  color: #1a1a2e;
  margin: 0;
}

.card-actions {
  display: flex;
  align-items: center;
}

.api-key-hint {
  padding: 8px 12px;
  background: #f0f7ff;
  border: 1px solid #d0e6ff;
  border-radius: 6px;
  font-size: 13px;
  color: #1976d2;
  margin-bottom: 4px;
}

.card-body {
  padding: 20px;
}

.form-group {
  margin-bottom: 16px;
}

.form-group:last-child {
  margin-bottom: 0;
}

.form-label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: #333;
  margin-bottom: 6px;
}

.required {
  color: #e74c3c;
}

.form-input,
.form-select,
.form-textarea {
  width: 100%;
  padding: 8px 12px;
  font-size: 13px;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  background: #fff;
  transition: all 0.2s;
}

.form-input:focus,
.form-select:focus,
.form-textarea:focus {
  outline: none;
  border-color: #4a90d9;
  box-shadow: 0 0 0 2px rgba(74, 144, 217, 0.1);
}

.form-textarea {
  resize: vertical;
  min-height: 80px;
}

.form-hint {
  font-size: 12px;
  color: #999;
  margin: 4px 0 0 0;
}

.form-row {
  display: flex;
  gap: 12px;
}

.form-row .form-group {
  flex: 1;
}

.form-range {
  width: 100%;
  height: 6px;
  border-radius: 3px;
  background: #e0e0e0;
  outline: none;
  -webkit-appearance: none;
  margin-top: 4px;
}

.form-range::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #4a90d9;
  cursor: pointer;
  border: 2px solid #fff;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
}

.form-color {
  width: 100%;
  height: 36px;
  padding: 2px;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  cursor: pointer;
}

.form-checkbox {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 8px 0;
}

.form-checkbox input {
  width: 16px;
  height: 16px;
  cursor: pointer;
}

.checkbox-label {
  font-size: 13px;
  color: #333;
}

.btn {
  padding: 8px 16px;
  font-size: 13px;
  font-weight: 500;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border: none;
}

.btn-block {
  width: 100%;
}

.btn-primary {
  background: #4a90d9;
  color: #fff;
}

.btn-primary:hover:not(:disabled) {
  background: #357abd;
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-secondary {
  background: #fff;
  color: #666;
  border: 1px solid #d9d9d9;
}

.btn-secondary:hover {
  border-color: #4a90d9;
  color: #4a90d9;
}

.btn-lg {
  padding: 12px 24px;
  font-size: 14px;
}

.loading-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid #fff;
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.result-box {
  margin-top: 16px;
  padding: 12px;
  background: #f9fafb;
  border-radius: 6px;
  border: 1px solid #e8e8e8;
}

.result-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  font-size: 12px;
  font-weight: 500;
  color: #666;
}

.btn-copy {
  padding: 2px 8px;
  font-size: 12px;
  background: #fff;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  cursor: pointer;
  color: #666;
}

.btn-copy:hover {
  border-color: #4a90d9;
  color: #4a90d9;
}

.result-content {
  font-size: 13px;
  line-height: 1.6;
  color: #333;
  white-space: pre-wrap;
  max-height: 150px;
  overflow-y: auto;
}

.action-bar {
  display: flex;
  gap: 12px;
  justify-content: center;
  margin-bottom: 20px;
}

.result-panel {
  background: #fff;
  border: 1px solid #e8e8e8;
  border-radius: 8px;
  overflow: hidden;
}

.result-panel-header {
  padding: 16px 20px;
  border-bottom: 1px solid #f0f0f0;
  background: #fafafa;
}

.result-panel-title {
  font-size: 15px;
  font-weight: 600;
  color: #1a1a2e;
  margin: 0;
}

.result-panel-body {
  padding: 20px;
}

.progress-section {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.progress-bar {
  flex: 1;
  height: 8px;
  background: #e0e0e0;
  border-radius: 4px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #4a90d9, #357abd);
  transition: width 0.3s;
}

.progress-text {
  font-size: 14px;
  font-weight: 500;
  color: #4a90d9;
  min-width: 50px;
}

.result-section {
  margin-bottom: 16px;
}

.result-section:last-child {
  margin-bottom: 0;
}

.result-label {
  font-size: 13px;
  font-weight: 600;
  color: #333;
  margin: 0 0 8px 0;
}

.terms-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.term-tag {
  padding: 4px 12px;
  background: #e3f2fd;
  color: #1976d2;
  border-radius: 16px;
  font-size: 12px;
}

.videos-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
}

.video-item {
  background: #f9fafb;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid #e8e8e8;
}

.video-player {
  width: 100%;
  max-height: 300px;
  display: block;
}

.download-link {
  display: block;
  padding: 10px;
  text-align: center;
  color: #4a90d9;
  text-decoration: none;
  font-size: 13px;
  border-top: 1px solid #e8e8e8;
}

.download-link:hover {
  background: #f0f0f0;
}

.error-section {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px;
  background: #fef2f2;
  border-radius: 6px;
  border: 1px solid #fecaca;
}

.error-icon {
  font-size: 18px;
}

.error-message {
  font-size: 13px;
  color: #dc2626;
}

.upload-area {
  border: 2px dashed #d9d9d9;
  border-radius: 8px;
  padding: 20px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
  background: #fafafa;
}

.upload-area:hover {
  border-color: #4a90d9;
  background: #f0f7ff;
}

.upload-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  color: #999;
  font-size: 13px;
}

.upload-icon {
  font-size: 32px;
}

.upload-files {
  text-align: left;
}

.upload-actions {
  margin-top: 10px;
  display: flex;
  justify-content: flex-start;
  gap: 8px;
}

.file-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: #fff;
  border-radius: 4px;
  margin-bottom: 6px;
  border: 1px solid #e8e8e8;
}

.file-item:last-child {
  margin-bottom: 0;
}

.file-name {
  flex: 1;
  font-size: 13px;
  color: #333;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-size {
  font-size: 12px;
  color: #999;
}

.file-remove {
  width: 20px;
  height: 20px;
  border: none;
  background: #fee2e2;
  color: #dc2626;
  border-radius: 50%;
  cursor: pointer;
  font-size: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.file-remove:hover {
  background: #fecaca;
}

@media (max-width: 1100px) {
  .cards-container {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 750px) {
  .cards-container {
    grid-template-columns: 1fr;
  }
  
  .action-bar {
    flex-direction: column;
  }
  
  .action-bar .btn {
    width: 100%;
  }
}
</style>
