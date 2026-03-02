-- 发布计划功能增强：添加账号ID列表和视频发布时间字段
-- 执行方式：在 MySQL 命令行或工具中执行此 SQL

-- 1. 为 publish_plans 表添加 account_ids 字段（存储JSON格式的账号ID列表）
ALTER TABLE `publish_plans` 
ADD COLUMN `account_ids` TEXT NULL COMMENT 'JSON字符串，存储指定的账号ID列表，如 "[1,2,3]"' 
AFTER `account_count`;

-- 2. 为 plan_videos 表添加 schedule_time 字段（用于分阶段发布）
ALTER TABLE `plan_videos` 
ADD COLUMN `schedule_time` DATETIME NULL COMMENT '该视频的发布时间（用于分阶段发布），如果为NULL则使用计划的publish_time' 
AFTER `thumbnail_url`;

-- 验证字段是否添加成功
-- SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_COMMENT 
-- FROM INFORMATION_SCHEMA.COLUMNS 
-- WHERE TABLE_SCHEMA = DATABASE() 
--   AND TABLE_NAME IN ('publish_plans', 'plan_videos')
--   AND COLUMN_NAME IN ('account_ids', 'schedule_time');

