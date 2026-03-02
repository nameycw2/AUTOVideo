"""
鏁版嵁妯″瀷瀹氫箟
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Index, Text, Float, REAL, Boolean
from sqlalchemy.orm import declarative_base
from werkzeug.security import generate_password_hash, check_password_hash

Base = declarative_base()


# 鐢ㄦ埛瑙掕壊锛歴uper_admin=瓒呯骇绠＄悊鍛? parent=姣嶈处鍙? child=瀛愯处鍙?
USER_ROLE_SUPER_ADMIN = 'super_admin'
USER_ROLE_PARENT = 'parent'
USER_ROLE_CHILD = 'child'


class User(Base):
    """鐢ㄦ埛琛?""
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    avatar_url = Column(String(500))
    is_verified = Column(Boolean, default=False)
    # 瑙掕壊锛歴uper_admin / parent / child
    role = Column(String(32), default=USER_ROLE_CHILD, nullable=False, index=True)
    # 瀛愯处鍙峰綊灞炵殑姣嶈处鍙?ID锛屼粎 role=child 鏃舵湁鍊?
    parent_id = Column(Integer, ForeignKey('users.id'), nullable=True, index=True)
    # 姣嶈处鍙蜂笅灞炲瓙璐﹀彿鏁伴噺涓婇檺锛屼粎 role=parent 鏃舵湁鏁堬紱NULL 琛ㄧず涓嶉檺鍒?
    max_children = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=lambda: __import__('datetime').datetime.now())
    updated_at = Column(DateTime, default=lambda: __import__('datetime').datetime.now(),
                       onupdate=lambda: __import__('datetime').datetime.now())
    
    def set_password(self, password):
        """璁剧疆瀵嗙爜锛堝姞瀵嗭級"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """楠岃瘉瀵嗙爜"""
        return check_password_hash(self.password_hash, password)


class EmailVerification(Base):
    """???????????????"""
    __tablename__ = 'email_verifications'

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), nullable=False, index=True)
    code = Column(String(20), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime)
    created_at = Column(DateTime, default=lambda: __import__('datetime').datetime.now())


class Device(Base):
    """璁惧琛?""
    __tablename__ = 'devices'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    device_id = Column(String(255), unique=True, nullable=False, index=True)
    device_name = Column(String(255))
    ip_address = Column(String(50))
    status = Column(String(50), default='offline')
    last_heartbeat = Column(DateTime)
    created_at = Column(DateTime, default=lambda: __import__('datetime').datetime.now())
    updated_at = Column(DateTime, default=lambda: __import__('datetime').datetime.now(), 
                       onupdate=lambda: __import__('datetime').datetime.now())


class Account(Base):
    """璐﹀彿琛?""
    __tablename__ = 'accounts'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    device_id = Column(Integer, ForeignKey('devices.id'), nullable=False)
    account_name = Column(String(255), nullable=False, index=True)
    platform = Column(String(50), default='douyin')
    cookie_file_path = Column(String(500))
    cookies = Column(Text)  # JSON瀛楃涓?
    login_status = Column(String(50), default='logged_out')
    last_login_time = Column(DateTime)
    created_at = Column(DateTime, default=lambda: __import__('datetime').datetime.now())
    updated_at = Column(DateTime, default=lambda: __import__('datetime').datetime.now(),
                       onupdate=lambda: __import__('datetime').datetime.now())


    plan_video_id = Column(Integer, ForeignKey('plan_videos.id'), nullable=True)
    created_at = Column(DateTime, default=lambda: __import__('datetime').datetime.now())
    started_at = Column(DateTime)
    completed_at = Column(DateTime)


class ChatTask(Base):
    """瀵硅瘽浠诲姟琛?""
    __tablename__ = 'chat_tasks'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey('accounts.id'), nullable=False)
    device_id = Column(Integer, ForeignKey('devices.id'), nullable=False)
    target_user = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    status = Column(String(50), default='pending')
    error_message = Column(Text)
    created_at = Column(DateTime, default=lambda: __import__('datetime').datetime.now())
    started_at = Column(DateTime)
    completed_at = Column(DateTime)


class ListenTask(Base):
    """鐩戝惉浠诲姟琛?""
    __tablename__ = 'listen_tasks'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey('accounts.id'), nullable=False)
    device_id = Column(Integer, ForeignKey('devices.id'), nullable=False)
    action = Column(String(50), default='start')
    status = Column(String(50), default='pending')
    error_message = Column(Text)
    created_at = Column(DateTime, default=lambda: __import__('datetime').datetime.now())
    started_at = Column(DateTime)
    completed_at = Column(DateTime)


class Message(Base):
    """娑堟伅琛?""
    __tablename__ = 'messages'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey('accounts.id'), nullable=False, index=True)
    user_name = Column(String(255), nullable=False, index=True)
    text = Column(Text, nullable=False)
    is_me = Column(Integer, default=0)
    message_time = Column(String(100))
    timestamp = Column(DateTime, default=lambda: __import__('datetime').datetime.now(), index=True)
    created_at = Column(DateTime, default=lambda: __import__('datetime').datetime.now())


class PublishPlan(Base):
    """鍙戝竷璁″垝琛?""
    __tablename__ = 'publish_plans'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    plan_name = Column(String(255), nullable=False)
    platform = Column(String(50), default='douyin')
    merchant_id = Column(Integer, ForeignKey('merchants.id'), nullable=True)
    video_count = Column(Integer, default=0)
    published_count = Column(Integer, default=0)
    pending_count = Column(Integer, default=0)
    claimed_count = Column(Integer, default=0)
    account_count = Column(Integer, default=0)
    account_ids = Column(Text, nullable=True)  # JSON字符串，存储指定的账号ID列表，如 "[1,2,3]"
    distribution_mode = Column(String(50), default='manual')  # manual, sms, qrcode, ai
    status = Column(String(50), default='pending')  # pending, publishing, completed, failed
    publish_time = Column(DateTime)
    created_at = Column(DateTime, default=lambda: __import__('datetime').datetime.now())
    updated_at = Column(DateTime, default=lambda: __import__('datetime').datetime.now(),
                       onupdate=lambda: __import__('datetime').datetime.now())


class PlanVideo(Base):
    """鍙戝竷璁″垝鍏宠仈鐨勮棰戣〃"""
    __tablename__ = 'plan_videos'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    plan_id = Column(Integer, ForeignKey('publish_plans.id'), nullable=False)
    video_url = Column(String(1000), nullable=False)
    video_title = Column(String(500))  # 视频标题
    video_description = Column(Text, nullable=True)  # 视频正文/描述
    video_tags = Column(String(500), nullable=True)  # 视频标签/话题，逗号分隔或JSON格式
    thumbnail_url = Column(String(1000))
    schedule_time = Column(DateTime, nullable=True)  # 该视频的发布时间（用于分阶段发布），如果为None则使用计划的publish_time
    status = Column(String(50), default='pending')
    created_at = Column(DateTime, default=lambda: __import__('datetime').datetime.now())


class Merchant(Base):
    """鍟嗗琛?""
    __tablename__ = 'merchants'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    merchant_name = Column(String(255), nullable=False, unique=True)
    contact_person = Column(String(100))
    contact_phone = Column(String(50))
    contact_email = Column(String(100))
    address = Column(String(500))
    status = Column(String(50), default='active')  # active, inactive
    created_at = Column(DateTime, default=lambda: __import__('datetime').datetime.now())
    updated_at = Column(DateTime, default=lambda: __import__('datetime').datetime.now(),
                       onupdate=lambda: __import__('datetime').datetime.now())


class VideoLibrary(Base):
    """浜戣棰戝簱琛?""
    __tablename__ = 'video_library'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)  # 鐢ㄦ埛ID锛岀敤浜庢暟鎹殧绂?
    video_name = Column(String(255), nullable=False)
    video_url = Column(String(1000), nullable=False)
    thumbnail_url = Column(String(1000))
    video_size = Column(Integer)  # 鏂囦欢澶у皬锛堝瓧鑺傦級
    duration = Column(Integer)  # 瑙嗛鏃堕暱锛堢锛?
    platform = Column(String(50))  # 鏉ユ簮骞冲彴
    tags = Column(String(500))  # 鏍囩锛岄€楀彿鍒嗛殧
    description = Column(Text)
    upload_time = Column(DateTime, default=lambda: __import__('datetime').datetime.now())
    created_at = Column(DateTime, default=lambda: __import__('datetime').datetime.now())
    updated_at = Column(DateTime, default=lambda: __import__('datetime').datetime.now(),
                       onupdate=lambda: __import__('datetime').datetime.now())


class AccountStats(Base):
    """璐﹀彿缁熻鏁版嵁琛紙鐢ㄤ簬鏁版嵁涓績锛?""
    __tablename__ = 'account_stats'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey('accounts.id'), nullable=False)
    stat_date = Column(DateTime, nullable=False)  # 缁熻鏃ユ湡
    platform = Column(String(50), default='douyin')
    followers = Column(Integer, default=0)  # 绮変笣鏁?
    playbacks = Column(Integer, default=0)  # 鎾斁閲?
    likes = Column(Integer, default=0)  # 鐐硅禐鏁?
    comments = Column(Integer, default=0)  # 璇勮鏁?
    shares = Column(Integer, default=0)  # 鍒嗕韩鏁?
    published_videos = Column(Integer, default=0)  # 鍙戝竷瑙嗛鏁?
    created_at = Column(DateTime, default=lambda: __import__('datetime').datetime.now())


class Material(Base):
    """绱犳潗琛紙瑙嗛/闊抽绱犳潗锛?""
    __tablename__ = 'materials'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)  # 鏂囦欢鍚?
    status = Column(String(50), default='ready')  # ready/processing/failed
    path = Column(String(500), nullable=True)  # 褰撳墠鍙敤鐨勬枃浠惰矾寰勶紙鐩稿 BASE_DIR锛?
    original_path = Column(String(500), nullable=True)  # 浠呭綋鍙戠敓杞爜鏃朵繚鐣欙紙鏂规C锛?
    meta_json = Column(Text, nullable=True)  # ffprobe 缁撴灉鎽樿锛屼究浜庢帓鏌?灞曠ず
    type = Column(String(50), nullable=False)  # video/audio
    duration = Column(REAL)  # 鏃堕暱锛堢锛夛紝浣跨敤 REAL 鏀寔灏忔暟
    width = Column(Integer)  # 瀹斤紙瑙嗛锛?
    height = Column(Integer)  # 楂橈紙瑙嗛锛?
    size = Column(Integer)  # 鏂囦欢澶у皬锛堝瓧鑺傦級
    created_at = Column(DateTime, default=lambda: __import__('datetime').datetime.now())
    updated_at = Column(DateTime, default=lambda: __import__('datetime').datetime.now(),
                       onupdate=lambda: __import__('datetime').datetime.now())


class VideoEditTask(Base):
    """瑙嗛鍓緫浠诲姟琛?""
    __tablename__ = 'video_edit_tasks'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)  # 鐢ㄦ埛ID锛岀敤浜庢暟鎹殧绂?
    video_ids = Column(Text, nullable=False)  # 瑙嗛ID鍒楄〃锛岄€楀彿鍒嗛殧
    voice_id = Column(Integer, nullable=True)  # 閰嶉煶闊抽ID
    bgm_id = Column(Integer, nullable=True)  # BGM闊抽ID
    speed = Column(Float, default=1.0)  # 鎾斁閫熷害锛?.0=姝ｅ父閫熷害锛?
    subtitle_path = Column(String(1000), nullable=True)  # 瀛楀箷鏂囦欢璺緞
    filter_type = Column(String(50), nullable=True)  # 婊ら暅绫诲瀷锛坴intage/noir/cyberpunk绛夛級
    filter_intensity = Column(Float, default=1.0)  # 婊ら暅寮哄害锛?.0-1.0锛?
    output_path = Column(String(1000), nullable=True)  # 杈撳嚭鏂囦欢璺緞锛堢浉瀵硅矾寰勶級
    output_filename = Column(String(255), nullable=True)  # 杈撳嚭鏂囦欢鍚?
    preview_url = Column(String(1000), nullable=True)  # 棰勮URL
    status = Column(String(50), default='pending')  # pending/running/success/fail
    progress = Column(Integer, default=0)  # 杩涘害锛?-100锛?
    error_message = Column(Text, nullable=True)  # 閿欒淇℃伅
    created_at = Column(DateTime, default=lambda: __import__('datetime').datetime.now())
    updated_at = Column(DateTime, default=lambda: __import__('datetime').datetime.now(),
                       onupdate=lambda: __import__('datetime').datetime.now())


class MaterialTranscodeTask(Base):
    """绱犳潗杞爜浠诲姟琛紙DB 闃熷垪锛?""
    __tablename__ = 'material_transcode_tasks'

    id = Column(Integer, primary_key=True, autoincrement=True)
    material_id = Column(Integer, ForeignKey('materials.id'), nullable=False, index=True)

    input_path = Column(String(500), nullable=False)  # 鍘熷鏂囦欢鐩稿璺緞
    output_path = Column(String(500), nullable=False)  # 杞爜浜х墿鐩稿璺緞
    kind = Column(String(50), nullable=False)  # video/audio

    status = Column(String(50), default='pending')  # pending/running/success/fail
    progress = Column(Integer, default=0)  # 0-100
    error_message = Column(Text, nullable=True)

    attempts = Column(Integer, default=0)
    max_attempts = Column(Integer, default=3)

    locked_by = Column(String(100), nullable=True)
    locked_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=lambda: __import__('datetime').datetime.now())
    updated_at = Column(
        DateTime,
        default=lambda: __import__('datetime').datetime.now(),
        onupdate=lambda: __import__('datetime').datetime.now(),
    )


# 鍒涘缓绱㈠紩
Index('idx_messages_account_id', Message.account_id)
Index('idx_messages_timestamp', Message.timestamp)
Index('idx_messages_user_name', Message.user_name)
Index('idx_publish_plans_status', PublishPlan.status)
Index('idx_publish_plans_platform', PublishPlan.platform)
Index('idx_account_stats_account_date', AccountStats.account_id, AccountStats.stat_date)
Index('idx_materials_type_time', Material.type, Material.created_at)
Index('idx_materials_status_time', Material.status, Material.updated_at)
# 娉ㄦ剰锛歱ath 瀛楁鐨勫敮涓€鎬х敱搴旂敤灞備繚璇侊紝鍥犱负 MySQL 瀵归暱瀛楁鐨勫敮涓€绱㈠紩鏈夐檺鍒?
# 濡傛灉闇€瑕佹暟鎹簱灞傞潰鐨勫敮涓€鎬э紝鍙互鑰冭檻浣跨敤鍝堝笇瀛楁鎴栫缉鐭矾寰勯暱搴?
Index('idx_video_edit_tasks_status_time', VideoEditTask.status, VideoEditTask.created_at)
Index('idx_video_edit_tasks_update_time', VideoEditTask.updated_at)

Index('idx_material_transcode_tasks_status_time', MaterialTranscodeTask.status, MaterialTranscodeTask.created_at)
Index('idx_material_transcode_tasks_lock', MaterialTranscodeTask.status, MaterialTranscodeTask.locked_at)

