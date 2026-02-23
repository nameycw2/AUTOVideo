"""
用户管理 API：超级管理员可管理母账号与子账号，母账号仅可管理下属子账号。
"""
from flask import Blueprint, request
from datetime import datetime

from utils import response_success, response_error, login_required, get_current_user_id, get_current_user_obj
from models import User, USER_ROLE_SUPER_ADMIN, USER_ROLE_PARENT, USER_ROLE_CHILD
from db import get_db

users_bp = Blueprint('users', __name__, url_prefix='/api/users')


def _user_to_dict(u, include_parent_username=False, parent_username=None, child_count=None, max_children=None):
    d = {
        'id': u.id,
        'username': u.username,
        'email': u.email,
        'role': getattr(u, 'role', None) or USER_ROLE_CHILD,
        'parent_id': getattr(u, 'parent_id', None),
        'is_verified': getattr(u, 'is_verified', False),
        'created_at': u.created_at.isoformat() if u.created_at else None,
        'updated_at': u.updated_at.isoformat() if u.updated_at else None,
    }
    if include_parent_username and parent_username is not None:
        d['parent_username'] = parent_username
    if getattr(u, 'role', None) == USER_ROLE_PARENT:
        d['max_children'] = getattr(u, 'max_children', None) if max_children is None else max_children
        if child_count is not None:
            d['child_count'] = child_count
    return d


def _can_manage_user(current_user, target_user):
    """当前用户是否有权查看/管理目标用户"""
    role = getattr(current_user, 'role', None) or USER_ROLE_CHILD
    tid = target_user.id
    tr = getattr(target_user, 'role', None) or USER_ROLE_CHILD
    tparent = getattr(target_user, 'parent_id', None)
    my_id = current_user.id

    if role == USER_ROLE_SUPER_ADMIN:
        return True
    if role == USER_ROLE_PARENT:
        return tr == USER_ROLE_CHILD and tparent == my_id
    return tid == my_id


def _can_create_role(current_user, new_role, parent_id):
    """当前用户是否有权创建指定角色的用户"""
    role = getattr(current_user, 'role', None) or USER_ROLE_CHILD
    if role == USER_ROLE_SUPER_ADMIN:
        if new_role == USER_ROLE_CHILD and parent_id is None:
            return False
        if new_role == USER_ROLE_PARENT:
            return parent_id is None
        if new_role == USER_ROLE_CHILD:
            return True
        return False
    if role == USER_ROLE_PARENT:
        return new_role == USER_ROLE_CHILD and parent_id == current_user.id
    return False


@users_bp.route('', methods=['GET'])
@login_required
def list_users():
    """
    列出当前用户有权查看的用户。
    超级管理员：所有用户（母账号 + 子账号，可带 parent 信息）
    母账号：仅下属子账号
    子账号：仅自己
    """
    current = get_current_user_obj()
    if not current:
        return response_error('请先登录', 401)

    role = getattr(current, 'role', None) or USER_ROLE_CHILD
    my_id = current.id

    with get_db() as db:
        if role == USER_ROLE_SUPER_ADMIN:
            q = db.query(User).order_by(User.id.asc())
            users = q.all()
            parent_map = {}
            child_count_map = {}
            for u in users:
                pid = getattr(u, 'parent_id', None)
                if pid:
                    p = db.query(User).filter(User.id == pid).first()
                    parent_map[u.id] = p.username if p else None
                    child_count_map[pid] = child_count_map.get(pid, 0) + 1
            items = []
            for u in users:
                child_count = child_count_map.get(u.id) if getattr(u, 'role', None) == USER_ROLE_PARENT else None
                items.append(_user_to_dict(u, include_parent_username=bool(getattr(u, 'parent_id', None)), parent_username=parent_map.get(u.id), child_count=child_count))
        elif role == USER_ROLE_PARENT:
            users = db.query(User).filter(User.parent_id == my_id, User.role == USER_ROLE_CHILD).order_by(User.id.asc()).all()
            items = [_user_to_dict(u) for u in users]
        else:
            items = [_user_to_dict(current)]

    return response_success({
        'list': items,
        'my_role': role
    })


@users_bp.route('/parents', methods=['GET'])
@login_required
def list_parents():
    """仅超级管理员可调用：列出所有母账号，用于创建子账号时选择归属母账号。"""
    current = get_current_user_obj()
    if not current:
        return response_error('请先登录', 401)
    role = getattr(current, 'role', None) or USER_ROLE_CHILD
    if role != USER_ROLE_SUPER_ADMIN:
        return response_error('无权限', 403)

    with get_db() as db:
        parents = db.query(User).filter(User.role == USER_ROLE_PARENT).order_by(User.id.asc()).all()
        child_counts = {}
        for u in parents:
            child_counts[u.id] = db.query(User).filter(User.parent_id == u.id).count()
    return response_success({
        'list': [{
            'id': u.id,
            'username': u.username,
            'email': u.email,
            'max_children': getattr(u, 'max_children', None),
            'child_count': child_counts.get(u.id, 0)
        } for u in parents]
    })


@users_bp.route('', methods=['POST'])
@login_required
def create_user():
    """
    创建用户。
    超级管理员：可创建母账号(role=parent)或子账号(role=child, parent_id 必填)。
    母账号：可创建子账号(role=child, parent_id=当前用户)。
    """
    current = get_current_user_obj()
    if not current:
        return response_error('请先登录', 401)

    data = request.json or {}
    username = (data.get('username') or '').strip()
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''
    role = (data.get('role') or USER_ROLE_CHILD).strip()
    parent_id = data.get('parent_id')
    max_children = data.get('max_children')

    if role not in (USER_ROLE_PARENT, USER_ROLE_CHILD):
        return response_error('无效角色（仅可创建母账号或子账号）', 400)
    if role == USER_ROLE_CHILD and parent_id is None:
        my_role = getattr(current, 'role', None) or USER_ROLE_CHILD
        if my_role == USER_ROLE_PARENT:
            parent_id = current.id
        else:
            return response_error('子账号必须指定母账号', 400)
    if role == USER_ROLE_PARENT and parent_id is not None:
        return response_error('母账号不能有 parent_id', 400)

    if not _can_create_role(current, role, parent_id):
        return response_error('无权限创建该角色用户', 403)

    if not username or len(username) < 2:
        return response_error('用户名至少 2 个字符', 400)
    if not email or '@' not in email:
        return response_error('邮箱格式无效', 400)
    if not password or len(password) < 8:
        return response_error('密码至少 8 位', 400)

    with get_db() as db:
        if db.query(User).filter(User.username == username).first():
            return response_error('用户名已存在', 400)
        if db.query(User).filter(User.email == email).first():
            return response_error('邮箱已存在', 400)
        if role == USER_ROLE_CHILD and parent_id is not None:
            parent = db.query(User).filter(User.id == parent_id, User.role == USER_ROLE_PARENT).first()
            if not parent:
                return response_error('指定的母账号不存在', 400)
            current_children = db.query(User).filter(User.parent_id == parent_id).count()
            parent_max = getattr(parent, 'max_children', None)
            if parent_max is not None and current_children >= parent_max:
                return response_error(f'该母账号下属子账号已达上限（{parent_max} 个）', 400)

        user = User(
            username=username,
            email=email,
            role=role,
            parent_id=parent_id if role == USER_ROLE_CHILD else None,
            max_children=max_children if role == USER_ROLE_PARENT and max_children is not None else None,
            is_verified=False
        )
        user.set_password(password)
        db.add(user)
        db.commit()
        created_id = user.id
    with get_db() as db2:
        user = db2.query(User).filter(User.id == created_id).first()
        out = _user_to_dict(user) if user else {'id': created_id, 'username': username, 'email': email, 'role': role, 'parent_id': parent_id}
    return response_success(out, '创建成功', 201)


@users_bp.route('/<int:uid>', methods=['GET'])
@login_required
def get_user(uid):
    """获取单个用户信息（需有权限）。"""
    current = get_current_user_obj()
    if not current:
        return response_error('请先登录', 401)

    with get_db() as db:
        target = db.query(User).filter(User.id == uid).first()
        if not target:
            return response_error('用户不存在', 404)
        if not _can_manage_user(current, target):
            return response_error('无权限查看', 403)

        parent_username = None
        if getattr(target, 'parent_id', None):
            p = db.query(User).filter(User.id == target.parent_id).first()
            parent_username = p.username if p else None
        child_count = None
        if getattr(target, 'role', None) == USER_ROLE_PARENT:
            child_count = db.query(User).filter(User.parent_id == uid).count()

    return response_success(_user_to_dict(target, include_parent_username=True, parent_username=parent_username, child_count=child_count))


@users_bp.route('/<int:uid>', methods=['PUT'])
@login_required
def update_user(uid):
    """更新用户（仅可改密码/邮箱等，不可改 role/parent_id 以免越权）。"""
    current = get_current_user_obj()
    if not current:
        return response_error('请先登录', 401)

    with get_db() as db:
        target = db.query(User).filter(User.id == uid).first()
        if not target:
            return response_error('用户不存在', 404)
        if not _can_manage_user(current, target):
            return response_error('无权限修改', 403)

        data = request.json or {}
        # 仅允许更新部分字段
        if 'password' in data and data['password']:
            if len(data['password']) < 8:
                return response_error('密码至少 8 位', 400)
            target.set_password(data['password'])
        if 'email' in data:
            email = (data['email'] or '').strip().lower()
            if email and '@' in email:
                existing = db.query(User).filter(User.email == email, User.id != uid).first()
                if existing:
                    return response_error('邮箱已被使用', 400)
                target.email = email
        # 超级管理员可设置母账号的子账号数量上限
        my_role = getattr(current, 'role', None) or USER_ROLE_CHILD
        if my_role == USER_ROLE_SUPER_ADMIN and getattr(target, 'role', None) == USER_ROLE_PARENT and 'max_children' in data:
            v = data['max_children']
            if v is not None and v != '':
                try:
                    n = int(v)
                    if n < 0:
                        return response_error('子账号上限不能为负数', 400)
                    current_children = db.query(User).filter(User.parent_id == uid).count()
                    if n < current_children:
                        return response_error(f'不能小于当前已有子账号数（{current_children}）', 400)
                    target.max_children = n
                except (TypeError, ValueError):
                    return response_error('子账号上限须为整数', 400)
            else:
                target.max_children = None  # 不限制

        db.commit()

    return response_success(_user_to_dict(target), '更新成功')
