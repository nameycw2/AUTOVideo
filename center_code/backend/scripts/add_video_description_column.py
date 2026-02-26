# -*- coding: utf-8 -*-
"""
数据库修复脚本：为 video_tasks 表添加 video_description 列（正文/描述）

使用方式（在 backend 目录下执行）：
    python -m scripts.add_video_description_column

可重复执行：若列已存在则跳过，不会报错。
"""
import sys
import os

# 保证从 backend 根目录运行时能导入 config、models
_backend = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend not in sys.path:
    sys.path.insert(0, _backend)

from sqlalchemy import create_engine, text, inspect


def main():
    try:
        from config import get_db_url
    except ImportError:
        print("错误：无法导入 config，请确保在 backend 目录下执行：")
        print("  cd center_code/backend")
        print("  python -m scripts.add_video_description_column")
        return 1

    db_url = get_db_url()
    if not db_url:
        print("错误：未配置数据库连接（请检查 .env 或环境变量）")
        return 1

    engine = create_engine(db_url)
    inspector = inspect(engine)

    if "video_tasks" not in inspector.get_table_names():
        print("表 video_tasks 不存在，请先初始化数据库（例如运行应用或 create_all）。")
        return 1

    existing = {c["name"] for c in inspector.get_columns("video_tasks")}
    if "video_description" in existing:
        print("video_tasks.video_description 已存在，无需修复。")
        return 0

    # 按数据库类型生成 ALTER（MySQL 用反引号，SQLite 不用）
    driver = (engine.url.drivername or "").lower()
    if "mysql" in driver or "pymysql" in driver:
        sql = "ALTER TABLE `video_tasks` ADD COLUMN `video_description` TEXT NULL"
    else:
        sql = 'ALTER TABLE video_tasks ADD COLUMN video_description TEXT NULL'

    with engine.begin() as conn:
        conn.execute(text(sql))

    print("已为 video_tasks 表添加 video_description 列，修复完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
