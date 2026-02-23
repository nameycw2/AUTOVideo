"""
为 users 表添加 role、parent_id 字段，并将首个用户设为 super_admin。
在 backend 目录执行: python -m scripts.migrate_user_roles
"""
import os
import sys

_backend = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend not in sys.path:
    sys.path.insert(0, _backend)

from sqlalchemy import text
from db import get_db

def main():
    with get_db() as db:
        # 检查是否已有 role 列
        try:
            db.execute(text("SELECT role FROM users LIMIT 1"))
            print("users.role 已存在，跳过迁移")
        except Exception:
            db.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR(32) NOT NULL DEFAULT 'child'"))
            db.execute(text("CREATE INDEX ix_users_role ON users(role)"))
            db.commit()
            print("已添加 users.role")

        try:
            db.execute(text("SELECT parent_id FROM users LIMIT 1"))
            print("users.parent_id 已存在，跳过迁移")
        except Exception:
            db.execute(text("ALTER TABLE users ADD COLUMN parent_id INTEGER NULL"))
            db.execute(text("CREATE INDEX ix_users_parent_id ON users(parent_id)"))
            db.commit()
            print("已添加 users.parent_id")

        # 若没有任何 super_admin，将 id 最小的用户设为 super_admin
        r = db.execute(text("SELECT id FROM users WHERE role = 'super_admin' LIMIT 1")).fetchone()
        if not r:
            r = db.execute(text("SELECT id FROM users ORDER BY id ASC LIMIT 1")).fetchone()
            if r:
                db.execute(text("UPDATE users SET role = 'super_admin' WHERE id = :id"), {"id": r[0]})
                db.commit()
                print(f"已将用户 id={r[0]} 设为超级管理员")

        # max_children：母账号下属子账号数量上限
        try:
            db.execute(text("SELECT max_children FROM users LIMIT 1"))
            print("users.max_children 已存在，跳过迁移")
        except Exception:
            db.execute(text("ALTER TABLE users ADD COLUMN max_children INTEGER NULL"))
            db.commit()
            print("已添加 users.max_children")
    print("迁移完成")

if __name__ == "__main__":
    main()
