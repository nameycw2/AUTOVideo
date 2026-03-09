"""
抖音中心管理平台 - Flask应用主文件
模块化设计，支持 MySQL 数据库
"""

import os
import sys

# 添加当前目录到 Python 路径，确保可以导入模块
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# 前端静态目录：优先 backend/static（Vite 构建输出），否则 frontend/dist
def _frontend_dist_dir():
    static_dir = os.path.join(current_dir, 'static')
    if os.path.isfile(os.path.join(static_dir, 'index.html')):
        return static_dir
    fallback = os.path.join(os.path.dirname(current_dir), 'frontend', 'dist')
    return fallback if os.path.isdir(fallback) else static_dir

from flask import Flask, send_from_directory, request, jsonify
from flask_cors import CORS

from models import Base
from db import engine

# 导入所有 API 模块（按功能划分）
from api.auth import auth_bp
from api.users import users_bp
from api.devices import devices_bp
from api.accounts import accounts_bp
from api.video import video_bp
from api.chat import chat_bp
from api.listen import listen_bp
from api.social import social_bp
from api.messages import messages_bp
from api.stats import stats_bp
from api.login import login_bp
from api.publish_plans import publish_plans_bp
from api.merchants import merchants_bp
from api.video_library import video_library_bp
from api.data_center import data_center_bp
from api.video_editor import video_editor_bp
from api.publish import publish_bp
from api.material import material_bp
from api.ai import ai_bp
from api.money_printer import money_printer_bp
from api.editor import editor_bp

# 导入任务处理器
from services.task_processor import get_task_processor
from workers.auto_transcode_worker import maybe_start_transcode_worker

app = Flask(__name__, static_folder=_frontend_dist_dir(), static_url_path='')

# Ensure money_printer routes are always available.
if 'money_printer' not in app.blueprints:
    app.register_blueprint(money_printer_bp)

# ==================== Session 安全配置 ====================
# 警告：生产环境必须设置强随机 SECRET_KEY！
# 生成方式：python -c "import secrets; print(secrets.token_hex(32))"
# 所有密钥必须通过环境变量配置，避免硬编码到代码中
secret_key = os.getenv('SECRET_KEY', '')

if not secret_key:
    import warnings
    import secrets
    # 开发环境：自动生成一个临时密钥（每次启动都会变化）
    # 生产环境：必须通过环境变量设置固定的 SECRET_KEY
    is_production = os.getenv('FLASK_ENV') == 'production' or os.getenv('ENVIRONMENT') == 'production'
    
    if is_production:
        raise ValueError(
            '❌ 错误：生产环境必须设置 SECRET_KEY 环境变量！\n'
            '请在 .env 文件或系统环境变量中设置 SECRET_KEY。\n'
            '生成方式：python -c "import secrets; print(secrets.token_hex(32))"'
        )
    else:
        # 开发环境：生成临时密钥并给出警告
        secret_key = secrets.token_hex(32)
        warnings.warn(
            '⚠️  警告：未设置 SECRET_KEY 环境变量，已自动生成临时密钥（仅用于开发环境）\n'
            '生产环境必须设置固定的 SECRET_KEY 环境变量！\n'
            '生成方式：python -c "import secrets; print(secrets.token_hex(32))"\n'
            '然后在 .env 文件中设置：SECRET_KEY=生成的密钥',
            UserWarning
        )
        print(f'ℹ️  开发环境临时 SECRET_KEY 已生成（本次运行有效）')

app.secret_key = secret_key

# 配置 session 安全选项
app.config['SESSION_COOKIE_NAME'] = 'session'
app.config['SESSION_COOKIE_HTTPONLY'] = True  # 防止 XSS 攻击，禁止 JavaScript 访问 cookie
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # 防止 CSRF 攻击，允许跨站请求携带 cookie
app.config['PERMANENT_SESSION_LIFETIME'] = 86400  # 24小时（秒）

# 生产环境建议启用以下配置（需要 HTTPS）：
# app.config['SESSION_COOKIE_SECURE'] = True  # 仅在 HTTPS 连接时发送 cookie
# 注意：开发环境（HTTP）不要启用 SESSION_COOKIE_SECURE，否则 cookie 无法工作

# 检查是否为生产环境（通过环境变量判断）
is_production = os.getenv('FLASK_ENV') == 'production' or os.getenv('ENVIRONMENT') == 'production'

# 检查是否使用 HTTPS
# 优先使用环境变量，如果没有设置，默认使用 HTTP（适用于通过 Nginx 反向代理的 HTTP）
use_https = os.getenv('USE_HTTPS', '').lower() == 'true'

if is_production:
    # 只有在明确使用 HTTPS 时才启用 SESSION_COOKIE_SECURE
    # 如果使用 HTTP 或通过 Nginx 反向代理（未配置 SSL），不要启用
    if use_https:
        app.config['SESSION_COOKIE_SECURE'] = True
        # 生产环境建议使用更严格的 SameSite 策略
        # app.config['SESSION_COOKIE_SAMESITE'] = 'Strict'  # 更严格，但可能影响跨站请求
    else:
        # HTTP 环境不启用 Secure，否则 Cookie 无法工作
        app.config['SESSION_COOKIE_SECURE'] = False
        # 保持 SameSite=Lax 以允许正常的跨站导航
        app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# 配置 CORS，允许携带凭证
# 开发环境允许所有 localhost 和 127.0.0.1 的端口（包括常见的开发端口）
cors_origins = [
    'http://localhost:3000', 'http://localhost:3001', 'http://localhost:3002', 'http://localhost:3003', 
    'http://localhost:5173', 'http://localhost:8080', 'http://localhost:8081', 'http://localhost:8082',
    'http://127.0.0.1:3000', 'http://127.0.0.1:3001', 'http://127.0.0.1:3002', 'http://127.0.0.1:3003',
    'http://127.0.0.1:5173', 'http://127.0.0.1:8080', 'http://127.0.0.1:8081', 'http://127.0.0.1:8082'
]
# 如果环境变量设置了允许的源，则使用环境变量
if os.getenv('CORS_ORIGINS'):
    cors_origins = [origin.strip() for origin in os.getenv('CORS_ORIGINS').split(',') if origin.strip()]
# 开发环境：如果没有设置 CORS_ORIGINS，允许所有 localhost 和 127.0.0.1 的端口
elif not is_production:
    # 开发环境允许所有 localhost 端口（使用通配符更灵活）
    cors_origins = ['*']  # 开发环境允许所有来源
# 生产环境：如果没有设置 CORS_ORIGINS，允许所有来源（通过 Nginx 代理时）
else:
    cors_origins = ['*']  # 生产环境通过 Nginx 代理，允许所有来源

CORS(app, 
     supports_credentials=True,
     origins=cors_origins,
     allow_headers=['Content-Type', 'Authorization', 'X-Requested-With'],
     methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS', 'PATCH'],
     expose_headers=['Content-Type', 'Authorization'],
     max_age=3600)

# 添加全局 CORS 错误处理，确保所有响应都包含 CORS 头（包括错误响应）
@app.after_request
def after_request(response):
    """确保所有响应都包含 CORS 头，包括错误响应"""
    origin = request.headers.get('Origin')
    
    # 如果请求包含 Origin 头，添加 CORS 响应头
    if origin:
        # 开发环境：优先允许所有 localhost 和 127.0.0.1
        if not is_production and ('localhost' in origin or '127.0.0.1' in origin):
            response.headers['Access-Control-Allow-Origin'] = origin
        # 检查是否在允许的源列表中，或者允许所有源
        elif cors_origins == ['*'] or origin in cors_origins:
            response.headers['Access-Control-Allow-Origin'] = origin
        
        # 只有在设置了 Access-Control-Allow-Origin 时才设置其他 CORS 头
        if 'Access-Control-Allow-Origin' in response.headers:
            response.headers['Access-Control-Allow-Credentials'] = 'true'
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS, PATCH'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With'
            response.headers['Access-Control-Expose-Headers'] = 'Content-Type, Authorization'
            response.headers['Access-Control-Max-Age'] = '3600'
    
    return response

# 处理 OPTIONS 预检请求
@app.before_request
def handle_preflight():
    """处理 CORS 预检请求"""
    if request.method == "OPTIONS":
        response = jsonify({})
        origin = request.headers.get('Origin')
        if origin:
            # 开发环境：允许所有 localhost 和 127.0.0.1
            if not is_production and ('localhost' in origin or '127.0.0.1' in origin):
                response.headers['Access-Control-Allow-Origin'] = origin
            elif cors_origins == ['*'] or origin in cors_origins:
                response.headers['Access-Control-Allow-Origin'] = origin
            
            if 'Access-Control-Allow-Origin' in response.headers:
                response.headers['Access-Control-Allow-Credentials'] = 'true'
                response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS, PATCH'
                response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With'
                response.headers['Access-Control-Max-Age'] = '3600'
        return response

# 全局错误处理，确保错误响应也包含 CORS 头
@app.errorhandler(Exception)
def handle_exception(e):
    """处理所有异常，确保错误响应包含 CORS 头"""
    from flask import make_response, request as flask_request
    import traceback

    # 非 API 路径的 404 直接返回 index.html，交给前端路由处理
    is_404 = hasattr(e, 'code') and e.code == 404
    is_api = flask_request.path.startswith('/api/') or flask_request.path.startswith('/uploads/')
    if is_404 and not is_api:
        return send_from_directory(_frontend_dist_dir(), 'index.html')

    # 记录错误
    error_type = type(e).__name__
    error_msg = str(e)
    print(f"\n{'='*60}")
    print(f"❌ 错误类型: {error_type}")
    print(f"❌ 错误信息: {error_msg}")
    print(f"{'='*60}")
    traceback.print_exc()
    print(f"{'='*60}\n")

    # 确定 HTTP 状态码
    if hasattr(e, 'code'):
        status_code = e.code
    elif '404' in error_msg or 'Not Found' in error_msg:
        status_code = 404
    elif '401' in error_msg or 'Unauthorized' in error_msg:
        status_code = 401
    elif '403' in error_msg or 'Forbidden' in error_msg:
        status_code = 403
    else:
        status_code = 500
    
    # 创建错误响应
    response = make_response(jsonify({
        'code': status_code,
        'message': error_msg if status_code != 500 else '服务器内部错误',
        'data': None
    }), status_code)
    
    # 添加 CORS 头
    origin = request.headers.get('Origin')
    if origin:
        # 开发环境：优先允许所有 localhost 和 127.0.0.1
        if not is_production and ('localhost' in origin or '127.0.0.1' in origin):
            response.headers['Access-Control-Allow-Origin'] = origin
        elif cors_origins == ['*'] or origin in cors_origins:
            response.headers['Access-Control-Allow-Origin'] = origin
        
        if 'Access-Control-Allow-Origin' in response.headers:
            response.headers['Access-Control-Allow-Credentials'] = 'true'
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS, PATCH'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With'
            response.headers['Access-Control-Expose-Headers'] = 'Content-Type, Authorization'
    
    return response

# 注册所有 Blueprint
# 定义模块分类和中文名称
blueprint_modules = {
    '认证授权模块': [
        ('auth', auth_bp),
        ('users', users_bp),
        ('login', login_bp),
    ],
    '设备管理模块': [
        ('devices', devices_bp),
    ],
    '账号管理模块': [
        ('accounts', accounts_bp),
    ],
    '视频处理模块': [
        ('video', video_bp),
        ('video_library', video_library_bp),
        ('video_editor', video_editor_bp),
        ('editor', editor_bp),
    ],
    'AI功能模块': [
        ('ai', ai_bp),
    ],
    '聊天监听模块': [
        ('chat', chat_bp),
        ('listen', listen_bp),
    ],
    '社交平台模块': [
        ('social', social_bp),
        ('publish', publish_bp),
        ('publish_plans', publish_plans_bp),
    ],
    '消息管理模块': [
        ('messages', messages_bp),
    ],
    '数据统计模块': [
        ('stats', stats_bp),
        ('data_center', data_center_bp),
    ],
    '商家管理模块': [
        ('merchants', merchants_bp),
    ],
    '素材管理模块': [
        ('material', material_bp),
    ],
}

# 注册所有 Blueprint 并记录状态
registered_modules = {}
for category, modules in blueprint_modules.items():
    registered_modules[category] = []
    for module_name, blueprint in modules:
        try:
            app.register_blueprint(blueprint)
            registered_modules[category].append((module_name, True, None))
        except Exception as e:
            registered_modules[category].append((module_name, False, str(e)))


try:
    app.register_blueprint(money_printer_bp)
except Exception:
    # Keep boot resilient; duplicate registration would raise.
    pass


def init_db():
    """初始化数据库表"""
    try:
        # 测试数据库连接
        from db import get_db
        from sqlalchemy import text
        with get_db() as db:
            db.execute(text('SELECT 1'))
        print("✓ 数据库连接成功")
        
        # 创建表
        Base.metadata.create_all(engine)
        print("✓ 数据库表初始化成功")
        
        # 修改用户名和邮箱列的排序规则为utf8mb4_bin，实现大小写敏感
        with get_db() as db:
            try:
                db.execute(text("ALTER TABLE users MODIFY COLUMN username VARCHAR(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;"))
                db.execute(text("ALTER TABLE users MODIFY COLUMN email VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;"))
                print("✓ 用户名和邮箱列已设置为大小写敏感")
            except Exception as e:
                # 如果表不存在或列不存在，忽略错误
                print(f"⚠️ 设置大小写敏感时出现警告: {e}")
            try:
                db.execute(text("ALTER TABLE video_tasks ADD COLUMN after_publish_actions TEXT NULL;"))
            except Exception:
                pass
            try:
                db.execute(text("ALTER TABLE video_tasks ADD COLUMN after_publish_comment VARCHAR(500) NULL;"))
            except Exception:
                pass
            try:
                db.execute(text("ALTER TABLE video_tasks ADD COLUMN after_publish_result TEXT NULL;"))
            except Exception:
                pass
            try:
                db.execute(text("ALTER TABLE video_tasks ADD COLUMN plan_video_id INT NULL;"))
            except Exception:
                pass
    except Exception as e:
        error_msg = str(e)
        if "Access denied" in error_msg or "1045" in error_msg:
            print("\n" + "="*60)
            print("❌ 数据库连接失败：用户名或密码错误")
            print("="*60)
            print("\n请配置 MySQL 数据库连接信息：")
            print("\n方法1：设置环境变量")
            print("  export DB_HOST=localhost")
            print("  export DB_PORT=3306")
            print("  export DB_NAME=autovideo")
            print("  export DB_USER=root")
            print("  export DB_PASSWORD=your_password")
            print("\n方法2：直接修改 backend/config.py 文件")
            print("  修改 MYSQL_CONFIG 字典中的配置项")
            print("\n方法3：创建数据库（如果还没有）")
            print("  mysql -u root -p")
            print("  CREATE DATABASE autovideo CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
            print("="*60 + "\n")
        elif "Unknown database" in error_msg or "1049" in error_msg:
            print("\n" + "="*60)
            print("❌ 数据库不存在")
            print("="*60)
            print("\n请先创建数据库：")
            print("  mysql -u root -p")
            print("  CREATE DATABASE autovideo CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
            print("="*60 + "\n")
        else:
            print(f"\n❌ 数据库连接失败: {error_msg}\n")
        raise


# ==================== 前端页面路由 ====================

@app.route('/')
def index():
    """提供前端页面"""
    return send_from_directory(_frontend_dist_dir(), 'index.html')


@app.route('/login-helper')
def login_helper():
    """提供登录助手页面"""
    return send_from_directory(_frontend_dist_dir(), 'index.html')


# 提供上传文件的静态路由（必须在 SPA 回退之前，否则 /uploads/* 会被拦截）
@app.route('/uploads/<path:filename>', methods=['GET', 'OPTIONS'])
def uploaded_file(filename):
    """提供上传的文件访问"""
    from flask import Response, request, send_file
    import mimetypes
    
    try:
        # 处理 OPTIONS 请求（CORS 预检）
        if request.method == 'OPTIONS':
            response = Response()
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
            return response
        
        upload_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'uploads')
        
        # 处理路径：URL中使用正斜杠，Windows需要转换为系统路径
        # filename 可能是 "materials/videos/xxx.mp4"
        # 需要转换为系统路径格式
        filename_normalized = filename.replace('/', os.sep).replace('\\', os.sep)
        file_path = os.path.join(upload_dir, filename_normalized)
        
        # 规范化路径（处理 .. 等）
        file_path = os.path.normpath(file_path)
        upload_dir = os.path.normpath(upload_dir)
        
        # 调试信息
        print(f"请求文件: {filename}")
        print(f"规范化文件名: {filename_normalized}")
        print(f"上传目录: {upload_dir}")
        print(f"文件路径: {file_path}")
        print(f"文件是否存在: {os.path.exists(file_path)}")
        
        # 安全检查：确保文件在 uploads 目录内
        upload_dir_abs = os.path.abspath(upload_dir)
        file_path_abs = os.path.abspath(file_path)
        if not file_path_abs.startswith(upload_dir_abs):
            print(f"路径安全检查失败: {file_path_abs} 不在 {upload_dir_abs} 内")
            return jsonify({'error': 'Invalid file path'}), 403
        
        if not os.path.exists(file_path):
            print(f"文件不存在: {file_path}")
            return jsonify({'error': 'File not found'}), 404
        
        if not os.path.isfile(file_path):
            print(f"不是文件: {file_path}")
            return jsonify({'error': 'Not a file'}), 400
        # 获取文件的 MIME 类型
        mimetype, _ = mimetypes.guess_type(file_path)
        if not mimetype:
            # 根据文件扩展名设置默认 MIME 类型
            ext = os.path.splitext(filename)[1].lower()
            mimetype_map = {
                '.mp4': 'video/mp4',
                '.mov': 'video/quicktime',
                '.avi': 'video/x-msvideo',
                '.flv': 'video/x-flv',
                '.wmv': 'video/x-ms-wmv',
                '.webm': 'video/webm',
                '.mkv': 'video/x-matroska'
            }
            mimetype = mimetype_map.get(ext, 'application/octet-stream')
        
        # 使用 send_file 直接发送文件（支持嵌套路径）
        try:
            # 确保文件路径是绝对路径
            file_path_abs = os.path.abspath(file_path)
            
            # 再次检查文件是否存在
            if not os.path.exists(file_path_abs):
                print(f"文件不存在（绝对路径）: {file_path_abs}")
                return jsonify({'error': 'File not found'}), 404
            
            if not os.path.isfile(file_path_abs):
                print(f"不是文件（绝对路径）: {file_path_abs}")
                return jsonify({'error': 'Not a file'}), 400
            
            response = send_file(
                file_path_abs,
                mimetype=mimetype,
                as_attachment=False,
                download_name=os.path.basename(filename)  # 下载时的文件名
            )
            # 设置 CORS 头，允许跨域访问
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS, HEAD'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Range'
            # 支持视频范围请求（用于视频播放）
            response.headers['Accept-Ranges'] = 'bytes'
            return response
        except Exception as e:
            print(f"发送文件时出错: {str(e)}")
            print(f"文件路径: {file_path}")
            print(f"绝对路径: {os.path.abspath(file_path) if 'file_path' in locals() else 'N/A'}")
            import traceback
            traceback.print_exc()
            return jsonify({'error': f'Failed to send file: {str(e)}'}), 500
    except Exception as e:
        print(f"处理文件请求时出错: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500


@app.route('/api/health', methods=['GET'])
def health_check():
    """健康检查"""
    try:
        from db import get_db
        from sqlalchemy import text
        # 测试数据库连接
        with get_db() as db:
            db.execute(text('SELECT 1'))
        
        return {
            'status': 'healthy',
            'database': 'mysql',
            'message': 'Service is running'
        }, 200
    except Exception as e:
        return {
            'status': 'unhealthy',
            'error': str(e)
        }, 500


@app.route('/<path:path>')
def serve_spa(path):
    """SPA 回退：未匹配到的路径返回 index.html，供前端路由处理（须在 /api/health、/uploads 之后注册）"""
    if path.startswith('api/') or path.startswith('uploads/'):
        from flask import abort
        abort(404)
    frontend_dist = _frontend_dist_dir()
    file_path = os.path.join(frontend_dist, path.replace('/', os.sep))
    if os.path.isfile(file_path):
        return send_from_directory(frontend_dist, path)
    return send_from_directory(frontend_dist, 'index.html')


def is_port_available(port):
    """检查端口是否可用"""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('0.0.0.0', port))
            return True
        except OSError:
            return False


if __name__ == '__main__':
    init_db()
    from config import SERVER_PORT
    port = int(SERVER_PORT)

    if not is_port_available(port):
        print(f"ERROR: port {port} is occupied. Please free it and retry.")
        sys.exit(1)

    task_processor_started = False
    try:
        task_processor = get_task_processor()
        task_processor.start()
        task_processor_started = True
        print("Task processor started.")
    except Exception as e:
        print(f"Task processor failed to start: {e}")
    print(f"Backend URL: http://localhost:{port}")
    print("Press Ctrl+C to stop.\n")

    try:
        app.run(debug=True, host='0.0.0.0', port=port, use_reloader=False)
    finally:
        if task_processor_started:
            try:
                task_processor = get_task_processor()
                task_processor.stop()
            except Exception:
                pass

def print_startup_info():
    """打印启动信息"""
    print("\n" + "="*70)
    print("🚀 抖音中心管理平台 - 启动信息")
    print("="*70)
    
    # 核心模块
    print("\n【核心模块】")
    try:
        from db import get_db
        from sqlalchemy import text
        with get_db() as db:
            db.execute(text('SELECT 1'))
        print("  ✅ 数据库连接模块 - 已启动")
    except Exception as e:
        print(f"  ❌ 数据库连接模块 - 启动失败: {e}")
    
    print("  ✅ Session 安全模块 - 已启动")
    print("  ✅ CORS 跨域模块 - 已启动")
    print("  ✅ 错误处理模块 - 已启动")
    
    # 业务模块
    print("\n【业务模块】")
    for category, modules in registered_modules.items():
        print(f"\n  {category}:")
        for module_name, success, error in modules:
            if success:
                print(f"    ✅ {module_name} - 已启动")
            else:
                print(f"    ❌ {module_name} - 启动失败: {error}")
    
    # 服务模块
    print("\n【服务模块】")
    task_processor_status = False
    if not os.environ.get('WERKZEUG_RUN_MAIN'):
        # 这是主进程，不是重载进程
        try:
            task_processor = get_task_processor()
            task_processor.start()  # 启动定时任务检查器（轻量级，只检查定时任务）
            print("  ✅ 定时任务检查器 - 已启动（每60秒检查一次定时任务）")
            task_processor_status = True
        except Exception as e:
            print(f"  ❌ 定时任务检查器 - 启动失败: {e}")
            print("     ⚠️  定时发布任务将不会自动执行")

        # 可选：自动拉起转码 worker（仅在非生产环境默认启用；或显式 AUTO_START_TRANSCODE_WORKER=true）
        try:
            started = maybe_start_transcode_worker()
            if started:
                print("  ✅ 转码 Worker - 已自动拉起（workers.worker_transcode）")
            else:
                print("  ⏭️  转码 Worker - 未拉起（无待处理任务或已在运行）")
        except Exception as e:
            print(f"  ❌ 转码 Worker - 自动拉起失败: {e}")
    else:
        # 这是重载进程，不启动定时检查器（主进程的检查器会继续运行）
        print("  ⏸️  定时任务检查器 - 已跳过（重载模式）")
    
    print("\n" + "="*70 + "\n")
    return task_processor_status

if False and __name__ == '__main__':
    # 初始化数据库
    init_db()
    
    # 从config.py获取默认端口（已从环境变量读取）
    from config import SERVER_PORT
    port = int(SERVER_PORT)
    
    # 命令行参数优先级最高（用于临时覆盖）
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print(f"警告: 无效的端口号 '{sys.argv[1]}', 使用配置的端口 {port}")
    
    # 检查端口是否可用
    original_port = port
    if not is_port_available(port):
        print(f"⚠️  警告: 端口 {port} 已被占用，尝试其他端口...")
        # 尝试 8081-8089
        for alt_port in range(8081, 8090):
            if is_port_available(alt_port):
                port = alt_port
                print(f"✓ 使用端口 {port} 启动服务器")
                break
        else:
            print(f"❌ 错误: 无法找到可用端口（尝试了 {original_port}-8089）")
            print("\n解决方案：")
            print(f"  1. 关闭占用端口 {original_port} 的程序")
            print(f"  2. 使用其他端口: python app.py <端口号>")
            print(f"  3. 设置环境变量: $env:PORT=8080")
            sys.exit(1)
    
    # 打印启动信息
    task_processor_started = print_startup_info()
    
    print(f"📍 访问地址: http://localhost:{port}")
    print(f"📊 数据库类型: MySQL")
    print(f"💡 按 Ctrl+C 停止服务器\n")
    
    try:
        app.run(
            debug=True,
            host='0.0.0.0',
            port=port,
            use_reloader=False
        )
    except OSError as e:
        if "以一种访问权限不允许的方式做了一个访问套接字的尝试" in str(e) or "permission denied" in str(e).lower():
            print(f"\n❌ 错误: 端口 {port} 访问被拒绝")
            print("可能的原因：")
            print("  1. 端口被其他程序占用")
            print("  2. 需要管理员权限")
            print("  3. 防火墙阻止")
            print("\n解决方案：")
            print(f"  1. 关闭占用端口 {port} 的程序")
            print(f"  2. 使用其他端口: python app.py <端口号>")
            print(f"  3. 以管理员身份运行")
        else:
            print(f"\n❌ 启动服务器时出错: {e}")
        sys.exit(1)
    finally:
        # 停止定时任务检查器
        if task_processor_started:
            try:
                task_processor = get_task_processor()
                task_processor.stop()
                print("\n✅ 定时任务检查器已停止")
            except:
                pass
