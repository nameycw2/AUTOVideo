"""
为 video_tasks 表添加缺失的 video_description 列（若表为旧 schema 则缺少该列）。
运行一次即可：python migrate_add_video_description.py
"""
import sys
from pathlib import Path

# 确保 backend 在路径中
sys.path.insert(0, str(Path(__file__).resolve().parent))

from db import engine
from sqlalchemy import text


def main():
    url = str(engine.url)
    if "mysql" not in url and "pymysql" not in url:
        print("当前未使用 MySQL，跳过迁移。")
        return

    with engine.begin() as conn:
        # 检查列是否已存在（MySQL）
        r = conn.execute(text("""
            SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'video_tasks'
              AND COLUMN_NAME = 'video_description'
        """))
        exists = r.scalar() > 0

        if exists:
            print("video_tasks.video_description 已存在，无需迁移。")
            return

        print("正在添加 video_tasks.video_description ...")
        conn.execute(text("""
            ALTER TABLE video_tasks
            ADD COLUMN video_description TEXT NULL COMMENT '正文/描述' AFTER video_title
        """))
    print("✓ video_description 添加成功。")


if __name__ == "__main__":
    main()
