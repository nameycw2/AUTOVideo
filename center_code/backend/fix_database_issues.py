"""
修复数据库问题的脚本：
1. 添加 video_library.user_id 字段
2. 清理无效的音频素材记录
"""
import os
import sys

# 添加当前目录到 Python 路径
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from sqlalchemy import text, inspect
from db import engine, get_db
from models import Material, VideoLibrary

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def check_column_exists(table_name, column_name):
    """检查列是否存在"""
    try:
        inspector = inspect(engine)
        columns = [col['name'] for col in inspector.get_columns(table_name)]
        return column_name in columns
    except Exception as e:
        print(f"检查列时出错: {e}")
        return False

def fix_video_library_user_id():
    """修复 video_library 表的 user_id 字段"""
    print("\n" + "=" * 60)
    print("1. 检查并修复 video_library 表的 user_id 字段")
    print("=" * 60)
    
    try:
        # 检查表是否存在
        inspector = inspect(engine)
        if 'video_library' not in inspector.get_table_names():
            print("⚠️  video_library 表不存在，跳过")
            return True
        
        # 检查user_id列是否已存在
        if check_column_exists('video_library', 'user_id'):
            print("✓ user_id 列已存在")
            return True
        
        print("\n正在添加 user_id 列...")
        
        with get_db() as db:
            # 检查是否有现有数据
            result = db.execute(text("SELECT COUNT(*) as count FROM video_library"))
            count = result.fetchone()[0]
            
            if count > 0:
                print(f"⚠️  发现 {count} 条现有数据，将全部删除（无法确定归属用户）")
                db.execute(text("DELETE FROM video_library"))
                db.commit()
                print("✓ 已清理现有数据")
            
            # 添加user_id列
            db.execute(text("""
                ALTER TABLE video_library 
                ADD COLUMN user_id INT NOT NULL DEFAULT 1
            """))
            
            # 添加外键约束
            try:
                db.execute(text("""
                    ALTER TABLE video_library 
                    ADD CONSTRAINT fk_video_library_user_id 
                    FOREIGN KEY (user_id) REFERENCES users(id)
                """))
            except Exception as e:
                print(f"⚠️  添加外键约束失败（可能已存在）: {e}")
            
            # 添加索引
            try:
                db.execute(text("""
                    CREATE INDEX idx_video_library_user_id 
                    ON video_library(user_id)
                """))
            except Exception as e:
                print(f"⚠️  添加索引失败（可能已存在）: {e}")
            
            db.commit()
        
        print("✓ video_library 表修复完成")
        return True
        
    except Exception as e:
        print(f"❌ 修复 video_library 表时出错: {e}")
        import traceback
        traceback.print_exc()
        return False

def clean_invalid_audio_materials():
    """清理无效的音频素材记录（文件不存在的记录）"""
    print("\n" + "=" * 60)
    print("2. 清理无效的音频素材记录")
    print("=" * 60)
    
    try:
        with get_db() as db:
            # 查询所有音频素材
            audio_materials = db.query(Material).filter(Material.type == 'audio').all()
            
            if not audio_materials:
                print("⚠️  没有找到音频素材记录")
                return True
            
            print(f"\n共找到 {len(audio_materials)} 条音频素材记录")
            
            invalid_count = 0
            invalid_list = []
            
            for mat in audio_materials:
                # 检查文件是否存在
                abs_path = os.path.join(BASE_DIR, mat.path)
                if not os.path.exists(abs_path):
                    invalid_count += 1
                    invalid_list.append({
                        'id': mat.id,
                        'name': mat.name,
                        'path': mat.path
                    })
            
            if invalid_count == 0:
                print("✓ 所有音频素材文件都存在")
                return True
            
            print(f"\n⚠️  发现 {invalid_count} 条无效记录（文件不存在）：")
            for item in invalid_list[:10]:  # 只显示前10条
                print(f"   - ID: {item['id']}, 名称: {item['name']}")
            
            if invalid_count > 10:
                print(f"   ... 还有 {invalid_count - 10} 条")
            
            # 询问是否删除
            confirm = input(f"\n是否删除这 {invalid_count} 条无效记录？(yes/no，默认yes): ").strip().lower()
            if confirm in ['', 'yes', 'y']:
                for item in invalid_list:
                    db.query(Material).filter(Material.id == item['id']).delete()
                db.commit()
                print(f"✓ 已删除 {invalid_count} 条无效记录")
            else:
                print("⚠️  跳过删除")
        
        return True
        
    except Exception as e:
        print(f"❌ 清理无效音频素材时出错: {e}")
        import traceback
        traceback.print_exc()
        return False

def fix_video_edit_tasks_user_id():
    """修复 video_edit_tasks 表的 user_id 字段"""
    print("\n" + "=" * 60)
    print("3. 检查并修复 video_edit_tasks 表的 user_id 字段")
    print("=" * 60)
    
    try:
        # 检查表是否存在
        inspector = inspect(engine)
        if 'video_edit_tasks' not in inspector.get_table_names():
            print("⚠️  video_edit_tasks 表不存在，跳过")
            return True
        
        # 检查user_id列是否已存在
        if check_column_exists('video_edit_tasks', 'user_id'):
            print("✓ user_id 列已存在")
            return True
        
        print("\n正在添加 user_id 列...")
        
        with get_db() as db:
            # 检查是否有现有数据
            result = db.execute(text("SELECT COUNT(*) as count FROM video_edit_tasks"))
            count = result.fetchone()[0]
            
            if count > 0:
                print(f"⚠️  发现 {count} 条现有数据，将全部删除")
                db.execute(text("DELETE FROM video_edit_tasks"))
                db.commit()
                print("✓ 已清理现有数据")
            
            # 添加user_id列
            db.execute(text("""
                ALTER TABLE video_edit_tasks 
                ADD COLUMN user_id INT NOT NULL DEFAULT 1
            """))
            
            # 添加外键约束
            try:
                db.execute(text("""
                    ALTER TABLE video_edit_tasks 
                    ADD CONSTRAINT fk_video_edit_tasks_user_id 
                    FOREIGN KEY (user_id) REFERENCES users(id)
                """))
            except Exception as e:
                print(f"⚠️  添加外键约束失败（可能已存在）: {e}")
            
            # 添加索引
            try:
                db.execute(text("""
                    CREATE INDEX idx_video_edit_tasks_user_id 
                    ON video_edit_tasks(user_id)
                """))
            except Exception as e:
                print(f"⚠️  添加索引失败（可能已存在）: {e}")
            
            db.commit()
        
        print("✓ video_edit_tasks 表修复完成")
        return True
        
    except Exception as e:
        print(f"❌ 修复 video_edit_tasks 表时出错: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("数据库问题修复脚本")
    print("=" * 60)
    print("\n此脚本将：")
    print("  1. 为 video_library 表添加 user_id 字段（如果缺失）")
    print("  2. 清理无效的音频素材记录（文件不存在的记录）")
    print("  3. 为 video_edit_tasks 表添加 user_id 字段（如果缺失）")
    print("\n⚠️  注意：运行前请确保已停止后端服务！")
    
    confirm = input("\n是否继续？(yes/no，默认yes): ").strip().lower()
    if confirm not in ['', 'yes', 'y']:
        print("❌ 已取消")
        return
    
    # 测试数据库连接
    try:
        with get_db() as db:
            db.execute(text('SELECT 1'))
        print("\n✓ 数据库连接成功")
    except Exception as e:
        print(f"\n❌ 数据库连接失败: {e}")
        sys.exit(1)
    
    # 执行修复
    success = True
    success = fix_video_library_user_id() and success
    success = clean_invalid_audio_materials() and success
    success = fix_video_edit_tasks_user_id() and success
    
    if success:
        print("\n" + "=" * 60)
        print("✓ 修复完成！")
        print("=" * 60)
        print("\n现在可以重启后端服务了。\n")
    else:
        print("\n" + "=" * 60)
        print("❌ 修复过程中出现错误，请检查上面的错误信息")
        print("=" * 60 + "\n")
        sys.exit(1)

if __name__ == '__main__':
    main()
