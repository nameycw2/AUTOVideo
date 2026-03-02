"""
鎶栭煶涓績绠＄悊骞冲彴 - Flask搴旂敤涓绘枃浠?
妯″潡鍖栬璁★紝鏀寔 MySQL 鏁版嵁搴?
"""

import os
import sys
import config

# 娣诲姞褰撳墠鐩綍鍒?Python 璺緞锛岀‘淇濆彲浠ュ鍏ユā鍧?
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from flask import Flask, send_from_directory, request, jsonify
from flask_cors import CORS

from models import Base
from db import engine

# 瀵煎叆鎵€鏈?API 妯″潡锛堟寜鍔熻兘鍒掑垎锛?
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
from api.editor import editor_bp
from api.money_printer import money_printer_bp

# 瀵煎叆浠诲姟澶勭悊鍣?
from services.task_processor import get_task_processor
from workers.auto_transcode_worker import maybe_start_transcode_worker

app = Flask(__name__, static_folder='../frontend/dist', static_url_path='')

# ==================== Session 瀹夊叏閰嶇疆 ====================
# 璀﹀憡锛氱敓浜х幆澧冨繀椤昏缃己闅忔満 SECRET_KEY锛?
# 鐢熸垚鏂瑰紡锛歱ython -c "import secrets; print(secrets.token_hex(32))"
# 鎵€鏈夊瘑閽ュ繀椤婚€氳繃鐜鍙橀噺閰嶇疆锛岄伩鍏嶇‖缂栫爜鍒颁唬鐮佷腑
secret_key = os.getenv('SECRET_KEY', '')

if not secret_key:
    import warnings
    import secrets
    # 寮€鍙戠幆澧冿細鑷姩鐢熸垚涓€涓复鏃跺瘑閽ワ紙姣忔鍚姩閮戒細鍙樺寲锛?
    # 鐢熶骇鐜锛氬繀椤婚€氳繃鐜鍙橀噺璁剧疆鍥哄畾鐨?SECRET_KEY
    is_production = os.getenv('FLASK_ENV') == 'production' or os.getenv('ENVIRONMENT') == 'production'
    
    if is_production:
        raise ValueError(
            '鉂?閿欒锛氱敓浜х幆澧冨繀椤昏缃?SECRET_KEY 鐜鍙橀噺锛乗n'
            '璇峰湪 .env 鏂囦欢鎴栫郴缁熺幆澧冨彉閲忎腑璁剧疆 SECRET_KEY銆俓n'
            '鐢熸垚鏂瑰紡锛歱ython -c "import secrets; print(secrets.token_hex(32))"'
        )
    else:
        # 寮€鍙戠幆澧冿細鐢熸垚涓存椂瀵嗛挜骞剁粰鍑鸿鍛?
        secret_key = secrets.token_hex(32)
        warnings.warn(
            '鈿狅笍  璀﹀憡锛氭湭璁剧疆 SECRET_KEY 鐜鍙橀噺锛屽凡鑷姩鐢熸垚涓存椂瀵嗛挜锛堜粎鐢ㄤ簬寮€鍙戠幆澧冿級\n'
            '鐢熶骇鐜蹇呴』璁剧疆鍥哄畾鐨?SECRET_KEY 鐜鍙橀噺锛乗n'
            '鐢熸垚鏂瑰紡锛歱ython -c "import secrets; print(secrets.token_hex(32))"\n'
            '鐒跺悗鍦?.env 鏂囦欢涓缃細SECRET_KEY=鐢熸垚鐨勫瘑閽?,
            UserWarning
        )
        print(f'鈩癸笍  寮€鍙戠幆澧冧复鏃?SECRET_KEY 宸茬敓鎴愶紙鏈杩愯鏈夋晥锛?)

app.secret_key = secret_key

# 閰嶇疆 session 瀹夊叏閫夐」
app.config['SESSION_COOKIE_NAME'] = 'session'
app.config['SESSION_COOKIE_HTTPONLY'] = True  # 闃叉 XSS 鏀诲嚮锛岀姝?JavaScript 璁块棶 cookie
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # 闃叉 CSRF 鏀诲嚮锛屽厑璁歌法绔欒姹傛惡甯?cookie
app.config['PERMANENT_SESSION_LIFETIME'] = 86400  # 24灏忔椂锛堢锛?

# 鐢熶骇鐜寤鸿鍚敤浠ヤ笅閰嶇疆锛堥渶瑕?HTTPS锛夛細
# app.config['SESSION_COOKIE_SECURE'] = True  # 浠呭湪 HTTPS 杩炴帴鏃跺彂閫?cookie
# 娉ㄦ剰锛氬紑鍙戠幆澧冿紙HTTP锛変笉瑕佸惎鐢?SESSION_COOKIE_SECURE锛屽惁鍒?cookie 鏃犳硶宸ヤ綔

# 妫€鏌ユ槸鍚︿负鐢熶骇鐜锛堥€氳繃鐜鍙橀噺鍒ゆ柇锛?
is_production = os.getenv('FLASK_ENV') == 'production' or os.getenv('ENVIRONMENT') == 'production'

# 妫€鏌ユ槸鍚︿娇鐢?HTTPS
# 浼樺厛浣跨敤鐜鍙橀噺锛屽鏋滄病鏈夎缃紝榛樿浣跨敤 HTTP锛堥€傜敤浜庨€氳繃 Nginx 鍙嶅悜浠ｇ悊鐨?HTTP锛?
use_https = os.getenv('USE_HTTPS', '').lower() == 'true'

if is_production:
    # 鍙湁鍦ㄦ槑纭娇鐢?HTTPS 鏃舵墠鍚敤 SESSION_COOKIE_SECURE
    # 濡傛灉浣跨敤 HTTP 鎴栭€氳繃 Nginx 鍙嶅悜浠ｇ悊锛堟湭閰嶇疆 SSL锛夛紝涓嶈鍚敤
    if use_https:
        app.config['SESSION_COOKIE_SECURE'] = True
        # 鐢熶骇鐜寤鸿浣跨敤鏇翠弗鏍肩殑 SameSite 绛栫暐
        # app.config['SESSION_COOKIE_SAMESITE'] = 'Strict'  # 鏇翠弗鏍硷紝浣嗗彲鑳藉奖鍝嶈法绔欒姹?
    else:
        # HTTP 鐜涓嶅惎鐢?Secure锛屽惁鍒?Cookie 鏃犳硶宸ヤ綔
        app.config['SESSION_COOKIE_SECURE'] = False
        # 淇濇寔 SameSite=Lax 浠ュ厑璁告甯哥殑璺ㄧ珯瀵艰埅
        app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# 閰嶇疆 CORS锛屽厑璁告惡甯﹀嚟璇?
# 寮€鍙戠幆澧冨厑璁告墍鏈?localhost 鍜?127.0.0.1 鐨勭鍙ｏ紙鍖呮嫭甯歌鐨勫紑鍙戠鍙ｏ級
cors_origins = [
    'http://localhost:3000', 'http://localhost:3001', 'http://localhost:3002', 'http://localhost:3003', 
    'http://localhost:5173', 'http://localhost:8080', 'http://localhost:8081', 'http://localhost:8082',
    'http://127.0.0.1:3000', 'http://127.0.0.1:3001', 'http://127.0.0.1:3002', 'http://127.0.0.1:3003',
    'http://127.0.0.1:5173', 'http://127.0.0.1:8080', 'http://127.0.0.1:8081', 'http://127.0.0.1:8082'
]
# 濡傛灉鐜鍙橀噺璁剧疆浜嗗厑璁哥殑婧愶紝鍒欎娇鐢ㄧ幆澧冨彉閲?
if os.getenv('CORS_ORIGINS'):
    cors_origins = [origin.strip() for origin in os.getenv('CORS_ORIGINS').split(',') if origin.strip()]
# 寮€鍙戠幆澧冿細濡傛灉娌℃湁璁剧疆 CORS_ORIGINS锛屽厑璁告墍鏈?localhost 鍜?127.0.0.1 鐨勭鍙?
elif not is_production:
    # 寮€鍙戠幆澧冨厑璁告墍鏈?localhost 绔彛锛堜娇鐢ㄩ€氶厤绗︽洿鐏垫椿锛?
    cors_origins = ['*']  # 寮€鍙戠幆澧冨厑璁告墍鏈夋潵婧?
# 鐢熶骇鐜锛氬鏋滄病鏈夎缃?CORS_ORIGINS锛屽厑璁告墍鏈夋潵婧愶紙閫氳繃 Nginx 浠ｇ悊鏃讹級
else:
    cors_origins = ['*']  # 鐢熶骇鐜閫氳繃 Nginx 浠ｇ悊锛屽厑璁告墍鏈夋潵婧?

CORS(app, 
     supports_credentials=True,
     origins=cors_origins,
     allow_headers=['Content-Type', 'Authorization', 'X-Requested-With'],
     methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS', 'PATCH'],
     expose_headers=['Content-Type', 'Authorization'],
     max_age=3600)

# 娣诲姞鍏ㄥ眬 CORS 閿欒澶勭悊锛岀‘淇濇墍鏈夊搷搴旈兘鍖呭惈 CORS 澶达紙鍖呮嫭閿欒鍝嶅簲锛?
@app.after_request
def after_request(response):
    """纭繚鎵€鏈夊搷搴旈兘鍖呭惈 CORS 澶达紝鍖呮嫭閿欒鍝嶅簲"""
    origin = request.headers.get('Origin')
    
    # 濡傛灉璇锋眰鍖呭惈 Origin 澶达紝娣诲姞 CORS 鍝嶅簲澶?
    if origin:
        # 寮€鍙戠幆澧冿細浼樺厛鍏佽鎵€鏈?localhost 鍜?127.0.0.1
        if not is_production and ('localhost' in origin or '127.0.0.1' in origin):
            response.headers['Access-Control-Allow-Origin'] = origin
        # 妫€鏌ユ槸鍚﹀湪鍏佽鐨勬簮鍒楄〃涓紝鎴栬€呭厑璁告墍鏈夋簮
        elif cors_origins == ['*'] or origin in cors_origins:
            response.headers['Access-Control-Allow-Origin'] = origin
        
        # 鍙湁鍦ㄨ缃簡 Access-Control-Allow-Origin 鏃舵墠璁剧疆鍏朵粬 CORS 澶?
        if 'Access-Control-Allow-Origin' in response.headers:
            response.headers['Access-Control-Allow-Credentials'] = 'true'
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS, PATCH'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With'
            response.headers['Access-Control-Expose-Headers'] = 'Content-Type, Authorization'
            response.headers['Access-Control-Max-Age'] = '3600'
    
    return response

# 澶勭悊 OPTIONS 棰勬璇锋眰
@app.before_request
def handle_preflight():
    """澶勭悊 CORS 棰勬璇锋眰"""
    if request.method == "OPTIONS":
        response = jsonify({})
        origin = request.headers.get('Origin')
        if origin:
            # 寮€鍙戠幆澧冿細鍏佽鎵€鏈?localhost 鍜?127.0.0.1
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

# 鍏ㄥ眬閿欒澶勭悊锛岀‘淇濋敊璇搷搴斾篃鍖呭惈 CORS 澶?
@app.errorhandler(Exception)
def handle_exception(e):
    """澶勭悊鎵€鏈夊紓甯革紝纭繚閿欒鍝嶅簲鍖呭惈 CORS 澶?""
    from flask import make_response
    import traceback
    
    # 璁板綍閿欒
    error_type = type(e).__name__
    error_msg = str(e)
    print(f"\n{'='*60}")
    print(f"鉂?閿欒绫诲瀷: {error_type}")
    print(f"鉂?閿欒淇℃伅: {error_msg}")
    print(f"{'='*60}")
    traceback.print_exc()
    print(f"{'='*60}\n")
    
    # 纭畾 HTTP 鐘舵€佺爜
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
    
    # 鍒涘缓閿欒鍝嶅簲
    response = make_response(jsonify({
        'code': status_code,
        'message': error_msg if status_code != 500 else '鏈嶅姟鍣ㄥ唴閮ㄩ敊璇?,
        'data': None
    }), status_code)
    
    # 娣诲姞 CORS 澶?
    origin = request.headers.get('Origin')
    if origin:
        # 寮€鍙戠幆澧冿細浼樺厛鍏佽鎵€鏈?localhost 鍜?127.0.0.1
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

# 娉ㄥ唽鎵€鏈?Blueprint
# 瀹氫箟妯″潡鍒嗙被鍜屼腑鏂囧悕绉?
blueprint_modules = {
    '璁よ瘉鎺堟潈妯″潡': [
        ('auth', auth_bp),
        ('users', users_bp),
        ('login', login_bp),
    ],
    '璁惧绠＄悊妯″潡': [
        ('devices', devices_bp),
    ],
    '璐﹀彿绠＄悊妯″潡': [
        ('accounts', accounts_bp),
    ],
    '瑙嗛澶勭悊妯″潡': [
        ('video', video_bp),
        ('video_library', video_library_bp),
        ('video_editor', video_editor_bp),
        ('editor', editor_bp),
    ],
    'AI鍔熻兘妯″潡': [
        ('ai', ai_bp),
        ('money_printer', money_printer_bp),
    ],
    '鑱婂ぉ鐩戝惉妯″潡': [
        ('chat', chat_bp),
        ('listen', listen_bp),
    ],
    '绀句氦骞冲彴妯″潡': [
        ('social', social_bp),
        ('publish', publish_bp),
        ('publish_plans', publish_plans_bp),
    ],
    '娑堟伅绠＄悊妯″潡': [
        ('messages', messages_bp),
    ],
    '鏁版嵁缁熻妯″潡': [
        ('stats', stats_bp),
        ('data_center', data_center_bp),
    ],
    '鍟嗗绠＄悊妯″潡': [
        ('merchants', merchants_bp),
    ],
    '绱犳潗绠＄悊妯″潡': [
        ('material', material_bp),
    ],
}

# 娉ㄥ唽鎵€鏈?Blueprint 骞惰褰曠姸鎬?
registered_modules = {}
for category, modules in blueprint_modules.items():
    registered_modules[category] = []
    for module_name, blueprint in modules:
        try:
            app.register_blueprint(blueprint)
            registered_modules[category].append((module_name, True, None))
        except Exception as e:
            registered_modules[category].append((module_name, False, str(e)))


def init_db():
    """鍒濆鍖栨暟鎹簱琛?""
    try:
        # 娴嬭瘯鏁版嵁搴撹繛鎺?
        from db import get_db
        from sqlalchemy import text
        with get_db() as db:
            db.execute(text('SELECT 1'))
        print("鉁?鏁版嵁搴撹繛鎺ユ垚鍔?)
        
        # 鍒涘缓琛?
        Base.metadata.create_all(engine)
        print("鉁?鏁版嵁搴撹〃鍒濆鍖栨垚鍔?)
        
        # 淇敼鐢ㄦ埛鍚嶅拰閭鍒楃殑鎺掑簭瑙勫垯涓簎tf8mb4_bin锛屽疄鐜板ぇ灏忓啓鏁忔劅
        with get_db() as db:
            try:
                db.execute(text("ALTER TABLE users MODIFY COLUMN username VARCHAR(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;"))
                db.execute(text("ALTER TABLE users MODIFY COLUMN email VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;"))
                print("鉁?鐢ㄦ埛鍚嶅拰閭鍒楀凡璁剧疆涓哄ぇ灏忓啓鏁忔劅")
            except Exception as e:
                # 濡傛灉琛ㄤ笉瀛樺湪鎴栧垪涓嶅瓨鍦紝蹇界暐閿欒
                print(f"鈿狅笍 璁剧疆澶у皬鍐欐晱鎰熸椂鍑虹幇璀﹀憡: {e}")
    except Exception as e:
        error_msg = str(e)
        if "Access denied" in error_msg or "1045" in error_msg:
            print("\n" + "="*60)
            print("鉂?鏁版嵁搴撹繛鎺ュけ璐ワ細鐢ㄦ埛鍚嶆垨瀵嗙爜閿欒")
            print("="*60)
            print("\n璇烽厤缃?MySQL 鏁版嵁搴撹繛鎺ヤ俊鎭細")
            print("\n鏂规硶1锛氳缃幆澧冨彉閲?)
            print("  export DB_HOST=localhost")
            print("  export DB_PORT=3306")
            print("  export DB_NAME=autovideo")
            print("  export DB_USER=root")
            print("  export DB_PASSWORD=your_password")
            print("\n鏂规硶2锛氱洿鎺ヤ慨鏀?backend/config.py 鏂囦欢")
            print("  淇敼 MYSQL_CONFIG 瀛楀吀涓殑閰嶇疆椤?)
            print("\n鏂规硶3锛氬垱寤烘暟鎹簱锛堝鏋滆繕娌℃湁锛?)
            print("  mysql -u root -p")
            print("  CREATE DATABASE autovideo CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
            print("="*60 + "\n")
        elif "Unknown database" in error_msg or "1049" in error_msg:
            print("\n" + "="*60)
            print("鉂?鏁版嵁搴撲笉瀛樺湪")
            print("="*60)
            print("\n璇峰厛鍒涘缓鏁版嵁搴擄細")
            print("  mysql -u root -p")
            print("  CREATE DATABASE autovideo CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
            print("="*60 + "\n")
        else:
            print(f"\n鉂?鏁版嵁搴撹繛鎺ュけ璐? {error_msg}\n")
        raise


# ==================== 鍓嶇椤甸潰璺敱 ====================

@app.route('/')
def index():
    """鎻愪緵鍓嶇椤甸潰"""
    return send_from_directory('../frontend/dist', 'index.html')


@app.route('/login-helper')
def login_helper():
    """鎻愪緵鐧诲綍鍔╂墜椤甸潰"""
    return send_from_directory('../frontend/dist', 'index.html')


# 鎻愪緵涓婁紶鏂囦欢鐨勯潤鎬佽矾鐢?
@app.route('/uploads/<path:filename>', methods=['GET', 'OPTIONS'])
def uploaded_file(filename):
    """鎻愪緵涓婁紶鐨勬枃浠惰闂?""
    from flask import Response, request, send_file
    import mimetypes
    
    try:
        # 澶勭悊 OPTIONS 璇锋眰锛圕ORS 棰勬锛?
        if request.method == 'OPTIONS':
            response = Response()
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
            return response
        
        upload_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'uploads')
        
        # 澶勭悊璺緞锛歎RL涓娇鐢ㄦ鏂滄潬锛學indows闇€瑕佽浆鎹负绯荤粺璺緞
        # filename 鍙兘鏄?"materials/videos/xxx.mp4"
        # 闇€瑕佽浆鎹负绯荤粺璺緞鏍煎紡
        filename_normalized = filename.replace('/', os.sep).replace('\\', os.sep)
        file_path = os.path.join(upload_dir, filename_normalized)
        
        # 瑙勮寖鍖栬矾寰勶紙澶勭悊 .. 绛夛級
        file_path = os.path.normpath(file_path)
        upload_dir = os.path.normpath(upload_dir)
        
        # 璋冭瘯淇℃伅
        print(f"璇锋眰鏂囦欢: {filename}")
        print(f"瑙勮寖鍖栨枃浠跺悕: {filename_normalized}")
        print(f"涓婁紶鐩綍: {upload_dir}")
        print(f"鏂囦欢璺緞: {file_path}")
        print(f"鏂囦欢鏄惁瀛樺湪: {os.path.exists(file_path)}")
        
        # 瀹夊叏妫€鏌ワ細纭繚鏂囦欢鍦?uploads 鐩綍鍐?
        upload_dir_abs = os.path.abspath(upload_dir)
        file_path_abs = os.path.abspath(file_path)
        if not file_path_abs.startswith(upload_dir_abs):
            print(f"璺緞瀹夊叏妫€鏌ュけ璐? {file_path_abs} 涓嶅湪 {upload_dir_abs} 鍐?)
            return jsonify({'error': 'Invalid file path'}), 403
        
        if not os.path.exists(file_path):
            print(f"鏂囦欢涓嶅瓨鍦? {file_path}")
            return jsonify({'error': 'File not found'}), 404
        
        if not os.path.isfile(file_path):
            print(f"涓嶆槸鏂囦欢: {file_path}")
            return jsonify({'error': 'Not a file'}), 400
        # 鑾峰彇鏂囦欢鐨?MIME 绫诲瀷
        mimetype, _ = mimetypes.guess_type(file_path)
        if not mimetype:
            # 鏍规嵁鏂囦欢鎵╁睍鍚嶈缃粯璁?MIME 绫诲瀷
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
        
        # 浣跨敤 send_file 鐩存帴鍙戦€佹枃浠讹紙鏀寔宓屽璺緞锛?
        try:
            # 纭繚鏂囦欢璺緞鏄粷瀵硅矾寰?
            file_path_abs = os.path.abspath(file_path)
            
            # 鍐嶆妫€鏌ユ枃浠舵槸鍚﹀瓨鍦?
            if not os.path.exists(file_path_abs):
                print(f"鏂囦欢涓嶅瓨鍦紙缁濆璺緞锛? {file_path_abs}")
                return jsonify({'error': 'File not found'}), 404
            
            if not os.path.isfile(file_path_abs):
                print(f"涓嶆槸鏂囦欢锛堢粷瀵硅矾寰勶級: {file_path_abs}")
                return jsonify({'error': 'Not a file'}), 400
            
            response = send_file(
                file_path_abs,
                mimetype=mimetype,
                as_attachment=False,
                download_name=os.path.basename(filename)  # 涓嬭浇鏃剁殑鏂囦欢鍚?
            )
            # 璁剧疆 CORS 澶达紝鍏佽璺ㄥ煙璁块棶
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS, HEAD'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Range'
            # 鏀寔瑙嗛鑼冨洿璇锋眰锛堢敤浜庤棰戞挱鏀撅級
            response.headers['Accept-Ranges'] = 'bytes'
            return response
        except Exception as e:
            print(f"鍙戦€佹枃浠舵椂鍑洪敊: {str(e)}")
            print(f"鏂囦欢璺緞: {file_path}")
            print(f"缁濆璺緞: {os.path.abspath(file_path) if 'file_path' in locals() else 'N/A'}")
            import traceback
            traceback.print_exc()
            return jsonify({'error': f'Failed to send file: {str(e)}'}), 500
    except Exception as e:
        print(f"澶勭悊鏂囦欢璇锋眰鏃跺嚭閿? {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500


@app.route('/api/health', methods=['GET'])
def health_check():
    """鍋ュ悍妫€鏌?""
    try:
        from db import get_db
        from sqlalchemy import text
        # 娴嬭瘯鏁版嵁搴撹繛鎺?
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


def is_port_available(port):
    """妫€鏌ョ鍙ｆ槸鍚﹀彲鐢?""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('0.0.0.0', port))
            return True
        except OSError:
            return False

def print_startup_info():
    """鎵撳嵃鍚姩淇℃伅"""
    print("\n" + "="*70)
    print("馃殌 鎶栭煶涓績绠＄悊骞冲彴 - 鍚姩淇℃伅")
    print("="*70)
    
    # 鏍稿績妯″潡
    print("\n銆愭牳蹇冩ā鍧椼€?)
    try:
        from db import get_db
        from sqlalchemy import text
        with get_db() as db:
            db.execute(text('SELECT 1'))
        print("  鉁?鏁版嵁搴撹繛鎺ユā鍧?- 宸插惎鍔?)
    except Exception as e:
        print(f"  鉂?鏁版嵁搴撹繛鎺ユā鍧?- 鍚姩澶辫触: {e}")
    
    print("  鉁?Session 瀹夊叏妯″潡 - 宸插惎鍔?)
    print("  鉁?CORS 璺ㄥ煙妯″潡 - 宸插惎鍔?)
    print("  鉁?閿欒澶勭悊妯″潡 - 宸插惎鍔?)
    
    # 涓氬姟妯″潡
    print("\n銆愪笟鍔℃ā鍧椼€?)
    for category, modules in registered_modules.items():
        print(f"\n  {category}:")
        for module_name, success, error in modules:
            if success:
                print(f"    鉁?{module_name} - 宸插惎鍔?)
            else:
                print(f"    鉂?{module_name} - 鍚姩澶辫触: {error}")
    
    # 鏈嶅姟妯″潡
    print("\n銆愭湇鍔℃ā鍧椼€?)
    task_processor_status = False
    if not os.environ.get('WERKZEUG_RUN_MAIN'):
        # 杩欐槸涓昏繘绋嬶紝涓嶆槸閲嶈浇杩涚▼
        try:
            task_processor = get_task_processor()
            task_processor.start()  # 鍚姩瀹氭椂浠诲姟妫€鏌ュ櫒锛堣交閲忕骇锛屽彧妫€鏌ュ畾鏃朵换鍔★級
            print("  鉁?瀹氭椂浠诲姟妫€鏌ュ櫒 - 宸插惎鍔紙姣?0绉掓鏌ヤ竴娆″畾鏃朵换鍔★級")
            task_processor_status = True
        except Exception as e:
            print(f"  鉂?瀹氭椂浠诲姟妫€鏌ュ櫒 - 鍚姩澶辫触: {e}")
            print("     鈿狅笍  瀹氭椂鍙戝竷浠诲姟灏嗕笉浼氳嚜鍔ㄦ墽琛?)

        # 鍙€夛細鑷姩鎷夎捣杞爜 worker锛堜粎鍦ㄩ潪鐢熶骇鐜榛樿鍚敤锛涙垨鏄惧紡 AUTO_START_TRANSCODE_WORKER=true锛?
        try:
            started = maybe_start_transcode_worker()
            if started:
                print("  鉁?杞爜 Worker - 宸茶嚜鍔ㄦ媺璧凤紙workers.worker_transcode锛?)
            else:
                print("  鈴笍  杞爜 Worker - 鏈媺璧凤紙鏃犲緟澶勭悊浠诲姟鎴栧凡鍦ㄨ繍琛岋級")
        except Exception as e:
            print(f"  鉂?杞爜 Worker - 鑷姩鎷夎捣澶辫触: {e}")
    else:
        # 杩欐槸閲嶈浇杩涚▼锛屼笉鍚姩瀹氭椂妫€鏌ュ櫒锛堜富杩涚▼鐨勬鏌ュ櫒浼氱户缁繍琛岋級
        print("  鈴革笍  瀹氭椂浠诲姟妫€鏌ュ櫒 - 宸茶烦杩囷紙閲嶈浇妯″紡锛?)
    
    print("\n" + "="*70 + "\n")
    return task_processor_status

if __name__ == '__main__':
    # 鍒濆鍖栨暟鎹簱
    init_db()
    
    # 浠巆onfig.py鑾峰彇榛樿绔彛锛堝凡浠庣幆澧冨彉閲忚鍙栵級
    from config import SERVER_PORT
    port = SERVER_PORT
    
    # 鍛戒护琛屽弬鏁颁紭鍏堢骇鏈€楂橈紙鐢ㄤ簬涓存椂瑕嗙洊锛?
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print(f"璀﹀憡: 鏃犳晥鐨勭鍙ｅ彿 '{sys.argv[1]}', 浣跨敤閰嶇疆鐨勭鍙?{port}")
    
    # 妫€鏌ョ鍙ｆ槸鍚﹀彲鐢?
    original_port = port
    if not is_port_available(port):
        print(f"鈿狅笍  璀﹀憡: 绔彛 {port} 宸茶鍗犵敤锛屽皾璇曞叾浠栫鍙?..")
        # 灏濊瘯 8081-8089
        for alt_port in range(8081, 8090):
            if is_port_available(alt_port):
                port = alt_port
                print(f"鉁?浣跨敤绔彛 {port} 鍚姩鏈嶅姟鍣?)
                break
        else:
            print(f"鉂?閿欒: 鏃犳硶鎵惧埌鍙敤绔彛锛堝皾璇曚簡 {original_port}-8089锛?)
            print("\n瑙ｅ喅鏂规锛?)
            print(f"  1. 鍏抽棴鍗犵敤绔彛 {original_port} 鐨勭▼搴?)
            print(f"  2. 浣跨敤鍏朵粬绔彛: python app.py <绔彛鍙?")
            print(f"  3. 璁剧疆鐜鍙橀噺: $env:PORT=8080")
            sys.exit(1)
    
    # 鎵撳嵃鍚姩淇℃伅
    task_processor_started = print_startup_info()
    
    print(f"馃搷 璁块棶鍦板潃: http://localhost:{port}")
    print(f"馃搳 鏁版嵁搴撶被鍨? MySQL")
    print(f"馃挕 鎸?Ctrl+C 鍋滄鏈嶅姟鍣╘n")
    
    try:
        app.run(
            debug=True,
            host='0.0.0.0',
            port=port,
            use_reloader=False
        )
    except OSError as e:
        if "浠ヤ竴绉嶈闂潈闄愪笉鍏佽鐨勬柟寮忓仛浜嗕竴涓闂鎺ュ瓧鐨勫皾璇? in str(e) or "permission denied" in str(e).lower():
            print(f"\n鉂?閿欒: 绔彛 {port} 璁块棶琚嫆缁?)
            print("鍙兘鐨勫師鍥狅細")
            print("  1. 绔彛琚叾浠栫▼搴忓崰鐢?)
            print("  2. 闇€瑕佺鐞嗗憳鏉冮檺")
            print("  3. 闃茬伀澧欓樆姝?)
            print("\n瑙ｅ喅鏂规锛?)
            print(f"  1. 鍏抽棴鍗犵敤绔彛 {port} 鐨勭▼搴?)
            print(f"  2. 浣跨敤鍏朵粬绔彛: python app.py <绔彛鍙?")
            print(f"  3. 浠ョ鐞嗗憳韬唤杩愯")
        else:
            print(f"\n鉂?鍚姩鏈嶅姟鍣ㄦ椂鍑洪敊: {e}")
        sys.exit(1)
    finally:
        # 鍋滄瀹氭椂浠诲姟妫€鏌ュ櫒
        if task_processor_started:
            try:
                task_processor = get_task_processor()
                task_processor.stop()
                print("\n鉁?瀹氭椂浠诲姟妫€鏌ュ櫒宸插仠姝?)
            except:
                pass
