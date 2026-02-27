"""
数据库迁移脚本：在 video_edit_tasks 表中添加滤镜字段
Usage: python migrate_add_filter_fields.py
"""
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from db import get_db

def migrate_add_filter_fields():
    """添加 filter_type 和 filter_intensity 字段到 video_edit_tasks 表"""
    try:
        with get_db() as db:
            # 检查字段是否已存在
            check_sql = """
                SELECT COLUMN_NAME 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_SCHEMA = DATABASE() 
                AND TABLE_NAME = 'video_edit_tasks' 
                AND COLUMN_NAME IN ('filter_type', 'filter_intensity')
            """
            result = db.execute(check_sql).fetchall()
            existing_columns = [row[0] for row in result]
            
            if 'filter_type' in existing_columns and 'filter_intensity' in existing_columns:
                print("✓ 字段已存在，无需迁移")
                return True
            
            # 添加 filter_type 字段
            if 'filter_type' not in existing_columns:
                print("正在添加 filter_type 字段...")
                alter_sql_1 = """
                    ALTER TABLE video_edit_tasks 
                    ADD COLUMN filter_type VARCHAR(50) NULL COMMENT '滤镜类型（vintage/noir/cyberpunk等）' 
                    AFTER subtitle_path
                """
                db.execute(alter_sql_1)
                print("✓ filter_type 字段添加成功")
            
            # 添加 filter_intensity 字段
            if 'filter_intensity' not in existing_columns:
                print("正在添加 filter_intensity 字段...")
                alter_sql_2 = """
                    ALTER TABLE video_edit_tasks 
                    ADD COLUMN filter_intensity FLOAT DEFAULT 1.0 COMMENT '滤镜强度（0.0-1.0）' 
                    AFTER filter_type
                """
                db.execute(alter_sql_2)
                print("✓ filter_intensity 字段添加成功")
            
            db.commit()
            print("\n✓ 迁移完成！")
            return True
            
    except Exception as e:
        print(f"✗ 迁移失败：{str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    print("=" * 60)
    print("数据库迁移：添加滤镜字段")
    print("=" * 60)
    success = migrate_add_filter_fields()
    sys.exit(0 if success else 1)
