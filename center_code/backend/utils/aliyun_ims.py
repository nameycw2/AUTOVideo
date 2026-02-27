import os
import json
import logging
import re
from alibabacloud_ice20201109.client import Client as IceClient
from alibabacloud_tea_openapi import models as open_api_models
from alibabacloud_ice20201109 import models as ice_models
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# ============================================================
# 1. 工具函数：将网页 #RRGGBB 转换为 阿里云 ICE 要求的 &H00BBGGRR
# ============================================================
def hex_to_ass_color(hex_str):
    """
    将 #RRGGBB 转换为 &H00BBGGRR (ASS BGR格式)
    """
    if not hex_str or not hex_str.startswith("#"): 
        return hex_str
    try:
        hex_val = hex_str.lstrip('#').upper()
        if len(hex_val) == 6:
            r, g, b = hex_val[0:2], hex_val[2:4], hex_val[4:6]
            # 顺序变为 BGR，前缀 &H00 (00代表不透明)
            return f"&H00{b}{g}{r}"
        return hex_str
    except Exception as e:
        print(f"⚠️ [COLOR ERROR] 颜色转换失败: {hex_str}, 错误: {e}")
        return hex_str

# ============================================================
# 2. 核心转换逻辑：将纯文本SRT转换为带Header样式的ASS (新增)
# ============================================================
def convert_srt_to_ass_content(srt_content, style_params):
    """
    将读取到的SRT内容转为带Style头的ASS内容，实现样式硬编码
    """
    font_name = style_params.get("FontName", "SimSun")
    font_size = style_params.get("FontSize", 60)
    primary_color = style_params.get("PrimaryColour", "&H00FFFFFF")
    outline_color = style_params.get("OutlineColour", "&H00000000")
    outline = style_params.get("Outline", 2)
    margin_v = style_params.get("MarginV", 160)

    # ASS 模板头部：定义设计稿
    ass_header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080

[v4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},{primary_color},&H000000FF,{outline_color},&H00000000,0,0,0,0,100,100,0,0,1,{outline},0,2,10,10,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ass_lines = []
    # 正则拆分 SRT 块
    srt_parts = re.split(r'\n\s*\n', srt_content.strip())
    for part in srt_parts:
        lines = part.split('\n')
        if len(lines) >= 3:
            # 匹配时间轴 00:00:01,000 --> 00:00:03,000
            time_match = re.search(r'(\d+:\d+:\d+),(\d+) --> (\d+:\d+:\d+),(\d+)', lines[1])
            if time_match:
                # 毫秒转厘秒并构造 ASS 时间戳
                start = f"{time_match.group(1)}.{time_match.group(2)[:2]}"
                end = f"{time_match.group(3)}.{time_match.group(4)[:2]}"
                # 调整为 h:mm:ss.cc 格式
                if start.startswith("00:"): start = start[1:]
                if end.startswith("00:"): end = end[1:]
                text = "\\N".join(lines[2:])
                ass_lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")

    return ass_header + "\n".join(ass_lines)

# ============================================================
# 3. 样式预设
# ============================================================
SUBTITLE_PRESETS = {
    "default": {"FontName": "SimSun", "FontSize": 60, "FontColor": "#FFFFFF", "Outline": 2, "OutlineColor": "#000000", "Y": 0.85},
    "variety": {"FontName": "SimSun", "FontSize": 80, "FontColor": "#FFD700", "Outline": 4, "OutlineColor": "#FF4500", "Y": 0.85},
    "movie": {"FontName": "SimSun", "FontSize": 40, "FontColor": "#F0F0F0", "Outline": 0, "OutlineColor": "#000000", "Y": 0.9}
}

ANIMATION_PRESETS = {
    "fade": {"InAnimation": "FadeIn", "OutAnimation": "FadeOut"},
    "none": {}
}

# ============================================================
# 4. 字幕效果构建类
# ============================================================
class SubtitleEffectBuilder:
    def __init__(self, subtitle_url, style_params):
        self.subtitle_url = subtitle_url
        self.params = style_params or {}

    def build_style(self):
        preset_name = self.params.get("subtitlePreset", "default")
        base = SUBTITLE_PRESETS.get(preset_name, SUBTITLE_PRESETS["default"])
        style = {}

        style["FontName"] = base.get("FontName", "SimSun")
        
        # --- [NEW] 字号映射控制 ---
        size_map = {
            "small": 48,
            "medium": 72,
            "large": 96
        }
        # 获取前端传来的字号枚举，默认为 medium
        size_key = self.params.get("subtitleFontSize", "medium")
        # 如果前端传来了为了兼容旧版的数字，尝试回退到默认
        if str(size_key).isdigit():
            val = int(size_key)
            style["FontSize"] = 48 if val < 60 else (96 if val > 80 else 72)
        else:
            style["FontSize"] = size_map.get(size_key, 72)
        
        # 颜色转换
        style["PrimaryColour"] = hex_to_ass_color(self.params.get("subtitleColor", base.get("FontColor", "#FFFFFF")))
        style["Outline"] = base.get("Outline", 2)
        style["OutlineColour"] = hex_to_ass_color(self.params.get("subtitleOutlineColor", base.get("OutlineColor", "#000000")))
        style["Alignment"] = 2  # 始终底部居中对齐

        # --- [NEW] 位置映射控制 (MarginV) ---
        # 1080p 画布高度
        CANVAS_HEIGHT = 1080
        # 预设 MarginV 值 (以底部为基准的垂直边距)
        # Top: 距离底部约 90% 的位置 -> Y=0.1
        # Middle: 距离底部 50% 的位置 -> Y=0.5
        # Bottom: 距离底部 15% 的位置 -> Y=0.85
        pos_map = {
            "top": int(CANVAS_HEIGHT * 0.85),     # 918px
            "middle": int(CANVAS_HEIGHT * 0.5),   # 540px
            "bottom": int(CANVAS_HEIGHT * 0.15)   # 162px (安全位)
        }
        pos_key = self.params.get("subtitleY", "bottom")
        
        # 兼容逻辑：如果传过来的是旧版浮点数字符串
        if str(pos_key).replace('.', '', 1).isdigit():
             y_val = float(pos_key)
             style["MarginV"] = int((1 - y_val) * CANVAS_HEIGHT)
        else:
            style["MarginV"] = pos_map.get(pos_key, 162)

        print(f"🎨 [FINAL-STYLE] 样式构建完成: {json.dumps(style, ensure_ascii=False)}")
        return style

    def build_clip(self):
        style_config = self.build_style()
        clip = {
            "Type": "Subtitle",
            "SubType": "Ass",      # ✅ 采用 Ass 格式以应用硬编码样式
            "FileUrl": self.subtitle_url,
            "SubtitleConfig": {
                "StyleConfig": style_config # 作为双重保险保留
            }
        }
        anim_name = self.params.get("subtitleAnimation", "none")
        if anim_name != "none":
            clip.update(ANIMATION_PRESETS.get(anim_name, {}))
        return clip

    def build_track(self):
        return {"SubtitleTrackClips": [self.build_clip()]}

# ============================================================
# 5. ICE 客户端与主提交函数
# ============================================================
def create_ice_client():
    ak = os.environ.get('IMS_ACCESS_KEY_ID')
    sk = os.environ.get('IMS_ACCESS_KEY_SECRET')
    region = os.environ.get('IMS_REGION_ID', 'cn-hangzhou')
    if not ak or not sk:
        logger.error("❌ IMS AccessKey 未配置")
        return None
    config = open_api_models.Config(access_key_id=ak, access_key_secret=sk)
    config.endpoint = f"ice.{region}.aliyuncs.com"
    return IceClient(config)

def build_subtitle_track(subtitle_url, style_params):
    if not subtitle_url: return None
    builder = SubtitleEffectBuilder(subtitle_url, style_params)
    return builder.build_track()

def submit_ims_task(video_url, subtitle_url, output_filename, subtitle_style=None, voice_url=None, bgm_url=None):
    """
    提交 IMS 剪辑任务 (最终稳健版)
    """
    print("\n🎬 [ICE-SUBMIT] 开始处理 IMS 提交...")
    client = create_ice_client()
    if not client: return {"success": False, "message": "Client 初始化失败"}

    # 音轨构造
    audio_tracks = []
    audio_tracks.append({"AudioTrackClips": [{"MediaUrl": video_url, "Volume": 0.4}]})
    if voice_url:
        print(f"🎙️ 插入配音轨道: {voice_url}")
        audio_tracks.append({"AudioTrackClips": [{"MediaUrl": voice_url, "Volume": 1.2}]})
    if bgm_url:
        print(f"🎵 插入 BGM 轨道: {bgm_url}")
        audio_tracks.append({"AudioTrackClips": [{"MediaUrl": bgm_url, "Volume": 0.2}]})

    # 先定义 timeline，再进行打印（修复原代码逻辑顺序错误）
    timeline = {
        "VideoTracks": [{"VideoTrackClips": [{"MediaUrl": video_url}]}],
        "AudioTracks": audio_tracks,
        "SubtitleTracks": []
    }

    if subtitle_url:
        sub_track = build_subtitle_track(subtitle_url, subtitle_style)
        if sub_track: timeline["SubtitleTracks"].append(sub_track)

    print("\n📦 [FINAL-TIMELINE] 发送至阿里的 JSON:")
    print(json.dumps(timeline, indent=2, ensure_ascii=False))

    bucket = os.environ.get('OSS_BUCKET_NAME')
    region = os.environ.get('IMS_REGION_ID', 'cn-hangzhou')
    output_url = f"https://{bucket}.oss-{region}.aliyuncs.com/output/{output_filename}"

    try:
        request = ice_models.SubmitMediaProducingJobRequest()
        request.timeline = json.dumps(timeline)
        request.output_media_config = json.dumps({"MediaURL": output_url})
        
        response = client.submit_media_producing_job(request)
        print(f"✅ JobID: {response.body.job_id}")
        return {"success": True, "job_id": response.body.job_id, "output_url": output_url}
    except Exception as e:
        print(f"❌ 阿里云提交失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return {"success": False, "message": str(e)}