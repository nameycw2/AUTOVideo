-- 数据库迁移 SQL：在 video_edit_tasks 表中添加滤镜字段
-- 用法: 在 MySQL 命令行或工具中执行此 SQL

USE autovideo;  -- 请根据实际数据库名称修改

-- 检查字段是否已存在（可选，用于验证）
SELECT COLUMN_NAME 
FROM INFORMATION_SCHEMA.COLUMNS 
WHERE TABLE_SCHEMA = DATABASE() 
AND TABLE_NAME = 'video_edit_tasks' 
AND COLUMN_NAME IN ('filter_type', 'filter_intensity');

-- 添加 filter_type 字段（如果字段已存在会报错，可忽略）
ALTER TABLE video_edit_tasks 
ADD COLUMN filter_type VARCHAR(50) NULL COMMENT '滤镜类型（vintage/noir/cyberpunk等）' 
AFTER subtitle_path;

-- 添加 filter_intensity 字段（如果字段已存在会报错，可忽略）
ALTER TABLE video_edit_tasks 
ADD COLUMN filter_intensity FLOAT DEFAULT 1.0 COMMENT '滤镜强度（0.0-1.0）' 
AFTER filter_type;

-- 验证字段已添加
SHOW COLUMNS FROM video_edit_tasks LIKE 'filter%';

SELECT '✓ 迁移完成！滤镜字段已添加到 video_edit_tasks 表' AS message;
