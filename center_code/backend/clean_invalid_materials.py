"""
清理无效的素材记录（文件不存在的记录）
"""
import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from db import get_db
from models import Material

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def clean_invalid_materials():
    """清理文件不存在的素材记录"""
    print("\n" + "=" * 60)
    print("清理无效的素材记录")
    print("=" * 60)
    
    try:
        with get_db() as db:
            # 查询所有素材
            all_materials = db.query(Material).all()
            
            if not all_materials:
                print("\n⚠️  没有找到任何素材记录")
                return
            
            print(f"\n共找到 {len(all_materials)} 条素材记录")
            
            invalid_materials = []
            
            for mat in all_materials:
                if not mat.path:
                    print(f"  ⚠️  素材 ID={mat.id} 没有路径信息")
                    invalid_materials.append(mat)
                    continue
                
                # 检查文件是否存在
                abs_path = os.path.join(BASE_DIR, mat.path)
                if not os.path.exists(abs_path):
                    invalid_materials.append(mat)
            
            if not invalid_materials:
                print("\n✅ 所有素材文件都存在，无需清理")
                return
            
            print(f"\n⚠️  发现 {len(invalid_materials)} 条无效记录（文件不存在）：")
            print("\n" + "-" * 60)
            for mat in invalid_materials[:20]:  # 只显示前20条
                abs_path = os.path.join(BASE_DIR, mat.path) if mat.path else "无路径"
                print(f"ID: {mat.id:4d} | 类型: {mat.type:5s} | 名称: {mat.name[:30]}")
                print(f"           路径: {mat.path}")
                print(f"           绝对路径: {abs_path}")
                print("-" * 60)
            
            if len(invalid_materials) > 20:
                print(f"... 还有 {len(invalid_materials) - 20} 条")
            
            # 询问是否删除
            confirm = input(f"\n是否删除这 {len(invalid_materials)} 条无效记录？(yes/no，默认no): ").strip().lower()
            
            if confirm in ['yes', 'y']:
                deleted_count = 0
                for mat in invalid_materials:
                    try:
                        db.delete(mat)
                        deleted_count += 1
                    except Exception as e:
                        print(f"  ❌ 删除素材 ID={mat.id} 失败: {e}")
                
                db.commit()
                print(f"\n✅ 成功删除 {deleted_count} 条无效记录")
            else:
                print("\n❌ 已取消删除")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 清理过程出错: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主函数"""
    try:
        clean_invalid_materials()
        
        print("\n" + "=" * 60)
        print("✅ 处理完成！")
        print("=" * 60)
        print("\n建议：")
        print("  1. 刷新前端页面，查看素材列表")
        print("  2. 重新上传需要的视频素材")
        print("  3. 确保素材文件不被手动删除\n")
        
    except Exception as e:
        print(f"\n❌ 执行出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()
