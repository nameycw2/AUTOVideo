"""
为 users 表添加缺失的 role、parent_id、max_children 列（与 models.User 一致）。
运行一次即可：python migrate_add_users_role_columns.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from db import engine
from sqlalchemy import text


def column_exists(conn, table, column):
    """检查 MySQL 表是否已有某列"""
    r = conn.execute(text("""
        SELECT COUNT(*) FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND COLUMN_NAME = :c
    """), {"t": table, "c": column})
    return r.scalar() > 0


def main():
    url = str(engine.url)
    if "mysql" not in url and "pymysql" not in url:
        print("当前未使用 MySQL，跳过迁移。")
        return

    with engine.begin() as conn:
        for col, ddl in [
            ("role", "ADD COLUMN role VARCHAR(32) NOT NULL DEFAULT 'child' COMMENT '角色'"),
            ("parent_id", "ADD COLUMN parent_id INT NULL COMMENT '母账号ID'"),
            ("max_children", "ADD COLUMN max_children INT NULL COMMENT '子账号数量上限'"),
        ]:
            if column_exists(conn, "users", col):
                print(f"users.{col} 已存在，跳过")
                continue
            print(f"正在添加 users.{col} ...")
            conn.execute(text(f"ALTER TABLE users {ddl}"))
        # 索引（若已存在会报错，可忽略）
        for idx, sql in [
            ("ix_users_role", "CREATE INDEX ix_users_role ON users(role)"),
            ("ix_users_parent_id", "CREATE INDEX ix_users_parent_id ON users(parent_id)"),
        ]:
            try:
                conn.execute(text(sql))
                print(f"已创建索引 {idx}")
            except Exception as e:
                if "Duplicate key name" in str(e) or "1061" in str(e):
                    print(f"索引 {idx} 已存在，跳过")
                else:
                    raise
    print("✓ users 表迁移完成。")


if __name__ == "__main__":
    main()
