"""
重置默认用户 hbut 的密码为 dydy?123（与 init_user.py 一致）。
若库里没有 hbut 会先创建。
在 backend 目录执行: python reset_hbut_password.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from db import get_db
from models import User

def main():
    with get_db() as db:
        user = db.query(User).filter(User.username == 'hbut').first()
        if not user:
            user = User(
                username='hbut',
                email='admin@example.com',
                is_verified=True
            )
            user.set_password('dydy?123')
            db.add(user)
            db.commit()
            print("已创建用户 hbut，密码: dydy?123")
        else:
            user.set_password('dydy?123')
            db.commit()
            print("已重置 hbut 的密码为: dydy?123")
    print("请使用 用户名 hbut / 密码 dydy?123 登录。")

if __name__ == "__main__":
    main()
