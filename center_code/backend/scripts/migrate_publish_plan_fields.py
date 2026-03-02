# -*- coding: utf-8 -*-
"""
发布计划功能增强：数据库迁移脚本

功能：
1. 为 publish_plans 表添加 account_ids 字段（存储JSON格式的账号ID列表）
2. 为 plan_videos 表添加 schedule_time 字段（用于分阶段发布）
3. 为 plan_videos 表添加 video_description 字段（视频正文/描述）
4. 为 plan_videos 表添加 video_tags 字段（视频标签/话题）

使用方式（在 backend 目录下执行）：
    python -m scripts.migrate_publish_plan_fields

可重复执行：若字段已存在则跳过，不会报错。
"""
import sys
import os

# 保证从 backend 根目录运行时能导入 config、db
_backend = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend not in sys.path:
    sys.path.insert(0, _backend)

from sqlalchemy import text, inspect, create_engine


def check_column_exists(inspector, table_name, column_name):
    """检查表中是否存在指定列"""
    try:
        columns = inspector.get_columns(table_name)
        return any(col['name'] == column_name for col in columns)
    except Exception:
        return False


def main():
    try:
        from config import get_db_url
    except ImportError:
        print("错误：无法导入 config，请确保在 backend 目录下执行：")
        print("  cd center_code/backend")
        print("  python -m scripts.migrate_publish_plan_fields")
        return 1

    db_url = get_db_url()
    if not db_url:
        print("错误：未配置数据库连接（请检查 .env 或环境变量）")
        return 1

    engine = create_engine(db_url)
    inspector = inspect(engine)

    # 检查表是否存在
    table_names = inspector.get_table_names()
    if "publish_plans" not in table_names:
        print("表 publish_plans 不存在，请先初始化数据库。")
        return 1
    if "plan_videos" not in table_names:
        print("表 plan_videos 不存在，请先初始化数据库。")
        return 1

    # 按数据库类型确定是否使用反引号
    driver = (engine.url.drivername or "").lower()
    use_backticks = "mysql" in driver or "pymysql" in driver or "mariadb" in driver

    with engine.begin() as conn:
        # 1. 为 publish_plans 表添加 account_ids 字段
        if not check_column_exists(inspector, "publish_plans", "account_ids"):
            if use_backticks:
                sql = """ALTER TABLE `publish_plans` 
                         ADD COLUMN `account_ids` TEXT NULL 
                         COMMENT 'JSON字符串，存储指定的账号ID列表，如 "[1,2,3]"' 
                         AFTER `account_count`"""
            else:
                sql = """ALTER TABLE publish_plans 
                         ADD COLUMN account_ids TEXT NULL"""
            conn.execute(text(sql))
            print("✓ 已为 publish_plans 表添加 account_ids 字段")
        else:
            print("- publish_plans.account_ids 已存在，跳过")

        # 2. 为 plan_videos 表添加 schedule_time 字段
        if not check_column_exists(inspector, "plan_videos", "schedule_time"):
            if use_backticks:
                sql = """ALTER TABLE `plan_videos` 
                         ADD COLUMN `schedule_time` DATETIME NULL 
                         COMMENT '该视频的发布时间（用于分阶段发布），如果为NULL则使用计划的publish_time' 
                         AFTER `thumbnail_url`"""
            else:
                sql = """ALTER TABLE plan_videos 
                         ADD COLUMN schedule_time DATETIME NULL"""
            conn.execute(text(sql))
            print("✓ 已为 plan_videos 表添加 schedule_time 字段")
        else:
            print("- plan_videos.schedule_time 已存在，跳过")

        # 3. 为 plan_videos 表添加 video_description 字段
        if not check_column_exists(inspector, "plan_videos", "video_description"):
            if use_backticks:
                sql = """ALTER TABLE `plan_videos` 
                         ADD COLUMN `video_description` TEXT NULL 
                         COMMENT '视频正文/描述' 
                         AFTER `video_title`"""
            else:
                sql = """ALTER TABLE plan_videos 
                         ADD COLUMN video_description TEXT NULL"""
            conn.execute(text(sql))
            print("✓ 已为 plan_videos 表添加 video_description 字段")
        else:
            print("- plan_videos.video_description 已存在，跳过")

        # 4. 为 plan_videos 表添加 video_tags 字段
        if not check_column_exists(inspector, "plan_videos", "video_tags"):
            if use_backticks:
                sql = """ALTER TABLE `plan_videos` 
                         ADD COLUMN `video_tags` VARCHAR(500) NULL 
                         COMMENT '视频标签/话题，逗号分隔' 
                         AFTER `video_description`"""
            else:
                sql = """ALTER TABLE plan_videos 
                         ADD COLUMN video_tags VARCHAR(500) NULL"""
            conn.execute(text(sql))
            print("✓ 已为 plan_videos 表添加 video_tags 字段")
        else:
            print("- plan_videos.video_tags 已存在，跳过")

    print("\n✅ 迁移完成！所有字段已检查并添加。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

