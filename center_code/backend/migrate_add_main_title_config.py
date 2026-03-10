"""
数据库迁移脚本：在 video_edit_tasks 表中添加主标题配置字段
Usage: python migrate_add_main_title_config.py
"""
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text
from db import get_db

def migrate_add_main_title_config():
    """添加 main_title_config 字段到 video_edit_tasks 表"""
    try:
        with get_db() as db:
            # 检查字段是否已存在
            check_sql = text("""
                SELECT COLUMN_NAME 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_SCHEMA = DATABASE() 
                AND TABLE_NAME = 'video_edit_tasks' 
                AND COLUMN_NAME = 'main_title_config'
            """)
            result = db.execute(check_sql).fetchall()
            existing_columns = [row[0] for row in result]
            
            if 'main_title_config' in existing_columns:
                print("✓ main_title_config 字段已存在，无需迁移")
                return True
            
            # 添加 main_title_config 字段（JSON 类型）
            print("正在添加 main_title_config 字段...")
            alter_sql = text("""
                ALTER TABLE video_edit_tasks 
                ADD COLUMN main_title_config JSON NULL 
                COMMENT '主标题配置（JSON格式：{font_size, color, stroke_color}）' 
                AFTER filter_intensity
            """)
            db.execute(alter_sql)
            db.commit()
            print("✓ main_title_config 字段添加成功")
            print("\n✓ 迁移完成！")
            return True
            
    except Exception as e:
        print(f"✗ 迁移失败：{str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    print("=" * 60)
    print("数据库迁移：添加主标题配置字段")
    print("=" * 60)
    migrate_add_main_title_config()
