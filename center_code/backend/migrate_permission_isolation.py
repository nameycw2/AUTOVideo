"""
权限隔离迁移脚本
为 devices、accounts、merchants、publish_plans、materials 表添加 user_id 字段
现有数据全部归属到 super_admin 用户
"""
import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from db import get_db
from models import User, USER_ROLE_SUPER_ADMIN


def get_super_admin_id(db):
    # 优先找 super_admin，找不到就用第一个用户
    admin = db.query(User).filter(User.role == USER_ROLE_SUPER_ADMIN).first()
    if not admin:
        admin = db.query(User).order_by(User.id.asc()).first()
    if not admin:
        raise RuntimeError('数据库中没有任何用户，请先运行 init_user.py')
    # 顺便把这个用户升级为 super_admin
    if admin.role != USER_ROLE_SUPER_ADMIN:
        admin.role = USER_ROLE_SUPER_ADMIN
        db.commit()
        print(f'[升级] 用户 {admin.username} (id={admin.id}) 已设置为 super_admin')
    return admin.id


def column_exists(db, table, column):
    """检查列是否已存在（兼容 MySQL 和 SQLite）"""
    try:
        from sqlalchemy import text
        result = db.execute(text(f'SELECT {column} FROM {table} LIMIT 1'))
        return True
    except Exception:
        return False


def run_migration():
    with get_db() as db:
        admin_id = get_super_admin_id(db)
        print(f'[迁移] super_admin ID = {admin_id}')

        from sqlalchemy import text

        tables = [
            ('devices', 'user_id'),
            ('accounts', 'user_id'),
            ('merchants', 'user_id'),
            ('publish_plans', 'user_id'),
            ('materials', 'user_id'),
        ]

        for table, col in tables:
            if column_exists(db, table, col):
                print(f'[跳过] {table}.{col} 已存在')
                # 将 NULL 值更新为 super_admin
                db.execute(text(
                    f'UPDATE {table} SET {col} = :uid WHERE {col} IS NULL'
                ), {'uid': admin_id})
                db.commit()
                print(f'[更新] {table}.{col} NULL -> {admin_id}')
                continue

            # 添加列
            try:
                db.execute(text(f'ALTER TABLE {table} ADD COLUMN {col} INTEGER'))
                db.commit()
                print(f'[添加] {table}.{col}')
            except Exception as e:
                print(f'[警告] 添加 {table}.{col} 失败: {e}')
                db.rollback()
                continue

            # 将现有数据归属到 super_admin
            db.execute(text(
                f'UPDATE {table} SET {col} = :uid WHERE {col} IS NULL'
            ), {'uid': admin_id})
            db.commit()
            print(f'[归属] {table} 现有数据 -> user_id={admin_id}')

        # MySQL 需要添加外键索引（SQLite 不支持 ALTER TABLE ADD FOREIGN KEY）
        # 如果使用 MySQL，可以手动执行以下 SQL：
        # ALTER TABLE devices ADD INDEX idx_devices_user_id (user_id);
        # ALTER TABLE accounts ADD INDEX idx_accounts_user_id (user_id);
        # ALTER TABLE merchants ADD INDEX idx_merchants_user_id (user_id);
        # ALTER TABLE publish_plans ADD INDEX idx_publish_plans_user_id (user_id);
        # ALTER TABLE materials ADD INDEX idx_materials_user_id (user_id);

        print('\n[完成] 权限隔离迁移完成')
        print(f'  - 所有现有数据已归属到 super_admin (user_id={admin_id})')
        print('  - 新创建的数据将自动归属到创建者')


if __name__ == '__main__':
    run_migration()
