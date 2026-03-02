<template>
  <div class="publish-plan-page">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <h3>发布计划管理</h3>
          <el-button type="primary" @click="handleCreate">
            <el-icon><Plus /></el-icon>
            新建发布计划
          </el-button>
        </div>
      </template>

      <!-- 筛选条件 -->
      <div class="filters">
        <el-select v-model="filters.platform" placeholder="选择平台" clearable style="width: 150px; margin-right: 10px;">
          <el-option label="抖音" value="douyin" />
          <el-option label="快手" value="kuaishou" />
          <el-option label="小红书" value="xiaohongshu" />
          <el-option label="微信视频号" value="weixin" />
          <el-option label="TikTok" value="tiktok" />
        </el-select>
        <el-select v-model="filters.status" placeholder="选择状态" clearable style="width: 150px; margin-right: 10px;">
          <el-option label="待发布" value="pending" />
          <el-option label="发布中" value="publishing" />
          <el-option label="发布成功" value="completed" />
          <el-option label="发布失败" value="failed" />
        </el-select>
        <el-input
          v-model="filters.search"
          placeholder="搜索计划名称"
          style="width: 250px; margin-right: 10px;"
          clearable
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
        <el-button type="primary" @click="loadPlans">查询</el-button>
        <el-button @click="resetFilters">重置</el-button>
      </div>

      <!-- 表格 -->
      <el-table 
        :data="plans" 
        v-loading="loading" 
        stripe 
        style="width: 100%; margin-top: 20px;"
        :row-key="row => row.id"
        @expand-change="(row, expandedRows) => handleExpandChange(row, expandedRows)"
      >
        <el-table-column type="expand" width="50">
          <template #default="{ row }">
            <div class="plan-videos-detail" v-loading="expandedPlans[row.id]?.loading">
              <div v-if="!expandedPlans[row.id] || expandedPlans[row.id].loading" class="loading-placeholder">
                <el-text type="info">加载中...</el-text>
              </div>
              <div v-else-if="expandedPlans[row.id].videos.length === 0" class="empty-videos">
                <el-empty description="该计划暂无视频" :image-size="80" />
              </div>
              <div v-else class="videos-list">
                <div 
                  v-for="(video, index) in expandedPlans[row.id].videos" 
                  :key="video.id"
                  class="video-item-card"
                >
                  <div class="video-item-header">
                    <div class="video-index">
                      <el-tag type="info" size="small">视频 {{ index + 1 }}</el-tag>
                    </div>
                    <div style="display: flex; gap: 8px; align-items: center;">
                      <div class="video-status">
                        <el-tag :type="getVideoStatusType(video.status)" size="small">
                          {{ getVideoStatusText(video.status) }}
                        </el-tag>
                      </div>
                      <el-button 
                        v-if="video.status === 'pending'"
                        link 
                        type="primary" 
                        size="small"
                        @click="handleEditVideo(row.id, video)"
                      >
                        编辑
                      </el-button>
                    </div>
                  </div>
                  <div class="video-item-content">
                    <div class="video-preview">
                      <el-image
                        v-if="video.thumbnail_url"
                        :src="video.thumbnail_url"
                        fit="cover"
                        style="width: 120px; height: 80px; border-radius: 4px;"
                        :preview-src-list="[video.thumbnail_url]"
                      />
                      <div v-else class="no-thumbnail">
                        <el-icon :size="40"><VideoPlay /></el-icon>
                      </div>
                    </div>
                    <div class="video-info">
                      <div class="info-row">
                        <span class="info-label">视频标题：</span>
                        <span class="info-value">{{ video.video_title || '未设置' }}</span>
                      </div>
                      <div class="info-row" v-if="video.video_description">
                        <span class="info-label">视频描述：</span>
                        <span class="info-value">{{ video.video_description }}</span>
                      </div>
                      <div class="info-row" v-if="video.video_tags">
                        <span class="info-label">标签/话题：</span>
                        <el-tag 
                          v-for="(tag, tagIndex) in video.video_tags.split(',')" 
                          :key="tagIndex"
                          size="small"
                          style="margin-right: 4px;"
                        >
                          {{ tag.trim() }}
                        </el-tag>
                      </div>
                      <div class="info-row">
                        <span class="info-label">发布时间：</span>
                        <span class="info-value">
                          {{ video.schedule_time ? new Date(video.schedule_time).toLocaleString('zh-CN') : (row.publish_time ? new Date(row.publish_time).toLocaleString('zh-CN') : '未设置') }}
                        </span>
                      </div>
                      <div class="info-row">
                        <span class="info-label">视频链接：</span>
                        <el-link :href="video.video_url" target="_blank" type="primary" :underline="false">
                          查看视频
                        </el-link>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="id" label="计划ID" width="100" />
        <el-table-column prop="plan_name" label="计划名称" min-width="200" />
        <el-table-column prop="platform" label="平台" width="100">
          <template #default="{ row }">
            <el-tag>{{ getPlatformText(row.platform) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="merchant_name" label="关联商家" width="150" />
        <el-table-column prop="video_count" label="视频数" width="100" />
        <el-table-column prop="published_count" label="已发布" width="100" />
        <el-table-column prop="pending_count" label="待发布" width="100" />
        <el-table-column prop="distribution_mode" label="分发模式" width="150">
          <template #default="{ row }">
            {{ getDistributionModeText(row.distribution_mode) }}
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)">{{ getStatusText(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="publish_time" label="发布时间" width="180">
          <template #default="{ row }">
            {{ row.publish_time ? new Date(row.publish_time).toLocaleString('zh-CN') : '-' }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="handleEdit(row)">编辑</el-button>
            <el-button link type="danger" size="small" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="pagination">
        <el-pagination
          :current-page="pagination.page"
          :page-size="pagination.size"
          :total="pagination.total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="handleSizeChange"
          @current-change="handlePageChange"
        />
      </div>
    </el-card>

    <!-- 创建/编辑对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogTitle"
      width="90%"
      :max-width="1200"
      destroy-on-close
    >
      <el-form :model="form" label-width="120px">
        <el-form-item label="计划名称" required>
          <el-input v-model="form.plan_name" placeholder="请输入计划名称" />
        </el-form-item>
        <el-form-item label="平台" required>
          <el-select v-model="form.platform" placeholder="请选择平台" style="width: 100%;">
            <el-option label="抖音" value="douyin" />
            <el-option label="快手" value="kuaishou" />
            <el-option label="小红书" value="xiaohongshu" />
            <el-option label="微信视频号" value="weixin" />
            <el-option label="TikTok" value="tiktok" />
          </el-select>
          <el-alert
            v-if="platformRulesTip"
            :title="platformRulesTip.title"
            :description="platformRulesTip.description"
            :type="platformRulesTip.type"
            show-icon
            style="margin-top: 8px;"
          />
        </el-form-item>
        <el-form-item label="关联商家">
          <el-select v-model="form.merchant_id" placeholder="请选择商家" clearable style="width: 100%;">
            <el-option
              v-for="merchant in merchants"
              :key="merchant.id"
              :label="merchant.merchant_name"
              :value="merchant.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="选择账号" required>
          <el-select
            v-model="form.account_ids"
            multiple
            filterable
            placeholder="请选择要使用的账号（可多选）"
            style="width: 100%;"
          >
            <el-option
              v-for="account in accounts"
              :key="account.id"
              :label="account.account_name"
              :value="account.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="分发模式">
          <el-select v-model="form.distribution_mode" placeholder="请选择分发模式" style="width: 100%;">
            <el-option label="手动分发" value="manual" />
            <el-option label="接收短信派发" value="sms" />
            <el-option label="扫二维码派发" value="qrcode" />
            <el-option label="AI智能分发" value="ai" />
          </el-select>
        </el-form-item>
        <el-form-item label="发布时间" v-if="form.publish_mode !== 'phased'">
          <el-date-picker
            v-model="form.publish_time"
            type="datetime"
            placeholder="选择发布时间"
            style="width: 100%;"
            value-format="YYYY-MM-DD HH:mm:ss"
          />
          <div style="font-size: 12px; color: #909399; margin-top: 4px;">
            批量发布时，所有视频将在此时间统一发布
          </div>
        </el-form-item>
        <el-form-item v-else>
          <template #label>
            <span>发布时间</span>
          </template>
          <el-text type="info" size="small">
            ℹ️ 分阶段发布模式下，请在下方为每个视频单独设置发布时间，无需在此设置统一发布时间
          </el-text>
        </el-form-item>
        <el-divider>视频与发布方式</el-divider>
        <el-form-item label="发布方式" required>
          <el-radio-group v-model="form.publish_mode">
            <el-radio label="phased">分阶段（按固定时间逐个发出）</el-radio>
            <el-radio label="batch">分批次（一次选择多个视频）</el-radio>
          </el-radio-group>
        </el-form-item>
        <div v-if="form.publish_mode === 'phased'">
          <el-form-item label="阶段列表" required>
            <div style="width: 100%;">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                <el-button type="primary" @click="addPhaseItem" :icon="Plus">
                  添加发布阶段
                </el-button>
                <el-text type="info" size="small" v-if="phasedItems.length > 0">
                  共 {{ phasedItems.length }} 个发布阶段
                </el-text>
              </div>
              
              <div v-if="phasedItems.length === 0" class="empty-phase-list">
                <el-empty description="暂无发布阶段" :image-size="100">
                  <el-button type="primary" @click="addPhaseItem">添加第一个阶段</el-button>
                </el-empty>
              </div>
              
              <div v-else class="phase-list" v-loading="videoLoading">
                <el-card 
                  v-for="(item, index) in phasedItems" 
                  :key="index"
                  class="phase-card"
                  shadow="hover"
                  :body-style="{ padding: '20px' }"
                >
                  <template #header>
                    <div class="phase-card-header">
                      <div class="phase-number">
                        <el-tag type="primary" size="large">阶段 {{ index + 1 }}</el-tag>
                      </div>
                      <div class="phase-actions">
                        <el-button 
                          link 
                          type="danger" 
                          size="small" 
                          @click="removePhaseItem(index)"
                          :icon="Delete"
                        >
                          删除
                        </el-button>
                      </div>
                    </div>
                  </template>
                  
                  <div class="phase-content">
                    <!-- 第一行：视频选择和发布时间 -->
                    <div class="phase-row">
                      <div class="phase-field" style="flex: 1;">
                        <label class="field-label">
                          <span class="required">*</span> 选择视频
                        </label>
                        <el-select 
                          v-model="item.video_id" 
                          placeholder="请选择视频" 
                          filterable 
                          style="width: 100%;" 
                          :loading="videoLoading"
                          @visible-change="onVideoDropdownOpened"
                          @change="handleVideoSelectChange(item, index)"
                        >
                          <el-option
                            v-for="video in videoLibrary"
                            :key="video.id"
                            :label="video.video_name || video.video_url"
                            :value="video.id"
                          >
                            <div style="display: flex; align-items: center;">
                              <el-image
                                v-if="video.thumbnail_url"
                                :src="video.thumbnail_url"
                                style="width: 40px; height: 30px; margin-right: 8px; border-radius: 4px;"
                                fit="cover"
                              />
                              <span>{{ video.video_name || video.video_url }}</span>
                            </div>
                          </el-option>
                          <el-option v-if="!videoLoading && videoLibrary.length === 0" disabled value="">
                            <span style="color: #909399;">暂无视频，请先上传或生成视频</span>
                          </el-option>
                        </el-select>
                      </div>
                      <div class="phase-field" style="width: 280px; margin-left: 16px;">
                        <label class="field-label">
                          <span class="required">*</span> 发布时间
                        </label>
                        <el-date-picker
                          v-model="item.schedule_time"
                          type="datetime"
                          placeholder="选择发布时间"
                          value-format="YYYY-MM-DD HH:mm:ss"
                          style="width: 100%;"
                        />
                      </div>
                    </div>
                    
                    <!-- 第二行：标题 -->
                    <div class="phase-row" style="margin-top: 16px;">
                      <div class="phase-field" style="flex: 1;">
                        <label class="field-label">视频标题</label>
                        <el-input
                          v-model="item.video_title"
                          :placeholder="titlePlaceholder"
                          :maxlength="titleMaxLength"
                          :minlength="titleMinLength > 0 ? titleMinLength : undefined"
                          show-word-limit
                        />
                        <div v-if="form.platform === 'xiaohongshu'" style="font-size: 12px; color: #e6a23c; margin-top: 4px;">
                          ⚠️ 小红书标题限制：最多20个字符
                        </div>
                        <div v-if="form.platform === 'weixin'" style="font-size: 12px; color: #e6a23c; margin-top: 4px;">
                          ⚠️ 微信视频号标题限制：6-16个字，符号仅支持书名号《》、引号""、冒号：、加号+、问号?、百分号%、摄氏度°，逗号可用空格代替
                        </div>
                      </div>
                    </div>
                    
                    <!-- 第三行：正文 -->
                    <div class="phase-row" style="margin-top: 16px;">
                      <div class="phase-field" style="flex: 1;">
                        <label class="field-label">视频正文/描述</label>
                        <el-input
                          v-model="item.video_description"
                          type="textarea"
                          :rows="3"
                          placeholder="输入视频正文或描述（可选，最多500字）"
                          maxlength="500"
                          show-word-limit
                        />
                      </div>
                    </div>
                    
                    <!-- 第四行：标签 -->
                    <div class="phase-row" style="margin-top: 16px;">
                      <div class="phase-field" style="flex: 1;">
                        <label class="field-label">标签/话题</label>
                        <el-input
                          v-model="item.video_tags"
                          :placeholder="`输入标签，用逗号分隔（可选，最多${tagMaxCount}个标签）`"
                          maxlength="200"
                        />
                        <div style="font-size: 12px; color: #909399; margin-top: 4px;">
                          💡 提示：多个标签请用逗号分隔，例如：美食,旅行,生活
                        </div>
                      </div>
                    </div>
                  </div>
                </el-card>
              </div>
            </div>
          </el-form-item>
        </div>
        <div v-else>
          <el-form-item label="选择视频" required>
            <el-select
              v-model="batchVideoIds"
              multiple
              filterable
              placeholder="从视频库选择多个视频"
              style="width: 100%;"
              :loading="videoLoading"
              @visible-change="onVideoDropdownOpened"
              @change="handleBatchVideoChange"
            >
              <el-option
                v-for="video in videoLibrary"
                :key="video.id"
                :label="video.video_name || video.video_url"
                :value="video.id"
              />
              <el-option v-if="!videoLoading && videoLibrary.length === 0" disabled value="">
                <span style="color: #909399;">暂无视频，请先上传或生成视频</span>
              </el-option>
            </el-select>
            <div v-if="!videoLoading && videoLibrary.length === 0" style="margin-top: 8px;">
              <el-text type="warning" size="small">视频成品库中暂无视频，请前往"视频库"页面上传或生成视频</el-text>
            </div>
          </el-form-item>
          <el-form-item v-if="batchVideoIds.length > 0" label="视频信息设置">
            <div class="batch-videos-list" v-loading="videoLoading">
              <div 
                v-for="(item, index) in batchVideoItems" 
                :key="item.video_id || index"
                class="batch-video-card"
              >
                <el-card shadow="hover" :body-style="{ padding: '20px' }">
                  <template #header>
                    <div class="batch-video-header">
                      <div class="video-index">
                        <el-tag type="info" size="large">视频 {{ index + 1 }}</el-tag>
                      </div>
                      <div class="video-name">
                        <el-text type="primary" size="small">
                          {{ getVideoName(item.video_id) || '未命名视频' }}
                        </el-text>
                      </div>
                    </div>
                  </template>
                  
                  <div class="batch-video-content">
                    <!-- 视频预览 -->
                    <div class="batch-video-preview">
                      <el-image
                        v-if="getVideoThumbnail(item.video_id)"
                        :src="getVideoThumbnail(item.video_id)"
                        fit="cover"
                        style="width: 120px; height: 80px; border-radius: 4px;"
                        :preview-src-list="[getVideoThumbnail(item.video_id)]"
                      />
                      <div v-else class="no-thumbnail">
                        <el-icon :size="40"><VideoPlay /></el-icon>
                      </div>
                    </div>
                    
                    <!-- 视频信息 -->
                    <div class="batch-video-info">
                      <!-- 标题 -->
                      <div class="batch-field">
                        <label class="field-label">视频标题</label>
                        <el-input
                          v-model="item.video_title"
                          :placeholder="titlePlaceholder"
                          :maxlength="titleMaxLength"
                          :minlength="titleMinLength > 0 ? titleMinLength : undefined"
                          show-word-limit
                        />
                        <div v-if="form.platform === 'xiaohongshu'" style="font-size: 12px; color: #e6a23c; margin-top: 4px;">
                          ⚠️ 小红书标题限制：最多20个字符
                        </div>
                        <div v-if="form.platform === 'weixin'" style="font-size: 12px; color: #e6a23c; margin-top: 4px;">
                          ⚠️ 微信视频号标题限制：6-16个字，符号仅支持书名号《》、引号""、冒号：、加号+、问号?、百分号%、摄氏度°，逗号可用空格代替
                        </div>
                      </div>
                      
                      <!-- 正文 -->
                      <div class="batch-field" style="margin-top: 16px;">
                        <label class="field-label">视频正文/描述</label>
                        <el-input
                          v-model="item.video_description"
                          type="textarea"
                          :rows="3"
                          placeholder="输入视频正文或描述（可选，最多500字）"
                          maxlength="500"
                          show-word-limit
                        />
                      </div>
                      
                      <!-- 标签 -->
                      <div class="batch-field" style="margin-top: 16px;">
                        <label class="field-label">标签/话题</label>
                        <el-input
                          v-model="item.video_tags"
                          :placeholder="`输入标签，用逗号分隔（可选，最多${tagMaxCount}个标签）`"
                          maxlength="200"
                        />
                        <div style="font-size: 12px; color: #909399; margin-top: 4px;">
                          💡 提示：多个标签请用逗号分隔，例如：美食,旅行,生活
                        </div>
                      </div>
                    </div>
                  </div>
                </el-card>
              </div>
            </div>
          </el-form-item>
          <el-form-item label="批次统一时间">
            <el-date-picker
              v-model="batchTime"
              type="datetime"
              placeholder="不选则使用上方发布时间或立即"
              style="width: 100%;"
              value-format="YYYY-MM-DD HH:mm:ss"
            />
          </el-form-item>
        </div>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmit">确定</el-button>
      </template>
    </el-dialog>

    <!-- 编辑视频对话框 -->
    <el-dialog
      v-model="videoEditDialogVisible"
      title="编辑视频信息"
      width="600px"
    >
      <el-form :model="videoEditForm" label-width="120px">
        <el-form-item label="视频标题">
          <el-input 
            v-model="videoEditForm.video_title" 
            :placeholder="videoEditTitlePlaceholder"
            :maxlength="videoEditTitleMaxLength"
            :minlength="videoEditTitleMinLength > 0 ? videoEditTitleMinLength : undefined"
            show-word-limit
          />
          <div v-if="videoEditForm.platform === 'xiaohongshu'" style="font-size: 12px; color: #e6a23c; margin-top: 4px;">
            ⚠️ 小红书标题限制：最多20个字符
          </div>
          <div v-if="videoEditForm.platform === 'weixin'" style="font-size: 12px; color: #e6a23c; margin-top: 4px;">
            ⚠️ 微信视频号标题限制：6-16个字，符号仅支持书名号《》、引号""、冒号：、加号+、问号?、百分号%、摄氏度°，逗号可用空格代替
          </div>
        </el-form-item>
        <el-form-item label="视频描述">
          <el-input
            v-model="videoEditForm.video_description"
            type="textarea"
            :rows="4"
            placeholder="输入视频正文或描述（可选，最多500字）"
            maxlength="500"
            show-word-limit
          />
        </el-form-item>
        <el-form-item label="标签/话题">
          <el-input
            v-model="videoEditForm.video_tags"
            placeholder="输入标签，用逗号分隔（可选，最多5个标签）"
            maxlength="200"
          />
          <div style="font-size: 12px; color: #909399; margin-top: 4px;">
            💡 提示：多个标签请用逗号分隔，例如：美食,旅行,生活
          </div>
        </el-form-item>
        <el-form-item label="发布时间">
          <el-date-picker
            v-model="videoEditForm.schedule_time"
            type="datetime"
            placeholder="选择发布时间（可选）"
            value-format="YYYY-MM-DD HH:mm:ss"
            style="width: 100%;"
          />
          <div style="font-size: 12px; color: #909399; margin-top: 4px;">
            💡 提示：不设置则使用计划的统一发布时间
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="videoEditDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleUpdateVideo">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, computed, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Delete, VideoPlay } from '@element-plus/icons-vue'
import { getPublishPlans, createPublishPlan, updatePublishPlan, deletePublishPlan, addVideoToPlan, savePublishInfo, getPlanVideos, updatePlanVideo } from '../api/publishPlans'
import { getMerchants } from '../api/merchants'
import { getOutputs } from '../api/material'
import api from '../api/index'

const loading = ref(false)
const plans = ref([])
const merchants = ref([])
const accounts = ref([])

const filters = ref({
  platform: '',
  status: '',
  search: ''
})

const pagination = ref({
  page: 1,
  size: 10,
  total: 0
})

const dialogVisible = ref(false)
const form = ref({
  id: null,
  plan_name: '',
  platform: 'douyin',
  merchant_id: null,
  distribution_mode: 'manual',
  publish_time: '',
  publish_mode: 'batch',
  account_ids: []
})
const videoLibrary = ref([])
const videoLoading = ref(false)
const phasedItems = ref([])
const batchVideoIds = ref([])
const batchVideoItems = ref([])  // 批量发布的视频信息列表
const batchTime = ref('')

// 展开行状态：存储每个计划的视频详情
const expandedPlans = ref({})

// 编辑视频对话框
const videoEditDialogVisible = ref(false)
const videoEditForm = ref({
  planId: null,
  videoId: null,
  video_title: '',
  video_description: '',
  video_tags: '',
  schedule_time: '',
  platform: '' // 添加平台字段
})

// 计算编辑视频时的标题最大长度（根据平台）
const videoEditTitleMaxLength = computed(() => {
  const platform = videoEditForm.value.platform
  if (platform === 'xiaohongshu') {
    return 20 // 小红书标题最多20个字符
  }
  return 100 // 其他平台默认100个字符
})

// 计算编辑视频时的标题提示文本
const videoEditTitlePlaceholder = computed(() => {
  const platform = videoEditForm.value.platform
  if (platform === 'xiaohongshu') {
    return '输入视频标题（可选，小红书最多20个字符）'
  }
  return '输入视频标题（可选，最多100字）'
})

const dialogTitle = computed(() => {
  return form.value.id ? '编辑发布计划' : '新建发布计划'
})

const getPlatformText = (platform) => {
  const map = {
    'douyin': '抖音',
    'kuaishou': '快手',
    'xiaohongshu': '小红书',
    'weixin': '微信视频号',
    'tiktok': 'TikTok'
  }
  return map[platform] || platform
}

// 计算标题最大长度（根据平台）
const titleMaxLength = computed(() => {
  const platform = form.value.platform
  if (platform === 'xiaohongshu') {
    return 20 // 小红书标题最多20个字符
  }
  if (platform === 'weixin') {
    return 16 // 微信视频号短标题最多16个字符
  }
  return 100 // 其他平台默认100个字符
})

// 计算标题最小长度（根据平台）
const titleMinLength = computed(() => {
  const platform = form.value.platform
  if (platform === 'weixin') {
    return 6 // 微信视频号短标题至少6个字符
  }
  return 0 // 其他平台无最小限制
})

// 计算标题提示文本（根据平台）
const titlePlaceholder = computed(() => {
  const platform = form.value.platform
  if (platform === 'xiaohongshu') {
    return '输入视频标题（可选，小红书最多20个字符）'
  }
  if (platform === 'weixin') {
    return '输入视频标题（可选，微信短标题6-16个字）'
  }
  return '输入视频标题（可选，最多100字）'
})

// 微信视频号短标题校验：6-16 字，符号仅支持书名号、引号、冒号、加号、问号、百分号、摄氏度，逗号用空格代替
function weixinShortTitleValidate(title) {
  if (!title || title.trim() === '') {
    return { valid: true } // 空标题允许（可选）
  }
  const s = title.trim()
  if (s.length < 6) {
    return { valid: false, message: '微信短标题至少 6 个字' }
  }
  if (s.length > 16) {
    return { valid: false, message: '微信短标题最多 16 个字' }
  }
  // 检查符号：仅支持书名号《》、引号""、冒号：、加号+、问号?、百分号%、摄氏度°，逗号可用空格代替
  // 允许的字符：中文、英文、数字、空格、书名号《》、引号""、冒号：、加号+、问号?、百分号%、摄氏度°
  // 移除所有允许的字符后，如果还有剩余字符，说明包含了不允许的符号
  const cleaned = s.replace(/[\u4e00-\u9fa5a-zA-Z0-9\s《》""：+?%°]/g, '')
  if (cleaned.length > 0) {
    return { valid: false, message: '微信短标题仅支持书名号《》、引号""、冒号：、加号+、问号?、百分号%、摄氏度°，逗号请用空格代替' }
  }
  return { valid: true }
}

// 计算标签最大数量（根据平台）
const tagMaxCount = computed(() => {
  const platform = form.value.platform
  if (platform === 'weixin') {
    return 10 // 微信视频号话题最多10个
  }
  if (platform === 'douyin') {
    return 5 // 抖音话题最多5个
  }
  return 10 // 其他平台默认10个
})

// 与立即发布一致的平台规则提示（标题/标签/正文等）
const platformRulesTip = computed(() => {
  const p = form.value.platform
  if (!p) return null
  const tips = {
    douyin: {
      title: '抖音发布规则',
      description: '标题最多 100 字；话题标签最多 5 个。',
      type: 'info'
    },
    xiaohongshu: {
      title: '小红书发布规则',
      description: '标题最多 20 个字符；正文+话题（#标签紧跟正文后，如 1234#话题1#话题2）；话题最多 20 个；封面由平台从视频帧生成。',
      type: 'warning'
    },
    weixin: {
      title: '微信视频号发布规则',
      description: '短标题 6-16 个字，符号仅支持书名号《》、引号""、冒号：、加号+、问号?、百分号%、摄氏度°，逗号可用空格代替；视频描述（正文）+ #话题；话题最多 10 个。',
      type: 'info'
    },
    kuaishou: {
      title: '快手发布规则',
      description: '标题最多 100 字；话题标签最多 10 个。',
      type: 'info'
    },
    tiktok: {
      title: 'TikTok 发布规则',
      description: '标题与描述按平台要求；话题最多 10 个。',
      type: 'info'
    }
  }
  return tips[p] || null
})

const getDistributionModeText = (mode) => {
  const map = {
    'manual': '手动分发',
    'sms': '接收短信派发',
    'qrcode': '扫二维码派发',
    'ai': 'AI智能分发'
  }
  return map[mode] || mode
}

const getStatusText = (status) => {
  const map = {
    'pending': '待发布',
    'publishing': '发布中',
    'completed': '发布成功',
    'failed': '发布失败'
  }
  return map[status] || status
}

const getStatusType = (status) => {
  const map = {
    'pending': 'warning',
    'publishing': 'info',
    'completed': 'success',
    'failed': 'danger'
  }
  return map[status] || 'info'
}

// 视频状态相关函数
const getVideoStatusText = (status) => {
  const map = {
    'pending': '待发布',
    'processing': '发布中',
    'published': '已发布',
    'failed': '发布失败'
  }
  return map[status] || status
}

const getVideoStatusType = (status) => {
  const map = {
    'pending': 'warning',
    'processing': 'info',
    'published': 'success',
    'failed': 'danger'
  }
  return map[status] || 'info'
}

// 加载计划视频详情
const loadPlanVideos = async (planId) => {
  // 如果已经加载过，直接返回
  if (expandedPlans.value[planId] && expandedPlans.value[planId].videos) {
    return
  }
  
  // 初始化加载状态
  if (!expandedPlans.value[planId]) {
    expandedPlans.value[planId] = {
      loading: true,
      videos: []
    }
  } else {
    expandedPlans.value[planId].loading = true
  }
  
  try {
    const response = await getPlanVideos(planId)
    if (response.code === 200 && response.data) {
      expandedPlans.value[planId] = {
        loading: false,
        videos: response.data.videos || []
      }
    } else {
      throw new Error(response.message || '加载视频详情失败')
    }
  } catch (error) {
    console.error('加载计划视频详情失败:', error)
    ElMessage.error('加载视频详情失败: ' + (error.message || '未知错误'))
    expandedPlans.value[planId] = {
      loading: false,
      videos: []
    }
  }
}

const loadPlans = async () => {
  try {
    loading.value = true
    const params = {
      platform: filters.value.platform || undefined,
      status: filters.value.status || undefined,
      limit: pagination.value.size,
      offset: (pagination.value.page - 1) * pagination.value.size
    }
    
    const response = await getPublishPlans(params)
            if (response.code === 200) {
              plans.value = response.data.plans
              pagination.value.total = response.data.total
            }
  } catch (error) {
    ElMessage.error('加载发布计划失败')
    console.error(error)
  } finally {
    loading.value = false
  }
}

const loadMerchants = async () => {
  try {
    const response = await getMerchants({ limit: 100 })
            if (response.code === 200) {
              merchants.value = response.data.merchants
            }
  } catch (error) {
    console.error('加载商家列表失败:', error)
  }
}

const loadAccounts = async (platform = 'douyin') => {
  try {
    const response = await api.accounts.list({ platform, limit: 100 })
    if (response.code === 200) {
      accounts.value = response.data.accounts
    }
  } catch (error) {
    console.error('加载账号列表失败:', error)
  }
}

const resetFilters = () => {
  filters.value = {
    platform: '',
    status: '',
    search: ''
  }
  loadPlans()
}

const handleSizeChange = (size) => {
  pagination.value.size = size
  pagination.value.page = 1
  loadPlans()
}

const handlePageChange = (page) => {
  pagination.value.page = page
  loadPlans()
}

const handleCreate = () => {
  form.value = {
    id: null,
    plan_name: '',
    platform: 'douyin',
    merchant_id: null,
    distribution_mode: 'manual',
    publish_time: '',
    publish_mode: 'batch',
    account_ids: []
  }
  phasedItems.value = []
  batchVideoIds.value = []
  batchVideoItems.value = []
  batchTime.value = ''
  loadAccounts('douyin')
  // 确保视频库已加载
  if (videoLibrary.value.length === 0 && !videoLoading.value) {
    loadVideoLibrary()
  }
  dialogVisible.value = true
}

const handleEdit = (row) => {
  form.value = {
    id: row.id,
    plan_name: row.plan_name,
    platform: row.platform,
    merchant_id: row.merchant_id,
    distribution_mode: row.distribution_mode,
    publish_time: row.publish_time ? new Date(row.publish_time).toISOString().slice(0, 19).replace('T', ' ') : '',
    publish_mode: 'batch',
    account_ids: []
  }
  phasedItems.value = []
  batchVideoIds.value = []
  batchVideoItems.value = []
  batchTime.value = ''
  loadAccounts(row.platform)
  // 确保视频库已加载
  if (videoLibrary.value.length === 0 && !videoLoading.value) {
    loadVideoLibrary()
  }
  dialogVisible.value = true
}

const handleDelete = async (row) => {
  try {
    await ElMessageBox.confirm('确定要删除该发布计划吗？', '提示', {
      type: 'warning'
    })
    
    const response = await deletePublishPlan(row.id)
            if (response.code === 200) {
              ElMessage.success('删除成功')
              loadPlans()
            }
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败')
      console.error(error)
    }
  }
}

const handleSubmit = async () => {
  if (!form.value.plan_name) {
    ElMessage.warning('请输入计划名称')
    return
  }
  if (!form.value.account_ids || form.value.account_ids.length === 0) {
    ElMessage.warning('请至少选择一个账号')
    return
  }
  if (form.value.publish_mode === 'phased') {
    const invalid = phasedItems.value.some(it => !it.video_id || !it.schedule_time)
    if (invalid) {
      ElMessage.warning('分阶段需为每行选择视频并设置时间')
      return
    }
    // 验证标题长度（根据平台）
    const maxTitleLength = titleMaxLength.value
    for (let i = 0; i < phasedItems.value.length; i++) {
      const item = phasedItems.value[i]
      if (item.video_title && item.video_title.length > maxTitleLength) {
        ElMessage.warning(
          form.value.platform === 'xiaohongshu'
            ? `阶段 ${i + 1} 的视频标题超过限制（小红书最多20个字符），请缩短标题`
            : `阶段 ${i + 1} 的视频标题超过限制（最多100个字符），请缩短标题`
        )
        return
      }
    }
  } else {
    if (!batchVideoIds.value || batchVideoIds.value.length === 0) {
      ElMessage.warning('请至少选择一个视频')
      return
    }
    // 验证标题长度和格式（根据平台）
    const maxTitleLength = titleMaxLength.value
    const minTitleLength = titleMinLength.value
    for (let i = 0; i < batchVideoItems.value.length; i++) {
      const item = batchVideoItems.value[i]
      if (item.video_title) {
        // 验证长度
        if (item.video_title.length > maxTitleLength) {
          let message = ''
          if (form.value.platform === 'xiaohongshu') {
            message = `视频 ${i + 1} 的标题超过限制（小红书最多20个字符），请缩短标题`
          } else if (form.value.platform === 'weixin') {
            message = `视频 ${i + 1} 的标题超过限制（微信短标题最多16个字），请缩短标题`
          } else {
            message = `视频 ${i + 1} 的标题超过限制（最多100个字符），请缩短标题`
          }
          ElMessage.warning(message)
          return
        }
        if (minTitleLength > 0 && item.video_title.length < minTitleLength) {
          ElMessage.warning(`视频 ${i + 1} 的标题少于限制（微信短标题至少6个字），请补充标题`)
          return
        }
        // 微信视频号符号验证
        if (form.value.platform === 'weixin') {
          const validateResult = weixinShortTitleValidate(item.video_title)
          if (!validateResult.valid) {
            ElMessage.warning(`视频 ${i + 1}: ${validateResult.message}`)
            return
          }
        }
      }
    }
  }
  
  try {
    // 对于分阶段发布，不设置计划的 publish_time，让每个视频使用各自的 schedule_time
    // 对于批量发布，使用计划的 publish_time
    const data = {
      plan_name: form.value.plan_name,
      platform: form.value.platform,
      merchant_id: form.value.merchant_id || undefined,
      distribution_mode: form.value.distribution_mode,
      publish_time: form.value.publish_mode === 'phased' ? undefined : (form.value.publish_time || undefined),
      account_ids: form.value.account_ids
    }
    
    let response
    let planId
    
    // 第一步：创建/更新计划
    if (form.value.id) {
      response = await updatePublishPlan(form.value.id, data)
      planId = form.value.id
    } else {
      response = await createPublishPlan(data)
      planId = response.data?.id
    }
    
    if (response.code !== 200 && response.code !== 201) {
      ElMessage.error(response.message || (form.value.id ? '更新失败' : '创建失败'))
      dialogVisible.value = false
      loadPlans()
      return
    }
    
    if (!planId) {
      ElMessage.warning('计划创建成功但未获取到ID')
      dialogVisible.value = false
      loadPlans()
      return
    }
    
    // 显示创建/更新成功消息
    ElMessage.success(form.value.id ? '更新成功' : '创建成功')
    
    // 第二步：添加视频和保存发布信息（异步执行，不影响用户体验）
    try {
      console.log('开始添加视频和保存发布信息...', { planId, publishMode: form.value.publish_mode })
      
      if (form.value.publish_mode === 'phased') {
        console.log('分阶段发布，视频数量:', phasedItems.value.length)
        for (const it of phasedItems.value) {
          const video = videoLibrary.value.find(v => v.id === it.video_id)
          if (video) {
            console.log('添加视频:', { videoId: it.video_id, videoName: video.video_name, scheduleTime: it.schedule_time })
            const addVideoResponse = await addVideoToPlan(planId, {
              video_url: video.video_url,
              video_title: it.video_title || video.video_name || '',
              video_description: it.video_description || '',
              video_tags: it.video_tags || '',
              thumbnail_url: video.thumbnail_url || '',
              schedule_time: it.schedule_time || undefined  // 传递该视频的发布时间
            })
            console.log('添加视频响应:', addVideoResponse)
          }
        }
        
        console.log('保存分阶段发布信息...')
        const saveInfoResponse = await savePublishInfo(planId, {
          publish_schedule: {
            mode: 'phased',
            items: phasedItems.value.map(it => {
              const v = videoLibrary.value.find(x => x.id === it.video_id)
              return {
                video_id: it.video_id,
                video_url: v?.video_url,
                schedule_time: it.schedule_time
              }
            })
          }
        })
        console.log('保存发布信息响应:', saveInfoResponse)
      } else {
        console.log('批量发布，视频数量:', batchVideoIds.value.length)
        for (const item of batchVideoItems.value) {
          const video = videoLibrary.value.find(v => v.id === item.video_id)
          if (video) {
            console.log('添加视频:', { videoId: item.video_id, videoName: video.video_name, title: item.video_title })
            const addVideoResponse = await addVideoToPlan(planId, {
              video_url: video.video_url,
              video_title: item.video_title || video.video_name || '',
              video_description: item.video_description || '',
              video_tags: item.video_tags || '',
              thumbnail_url: video.thumbnail_url || ''
            })
            console.log('添加视频响应:', addVideoResponse)
          }
        }
        
        console.log('保存批量发布信息...')
        const saveInfoResponse = await savePublishInfo(planId, {
          publish_schedule: {
            mode: 'batch',
            items: batchVideoIds.value.map(vid => {
              const v = videoLibrary.value.find(x => x.id === vid)
              return {
                video_id: vid,
                video_url: v?.video_url
              }
            }),
            batch_time: batchTime.value || form.value.publish_time || ''
          }
        })
        console.log('保存发布信息响应:', saveInfoResponse)
      }
      
      console.log('所有步骤成功完成！')
    } catch (error) {
      // 视频添加或发布信息保存失败（仅记录日志，不影响用户体验）
      console.error('添加视频或保存发布信息失败:', error)
      console.error('错误详情:', error.response || error)
    } finally {
      // 关闭对话框并刷新列表
      console.log('关闭对话框并刷新列表...')
      dialogVisible.value = false
      loadPlans()
    }
  } catch (error) {
    // 其他未知错误
    ElMessage.error('操作失败')
    console.error('未知错误:', error)
  }
}

// 监听平台变化，更新账号列表
watch(() => form.value.platform, (newPlatform) => {
  loadAccounts(newPlatform)
  // 清空已选择的账号，因为平台变了
  form.value.account_ids = []
})

onMounted(() => {
  loadPlans()
  loadMerchants()
  loadVideoLibrary()
})

const loadVideoLibrary = async () => {
  try {
    videoLoading.value = true
    // 从腾讯云COS获取成品视频列表（成品库视频存储在COS中，不在数据库）
    const response = await getOutputs()
    console.log('视频成品库API响应:', response) // 调试日志
    if (response.code === 200) {
      // 转换数据格式以匹配现有的视频库格式
      const outputs = response.data || []
      videoLibrary.value = outputs.map(output => ({
        id: output.id || output.cos_key || Math.random(),
        video_name: output.video_name || output.filename || '未命名',
        video_url: output.video_url || output.preview_url || output.download_url || '',
        // 只使用真正的缩略图URL，不要用视频URL作为缩略图（会导致加载失败）
        thumbnail_url: output.thumbnail_url || null,
        video_size: output.size || 0,
        duration: output.duration || 0,
        platform: output.platform || '',
        tags: output.tags || '',
        description: output.description || '',
        upload_time: output.update_time || output.created_at || '',
        created_at: output.created_at || output.update_time || '',
        cos_key: output.cos_key || '', // 保存COS key，便于后续使用
        filename: output.filename || ''
      }))
      console.log(`成功加载 ${videoLibrary.value.length} 个视频到视频库`)
      if (videoLibrary.value.length === 0) {
        ElMessage.warning('视频成品库中暂无视频，请先上传或生成视频')
      }
    } else {
      console.error('加载视频成品库失败，响应码:', response.code, '消息:', response.message)
      ElMessage.error(response.message || '加载视频成品库失败')
    }
  } catch (e) {
    console.error('加载视频成品库异常:', e)
    ElMessage.error('加载视频成品库失败: ' + (e.message || '未知错误'))
  } finally {
    videoLoading.value = false
  }
}

const onVideoDropdownOpened = (opened) => {
  if (opened && videoLibrary.value.length === 0 && !videoLoading.value) {
    loadVideoLibrary()
  }
}

// 处理表格展开/收起
const handleExpandChange = (row, expandedRows) => {
  // 如果展开，加载该计划的视频详情
  const isExpanded = expandedRows.some(r => r.id === row.id)
  if (isExpanded) {
    loadPlanVideos(row.id)
  }
}

// 获取视频名称（用于批量发布）
const getVideoName = (videoId) => {
  if (!videoId) return ''
  const video = videoLibrary.value.find(v => v.id === videoId)
  return video?.video_name || ''
}

// 获取视频缩略图（用于批量发布）
const getVideoThumbnail = (videoId) => {
  if (!videoId) return null
  const video = videoLibrary.value.find(v => v.id === videoId)
  return video?.thumbnail_url || null
}

const addPhaseItem = () => {
  phasedItems.value.push({ 
    video_id: null, 
    schedule_time: '',
    video_title: '',
    video_description: '',
    video_tags: ''
  })
}

// 处理批量视频选择变化
const handleBatchVideoChange = (selectedIds) => {
  // 更新 batchVideoItems，确保包含所有选中的视频
  const currentItems = batchVideoItems.value.map(item => item.video_id)
  const newItems = []
  
  for (const videoId of selectedIds) {
    const existingItem = batchVideoItems.value.find(item => item.video_id === videoId)
    if (existingItem) {
      newItems.push(existingItem)
    } else {
      const video = videoLibrary.value.find(v => v.id === videoId)
      newItems.push({
        video_id: videoId,
        video_name: video?.video_name || '',
        video_title: '',
        video_description: '',
        video_tags: ''
      })
    }
  }
  
  batchVideoItems.value = newItems
}

// 处理分阶段视频选择变化
const handleVideoSelectChange = (item, index) => {
  // 当选择视频后，可以自动填充视频名称作为默认标题
  if (item.video_id) {
    const video = videoLibrary.value.find(v => v.id === item.video_id)
    if (video && !item.video_title) {
      item.video_title = video.video_name || ''
    }
  }
}

const removePhaseItem = (idx) => {
  phasedItems.value.splice(idx, 1)
}

// 打开编辑视频对话框
const handleEditVideo = (planId, video) => {
  // 获取计划信息以确定平台
  const plan = plans.value.find(p => p.id === planId)
  videoEditForm.value = {
    planId: planId,
    videoId: video.id,
    video_title: video.video_title || '',
    video_description: video.video_description || '',
    video_tags: video.video_tags || '',
    schedule_time: video.schedule_time || '',
    platform: plan?.platform || '' // 保存平台信息
  }
  videoEditDialogVisible.value = true
}

// 更新视频信息
const handleUpdateVideo = async () => {
  try {
    const { planId, videoId, platform, ...updateData } = videoEditForm.value
    
    // 验证标题长度和格式（根据平台）
    if (updateData.video_title) {
      let maxLength = 100
      let minLength = 0
      if (platform === 'xiaohongshu') {
        maxLength = 20
      } else if (platform === 'weixin') {
        maxLength = 16
        minLength = 6
      }
      
      if (updateData.video_title.length > maxLength) {
        let message = ''
        if (platform === 'xiaohongshu') {
          message = '小红书标题最多20个字符，请缩短标题'
        } else if (platform === 'weixin') {
          message = '微信短标题最多16个字，请缩短标题'
        } else {
          message = '视频标题不能超过100个字符'
        }
        ElMessage.warning(message)
        return
      }
      
      if (minLength > 0 && updateData.video_title.length < minLength) {
        ElMessage.warning('微信短标题至少6个字，请补充标题')
        return
      }
      
      // 微信视频号符号验证
      if (platform === 'weixin') {
        const validateResult = weixinShortTitleValidate(updateData.video_title)
        if (!validateResult.valid) {
          ElMessage.warning(validateResult.message)
          return
        }
      }
    }
    
    // 如果 schedule_time 为空字符串，设置为 null
    if (updateData.schedule_time === '') {
      updateData.schedule_time = null
    }
    
    const response = await updatePlanVideo(planId, videoId, updateData)
    
    if (response.code === 200) {
      ElMessage.success('视频信息更新成功')
      videoEditDialogVisible.value = false
      
      // 刷新该计划的视频列表
      if (expandedPlans.value[planId]) {
        await loadPlanVideos(planId)
      }
      
      // 刷新计划列表
      await loadPlans()
    } else {
      ElMessage.error(response.message || '更新失败')
    }
  } catch (error) {
    console.error('更新视频信息失败:', error)
    ElMessage.error('更新视频信息失败: ' + (error.message || '未知错误'))
  }
}
</script>

<style scoped>
.publish-plan-page {
  padding: 0;
  width: 100%;
  max-width: 100%;
  overflow-x: auto;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.filters {
  display: flex;
  align-items: center;
  margin-bottom: 20px;
}

.pagination {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}

/* 分阶段发布列表样式 */
.empty-phase-list {
  padding: 40px 0;
  text-align: center;
}

.phase-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.phase-card {
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  transition: all 0.3s;
}

.phase-card:hover {
  border-color: #409eff;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
}

.phase-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.phase-number {
  font-weight: 600;
}

.phase-actions {
  display: flex;
  gap: 8px;
}

.phase-content {
  width: 100%;
}

.phase-row {
  display: flex;
  align-items: flex-start;
  gap: 16px;
}

.phase-field {
  display: flex;
  flex-direction: column;
}

.field-label {
  font-size: 14px;
  font-weight: 500;
  color: #606266;
  margin-bottom: 8px;
  display: flex;
  align-items: center;
}

.field-label .required {
  color: #f56c6c;
  margin-right: 4px;
}

/* 展开行视频详情样式 */
.plan-videos-detail {
  padding: 20px;
  background-color: #fafafa;
}

.loading-placeholder {
  padding: 40px;
  text-align: center;
}

.empty-videos {
  padding: 40px;
  text-align: center;
}

.videos-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.video-item-card {
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  padding: 16px;
  transition: all 0.3s;
}

.video-item-card:hover {
  border-color: #409eff;
  box-shadow: 0 2px 8px 0 rgba(0, 0, 0, 0.1);
}

.video-item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid #f0f0f0;
}

.video-index {
  font-weight: 600;
}

.video-item-content {
  display: flex;
  gap: 16px;
}

.video-preview {
  flex-shrink: 0;
}

.no-thumbnail {
  width: 120px;
  height: 80px;
  background-color: #f5f7fa;
  border: 1px dashed #dcdfe6;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #909399;
}

.video-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.info-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  line-height: 1.6;
}

.info-label {
  font-weight: 500;
  color: #606266;
  min-width: 80px;
  flex-shrink: 0;
}

.info-value {
  color: #303133;
  flex: 1;
  word-break: break-word;
}

/* 批量发布视频列表样式 */
.batch-videos-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.batch-video-card {
  width: 100%;
}

.batch-video-card .el-card {
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  transition: all 0.3s;
}

.batch-video-card .el-card:hover {
  border-color: #409eff;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
}

.batch-video-header {
  display: flex;
  align-items: center;
  gap: 12px;
}

.video-index {
  flex-shrink: 0;
}

.video-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.batch-video-content {
  display: flex;
  gap: 16px;
  width: 100%;
}

.batch-video-preview {
  flex-shrink: 0;
}

.batch-video-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0; /* 允许flex子元素收缩 */
}

.batch-field {
  display: flex;
  flex-direction: column;
  width: 100%;
}

/* 响应式布局：小屏幕时垂直排列 */
@media (max-width: 768px) {
  .batch-video-content {
    flex-direction: column;
  }
  
  .batch-video-preview {
    align-self: center;
  }
}
</style>
