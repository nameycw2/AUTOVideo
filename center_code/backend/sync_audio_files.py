"""
同步本地音频文件到数据库
扫描 uploads/materials/audios 目录，将本地存在但数据库没有记录的音频文件重新导入
"""
import os
import sys

# 添加当前目录到 Python 路径
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from db import get_db
from models import Material

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIO_DIR = os.path.join(BASE_DIR, 'uploads', 'materials', 'audios')

def get_audio_duration(file_path):
    """获取音频时长"""
    try:
        import ffmpeg
        probe = ffmpeg.probe(file_path)
        duration = float(probe.get('format', {}).get('duration', 0))
        return duration
    except Exception as e:
        print(f"  ⚠️  无法获取时长: {e}")
        return None

def sync_audio_files():
    """同步音频文件到数据库"""
    print("\n" + "=" * 60)
    print("同步本地音频文件到数据库")
    print("=" * 60)
    
    # 检查目录是否存在
    if not os.path.exists(AUDIO_DIR):
        print(f"\n❌ 音频目录不存在: {AUDIO_DIR}")
        return
    
    # 扫描本地音频文件
    local_files = []
    for filename in os.listdir(AUDIO_DIR):
        if filename.lower().endswith(('.mp3', '.wav', '.flac', '.m4a')):
            file_path = os.path.join(AUDIO_DIR, filename)
            if os.path.isfile(file_path):
                local_files.append({
                    'filename': filename,
                    'path': file_path,
                    'size': os.path.getsize(file_path)
                })
    
    if not local_files:
        print("\n⚠️  本地音频目录为空")
        return
    
    print(f"\n✓ 找到 {len(local_files)} 个本地音频文件")
    
    # 查询数据库中已有的音频记录
    with get_db() as db:
        existing_materials = db.query(Material).filter(Material.type == 'audio').all()
        existing_paths = set()
        for mat in existing_materials:
            # 提取文件名
            if mat.path:
                existing_paths.add(os.path.basename(mat.path))
        
        print(f"✓ 数据库中已有 {len(existing_paths)} 条音频记录")
        
        # 找出需要导入的文件
        to_import = []
        for file_info in local_files:
            if file_info['filename'] not in existing_paths:
                to_import.append(file_info)
        
        if not to_import:
            print("\n✓ 所有本地文件都已在数据库中")
            return
        
        print(f"\n⚠️  发现 {len(to_import)} 个文件需要导入：")
        for i, file_info in enumerate(to_import[:10], 1):
            size_mb = file_info['size'] / 1024 / 1024
            print(f"   {i}. {file_info['filename']} ({size_mb:.2f} MB)")
        
        if len(to_import) > 10:
            print(f"   ... 还有 {len(to_import) - 10} 个文件")
        
        # 询问是否导入
        confirm = input(f"\n是否导入这 {len(to_import)} 个文件到数据库？(yes/no，默认yes): ").strip().lower()
        if confirm not in ['', 'yes', 'y']:
            print("❌ 已取消")
            return
        
        # 导入文件
        imported_count = 0
        failed_count = 0
        
        print("\n开始导入...")
        for file_info in to_import:
            try:
                filename = file_info['filename']
                file_path = file_info['path']
                
                # 构建相对路径
                rel_path = os.path.relpath(file_path, BASE_DIR).replace(os.sep, '/')
                
                # 生成显示名称（去掉扩展名）
                display_name = os.path.splitext(filename)[0]
                
                # 获取音频时长
                duration = get_audio_duration(file_path)
                
                # 创建数据库记录
                material = Material(
                    name=display_name,
                    path=rel_path,
                    type='audio',
                    status='ready',
                    duration=duration,
                    width=None,
                    height=None,
                    size=file_info['size'],
                    original_path=None,
                    meta_json=None
                )
                
                db.add(material)
                db.flush()
                
                imported_count += 1
                print(f"  ✓ 已导入: {filename} (ID: {material.id})")
                
            except Exception as e:
                failed_count += 1
                print(f"  ❌ 导入失败: {filename} - {e}")
        
        # 提交事务
        try:
            db.commit()
            print(f"\n✓ 成功导入 {imported_count} 个文件")
            if failed_count > 0:
                print(f"⚠️  失败 {failed_count} 个文件")
        except Exception as e:
            print(f"\n❌ 提交事务失败: {e}")
            db.rollback()

def main():
    """主函数"""
    try:
        sync_audio_files()
        
        print("\n" + "=" * 60)
        print("✓ 同步完成！")
        print("=" * 60)
        print("\n现在刷新前端页面，应该可以看到所有音频素材了。\n")
        
    except Exception as e:
        print(f"\n❌ 同步过程中出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()
