"""
MoneyPrinterTurbo 视频 AI 生成 API
一键生成高清短视频
"""
import os
import shutil
import sys
import uuid
import logging
from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename

from utils import response_success, response_error, login_required

logger = logging.getLogger(__name__)

money_printer_bp = Blueprint('money_printer', __name__, url_prefix='/api/money-printer')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UPLOAD_DIR = os.path.join(BASE_DIR, 'uploads', 'materials', 'ai_video')

if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)


def _get_deepseek_api_key():
    """获取 DeepSeek API Key"""
    from config import DEEPSEEK_API_KEY
    return DEEPSEEK_API_KEY


def _get_pexels_api_key():
    """获取 Pexels API Key"""
    return os.environ.get('PEXELS_API_KEY', '')


@money_printer_bp.route('/upload', methods=['POST'])
@login_required
def upload_material():
    """
    上传素材文件
    
    返回:
        {
            "code": 200,
            "data": {
                "url": "string",
                "filename": "string"
            }
        }
    """
    try:
        if 'file' not in request.files:
            return response_error('没有上传文件', 400)
        
        file = request.files['file']
        if file.filename == '':
            return response_error('没有选择文件', 400)
        
        allowed_extensions = {'.mp4', '.mov', '.avi', '.mkv', '.jpg', '.jpeg', '.png', '.gif', '.webp'}
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in allowed_extensions:
            return response_error(f'不支持的文件格式: {ext}', 400)
        
        filename = f"{uuid.uuid4().hex}{ext}"
        filepath = os.path.join(UPLOAD_DIR, filename)
        file.save(filepath)
        
        rel_path = os.path.relpath(filepath, BASE_DIR).replace(os.sep, '/')
        
        return response_success({
            'url': f"/uploads/{rel_path.split('uploads/')[-1]}",
            'filename': file.filename,
            'path': rel_path
        })
        
    except Exception as e:
        logger.exception('上传素材失败')
        return response_error(f'上传失败：{e}', 500)


@money_printer_bp.route('/providers', methods=['GET'])
@login_required
def get_providers():
    """
    获取支持的 LLM 提供商列表
    
    返回:
        {
            "code": 200,
            "data": [
                {"id": "deepseek", "name": "DeepSeek", "requires_api_key": true},
                ...
            ]
        }
    """
    from utils.money_printer import get_llm_providers
    return response_success(get_llm_providers())


@money_printer_bp.route('/voices', methods=['GET'])
@login_required
def get_voices():
    """
    获取可用的 TTS 音色列表（阿里云 CosyVoice）
    
    参数:
        language: 语言（zh/en），默认 zh
        
    返回:
        {
            "code": 200,
            "data": [
                {"id": "longanyang", "name": "龙安洋"},
                ...
            ]
        }
    """
    from utils.dashscope_tts import list_voices_for_frontend
    
    voices = list_voices_for_frontend()
    return response_success(voices)


@money_printer_bp.route('/video-sources', methods=['GET'])
@login_required
def get_video_sources():
    """
    获取支持的视频素材来源
    
    返回:
        {
            "code": 200,
            "data": [
                {"id": "pexels", "name": "Pexels", "requires_api_key": true},
                ...
            ]
        }
    """
    from utils.money_printer import get_video_sources
    return response_success(get_video_sources())


@money_printer_bp.route('/script/generate', methods=['POST'])
@login_required
def generate_script():
    """
    生成视频脚本
    
    请求体:
        {
            "subject": "string",           # 必填，视频主题
            "language": "string",          # 可选，语言（zh-CN, en-US）
            "paragraph_number": int,       # 可选，段落数量，默认 1
            "llm_provider": "string",      # 可选，LLM 提供商
            "api_key": "string"            # 可选，API Key
        }
        
    返回:
        {
            "code": 200,
            "data": {
                "script": "string"
            }
        }
    """
    try:
        data = request.get_json(silent=True) or {}
        subject = (data.get('subject') or data.get('video_subject') or '').strip()
        language = (data.get('language') or data.get('video_language') or '').strip()
        paragraph_number = data.get('paragraph_number', 1)
        
        if not subject:
            return response_error('subject 不能为空', 400)
        
        try:
            paragraph_number = int(paragraph_number)
        except Exception:
            paragraph_number = 1
        
        # 使用与 AI 视频剪辑相同的文案生成逻辑
        from utils.ai import deepseek_generate_copies
        
        result = deepseek_generate_copies(
            theme=subject,
            keywords='',
            reference='',
            count=paragraph_number,
        )
        
        copies = result.get('copies', [])
        if copies:
            # 取第一条文案，合并 lines 为完整脚本
            first_copy = copies[0]
            lines = first_copy.get('lines', [])
            script = '\n\n'.join(lines) if lines else first_copy.get('title', '')
        else:
            # 如果没有生成文案，返回原始内容
            script = result.get('raw', '生成失败，请重试')
        
        return response_success({'script': script})
        
    except Exception as e:
        logger.exception('生成脚本失败')
        return response_error(f'生成脚本失败：{e}', 500)


@money_printer_bp.route('/terms/generate', methods=['POST'])
@login_required
def generate_terms():
    """
    生成视频搜索关键词
    
    请求体:
        {
            "subject": "string",           # 必填，视频主题
            "script": "string",            # 必填，视频脚本
            "amount": int,                 # 可选，关键词数量，默认 5
            "llm_provider": "string",      # 可选，LLM 提供商
            "api_key": "string"            # 可选，API Key
        }
        
    返回:
        {
            "code": 200,
            "data": {
                "terms": ["string", ...]
            }
        }
    """
    try:
        from utils.money_printer import generate_terms as _generate_terms
        
        data = request.get_json(silent=True) or {}
        subject = (data.get('subject') or data.get('video_subject') or '').strip()
        script = (data.get('script') or data.get('video_script') or '').strip()
        amount = data.get('amount', 5)
        keywords = (data.get('keywords') or data.get('video_keywords') or '').strip()
        llm_provider = (data.get('llm_provider') or 'deepseek').strip()
        # 强制使用后端 .env 的 DeepSeek API Key，忽略前端传入
        api_key = _get_deepseek_api_key()
        
        if not subject:
            return response_error('subject 不能为空', 400)
        if not script:
            return response_error('script 不能为空', 400)
        
        try:
            amount = int(amount)
        except Exception:
            amount = 5
        
        terms = _generate_terms(
            video_subject=subject,
            video_script=script,
            amount=amount,
            keywords=keywords,
            llm_provider=llm_provider,
            api_key=api_key,
        )
        
        return response_success({'terms': terms})
        
    except Exception as e:
        logger.exception('生成关键词失败')
        return response_error(f'生成关键词失败：{e}', 500)


@money_printer_bp.route('/script/analyze', methods=['POST'])
@login_required
def analyze_script():
    """
    分析脚本内容，提取关键内容并生成对应的搜索关键词
    
    请求体:
        {
            "script": "string",            # 必填，视频脚本
            "api_key": "string"            # 可选，API Key
        }
        
    返回:
        {
            "code": 200,
            "data": {
                "segments": [
                    {
                        "content": "string",
                        "search_terms": ["string", ...]
                    },
                    ...
                ]
            }
        }
    """
    try:
        from utils.money_printer.llm_service import analyze_script_content
        
        data = request.get_json(silent=True) or {}
        script = (data.get('script') or data.get('video_script') or '').strip()
        api_key = _get_deepseek_api_key()
        
        if not script:
            return response_error('script 不能为空', 400)
        
        segments = analyze_script_content(
            video_script=script,
            api_key=api_key
        )
        
        return response_success({'segments': segments})
        
    except Exception as e:
        logger.exception('分析脚本失败')
        return response_error(f'分析脚本失败：{e}', 500)


@money_printer_bp.route('/tts/synthesize', methods=['POST'])
@login_required
def tts_synthesize():
    """
    TTS 语音合成
    
    请求体:
        {
            "text": "string",              # 必填，要合成的文本
            "voice_name": "string",        # 可选，音色名称
            "voice_rate": float,           # 可选，语速，默认 1.0
            "voice_volume": float,         # 可选，音量，默认 1.0
            "provider": "string"           # 可选，TTS 提供商，默认 edge
        }
        
    返回:
        {
            "code": 200,
            "data": {
                "audio_url": "string",
                "duration": float
            }
        }
    """
    try:
        from utils.money_printer import tts, get_audio_duration
        
        data = request.get_json(silent=True) or {}
        text = (data.get('text') or '').strip()
        voice_name = (data.get('voice_name') or 'zh-CN-XiaoxiaoNeural-Female').strip()
        voice_rate = float(data.get('voice_rate', 1.0))
        voice_volume = float(data.get('voice_volume', 1.0))
        provider = (data.get('provider') or 'edge').strip()
        
        if not text:
            return response_error('text 不能为空', 400)
        
        BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        tts_dir = os.path.join(BASE_DIR, 'uploads', 'money_printer', 'tts')
        os.makedirs(tts_dir, exist_ok=True)
        
        audio_file = os.path.join(tts_dir, f"{uuid.uuid4().hex}.mp3")
        
        success = tts(
            text=text,
            voice_name=voice_name,
            voice_rate=voice_rate,
            voice_file=audio_file,
            voice_volume=voice_volume,
            provider=provider,
        )
        
        if not success:
            return response_error('语音合成失败', 500)
        
        duration = get_audio_duration(audio_file)
        
        rel_path = os.path.relpath(audio_file, BASE_DIR).replace(os.sep, '/')
        audio_url = f"/{rel_path}"
        
        return response_success({
            'audio_url': audio_url,
            'duration': duration,
            'path': audio_file
        })
        
    except Exception as e:
        logger.exception('TTS 合成失败')
        return response_error(f'TTS 合成失败：{e}', 500)


@money_printer_bp.route('/video/create', methods=['POST'])
@login_required
def create_video():
    """
    创建视频生成任务
    
    请求体:
        {
            "video_subject": "string",     # 必填，视频主题
            "video_script": "string",      # 可选，视频脚本（不提供则自动生成）
            "video_aspect": "string",      # 可选，视频比例，默认 9:16
            "voice_name": "string",        # 可选，音色名称
            "voice_rate": float,           # 可选，语速
            "subtitle_enabled": bool,      # 可选，是否启用字幕
            "video_source": "string",      # 可选，视频素材来源
            "llm_provider": "string",      # 可选，LLM 提供商
            "api_key": "string",           # 可选，API Key
            "pexels_api_key": "string",    # 可选，Pexels API Key
            "stop_at": "string"            # 可选，停止阶段
        }
        
    返回:
        {
            "code": 200,
            "data": {
                "task_id": "string"
            }
        }
    """
    try:
        from utils.money_printer import start_video_task, VideoParams
        
        data = request.get_json(silent=True) or {}
        
        video_subject = (data.get('video_subject') or '').strip()
        if not video_subject:
            return response_error('video_subject 不能为空', 400)
        
        params = VideoParams(
            video_subject=video_subject,
            video_script=data.get('video_script', ''),
            video_keywords=data.get('video_keywords', ''),
            video_terms=data.get('video_terms'),
            video_aspect=data.get('video_aspect', '9:16'),
            video_concat_mode=data.get('video_concat_mode', 'random'),
            video_transition_mode=data.get('video_transition_mode'),
            video_clip_duration=int(data.get('video_clip_duration', 5)),
            video_count=int(data.get('video_count', 1)),
            video_source=data.get('video_source', 'pexels'),
            video_materials=data.get('video_materials'),
            custom_audio_file=data.get('custom_audio_file'),
            video_language=data.get('video_language', ''),
            
            voice_name=data.get('voice_name', 'zh-CN-XiaoxiaoNeural-Female'),
            voice_volume=float(data.get('voice_volume', 1.0)),
            voice_rate=float(data.get('voice_rate', 1.0)),
            bgm_type=data.get('bgm_type', 'random'),
            bgm_file=data.get('bgm_file', ''),
            bgm_volume=float(data.get('bgm_volume', 0.2)),
            
            subtitle_enabled=data.get('subtitle_enabled', True),
            subtitle_position=data.get('subtitle_position', 'bottom'),
            custom_position=float(data.get('custom_position', 70.0)),
            font_name=data.get('font_name', 'STHeitiMedium.ttc'),
            text_fore_color=data.get('text_fore_color', '#FFFFFF'),
            # 默认透明背景：白字+描边，不加黑色底框
            text_background_color=data.get('text_background_color', ''),
            font_size=int(data.get('font_size', 60)),
            stroke_color=data.get('stroke_color', '#000000'),
            stroke_width=float(data.get('stroke_width', 1.5)),
            n_threads=int(data.get('n_threads', 2)),
            paragraph_number=int(data.get('paragraph_number', 1)),
            
            llm_provider=data.get('llm_provider', 'deepseek'),
            llm_api_key=_get_deepseek_api_key(),
            pexels_api_key=data.get('pexels_api_key') or _get_pexels_api_key(),
            pixabay_api_key=data.get('pixabay_api_key') or os.environ.get('PIXABAY_API_KEY', ''),
        )
        
        stop_at = data.get('stop_at', 'video')
        
        task = start_video_task(params=params, stop_at=stop_at)
        
        return response_success({
            'task_id': task.task_id,
            'state': task.state,
            'progress': task.progress,
            'script': task.script,
            'terms': task.terms,
            'audio_file': task.audio_file,
            'audio_duration': task.audio_duration,
            'subtitle_path': task.subtitle_path,
            'materials': task.materials,
            'videos': task.videos,
            'combined_videos': task.combined_videos,
            'error': task.error,
        })
        
    except Exception as e:
        logger.exception('创建视频任务失败')
        return response_error(f'创建视频任务失败：{e}', 500)


@money_printer_bp.route('/task/<task_id>', methods=['GET'])
@login_required
def get_task_status(task_id):
    """
    获取任务状态
    
    返回:
        {
            "code": 200,
            "data": {
                "task_id": "string",
                "state": "string",
                "progress": int,
                "videos": ["string", ...],
                ...
            }
        }
    """
    try:
        from utils.money_printer import get_task_status
        
        task = get_task_status(task_id)
        if not task:
            return response_error('任务不存在', 404)
        
        return response_success({
            'task_id': task.task_id,
            'state': task.state,
            'progress': task.progress,
            'script': task.script,
            'terms': task.terms,
            'audio_file': task.audio_file,
            'audio_duration': task.audio_duration,
            'subtitle_path': task.subtitle_path,
            'materials': task.materials,
            'videos': task.videos,
            'combined_videos': task.combined_videos,
            'error': task.error,
        })
        
    except Exception as e:
        logger.exception('获取任务状态失败')
        return response_error(f'获取任务状态失败：{e}', 500)


@money_printer_bp.route('/video/full', methods=['POST'])
@login_required
def create_full_video():
    """
    一键生成完整视频（同步接口）
    
    请求体:
        {
            "video_subject": "string",     # 必填，视频主题
            "video_script": "string",      # 可选，视频脚本
            "video_aspect": "string",      # 可选，视频比例
            "voice_name": "string",        # 可选，音色名称
            ...
        }
        
    返回:
        {
            "code": 200,
            "data": {
                "videos": ["string", ...],
                "script": "string",
                ...
            }
        }
    """
    try:
        from utils.money_printer import start_video_task, VideoParams
        
        data = request.get_json(silent=True) or {}
        
        video_subject = (data.get('video_subject') or '').strip()
        if not video_subject:
            return response_error('video_subject 不能为空', 400)
        
        params = VideoParams(
            video_subject=video_subject,
            video_script=data.get('video_script', ''),
            video_keywords=data.get('video_keywords', ''),
            video_terms=data.get('video_terms'),
            video_aspect=data.get('video_aspect', '9:16'),
            video_concat_mode=data.get('video_concat_mode', 'random'),
            video_transition_mode=data.get('video_transition_mode'),
            video_clip_duration=int(data.get('video_clip_duration', 5)),
            video_count=int(data.get('video_count', 1)),
            video_source=data.get('video_source', 'pexels'),
            video_materials=data.get('video_materials'),
            custom_audio_file=data.get('custom_audio_file'),
            video_language=data.get('video_language', ''),
            
            voice_name=data.get('voice_name', 'zh-CN-XiaoxiaoNeural-Female'),
            voice_volume=float(data.get('voice_volume', 1.0)),
            voice_rate=float(data.get('voice_rate', 1.0)),
            bgm_type=data.get('bgm_type', 'random'),
            bgm_file=data.get('bgm_file', ''),
            bgm_volume=float(data.get('bgm_volume', 0.2)),
            
            subtitle_enabled=data.get('subtitle_enabled', True),
            subtitle_position=data.get('subtitle_position', 'bottom'),
            custom_position=float(data.get('custom_position', 70.0)),
            font_name=data.get('font_name', 'STHeitiMedium.ttc'),
            text_fore_color=data.get('text_fore_color', '#FFFFFF'),
            # 默认透明背景：白字+描边，不加黑色底框
            text_background_color=data.get('text_background_color', ''),
            font_size=int(data.get('font_size', 60)),
            stroke_color=data.get('stroke_color', '#000000'),
            stroke_width=float(data.get('stroke_width', 1.5)),
            n_threads=int(data.get('n_threads', 2)),
            paragraph_number=int(data.get('paragraph_number', 1)),
            
            llm_provider=data.get('llm_provider', 'deepseek'),
            llm_api_key=_get_deepseek_api_key(),
            pexels_api_key=data.get('pexels_api_key') or _get_pexels_api_key(),
            pixabay_api_key=data.get('pixabay_api_key'),
        )
        
        logger.info(f"API Key from request: {data.get('api_key', 'N/A')[:10] if data.get('api_key') else 'N/A'}...")
        logger.info(f"DeepSeek API Key from env: {_get_deepseek_api_key()[:10] if _get_deepseek_api_key() else 'N/A'}...")
        logger.info(f"Final LLM API Key: {params.llm_api_key[:10] if params.llm_api_key else 'N/A'}...")
        
        task = start_video_task(params=params, stop_at='video')
        
        if task.state == 'failed':
            return response_error(task.error or '视频生成失败', 500)
        
        BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        outputs_dir = os.path.join(BASE_DIR, 'uploads', 'money_printer', 'outputs', task.task_id)
        os.makedirs(outputs_dir, exist_ok=True)
        
        video_urls = []
        for idx, video_path in enumerate(task.videos, 1):
            if not video_path or not os.path.exists(video_path):
                continue
            filename = os.path.basename(video_path) or f"final-{idx}.mp4"
            target_path = os.path.join(outputs_dir, filename)
            try:
                shutil.copy(video_path, target_path)
                rel_path = os.path.relpath(target_path, os.path.join(BASE_DIR, 'uploads')).replace(os.sep, '/')
                video_urls.append(f"/uploads/{rel_path}")
            except Exception as e:
                logger.exception(f"复制视频到 uploads 失败: {e}")
        
        return response_success({
            'task_id': task.task_id,
            'state': task.state,
            'progress': task.progress,
            'script': task.script,
            'terms': task.terms,
            'audio_file': task.audio_file,
            'audio_duration': task.audio_duration,
            'subtitle_path': task.subtitle_path,
            'videos': video_urls,
            'video_paths': task.videos,
            'combined_videos': task.combined_videos,
        })
        
    except Exception as e:
        logger.exception('生成视频失败')
        return response_error(f'生成视频失败：{e}', 500)
