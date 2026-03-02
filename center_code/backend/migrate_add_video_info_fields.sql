-- 为 plan_videos 表添加视频信息字段（标题、正文、标签）
-- 执行方式：在 MySQL 命令行或工具中执行此 SQL

-- 为 plan_videos 表添加 video_description 字段（视频正文/描述）
ALTER TABLE `plan_videos` 
ADD COLUMN `video_description` TEXT NULL COMMENT '视频正文/描述' 
AFTER `video_title`;

-- 为 plan_videos 表添加 video_tags 字段（视频标签/话题）
ALTER TABLE `plan_videos` 
ADD COLUMN `video_tags` VARCHAR(500) NULL COMMENT '视频标签/话题，逗号分隔' 
AFTER `video_description`;

-- 验证字段是否添加成功
-- SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_COMMENT 
-- FROM INFORMATION_SCHEMA.COLUMNS 
-- WHERE TABLE_SCHEMA = DATABASE() 
--   AND TABLE_NAME = 'plan_videos'
--   AND COLUMN_NAME IN ('video_description', 'video_tags');

