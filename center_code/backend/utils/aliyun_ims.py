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
def convert_srt_to_ass_content(srt_content, style_params, main_title_text=None, main_title_config=None):
    """
    将读取到的SRT内容转为带Style头的ASS内容，实现样式硬编码。
    style_params 可含 PlayResX/PlayResY，用于适配成片分辨率（与视频大小一致）。
    """
    font_name = style_params.get("FontName", "SimSun")
    font_size = style_params.get("FontSize", 60)
    primary_color = style_params.get("PrimaryColour", "&H00FFFFFF")
    outline_color = style_params.get("OutlineColour", "&H00000000")
    outline = style_params.get("Outline", 2)
    margin_v = style_params.get("MarginV", 160)
    # 成片分辨率，与视频一致时字幕比例正确（默认 1080p 横屏）
    play_res_x = int(style_params.get("PlayResX", 1920))
    play_res_y = int(style_params.get("PlayResY", 1080))
    play_res_x = max(320, min(4096, play_res_x))
    play_res_y = max(320, min(4096, play_res_y))

    # 可选主标题样式（顶部常驻）
    top_title_style_line = ""
    top_title_text = (main_title_text or "").strip()
    top_title_cfg = main_title_config or {}
    if top_title_text:
        top_size_map = {"小": 48, "中": 72, "大": 96}
        top_size_key = str(top_title_cfg.get("font_size", "中"))
        top_size = top_size_map.get(top_size_key, 72)
        top_color = hex_to_ass_color(top_title_cfg.get("color", "#FFFFFF"))
        top_outline_color = hex_to_ass_color(top_title_cfg.get("stroke_color", "#000000"))
        # Alignment=8 顶部居中，MarginV 控制离顶部距离
        top_margin_v = max(12, round(play_res_y * 0.06))
        top_title_style_line = (
            f"Style: TopTitle,{font_name},{top_size},{top_color},&H000000FF,{top_outline_color},"
            f"&H00000000,1,0,0,0,100,100,0,0,1,3,0,8,10,10,{top_margin_v},1"
        )

    # ASS 模板头部：使用成片分辨率，字幕随视频大小适配
    ass_header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {play_res_x}
PlayResY: {play_res_y}

[v4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},{primary_color},&H000000FF,{outline_color},&H00000000,0,0,0,0,100,100,0,0,1,{outline},0,2,10,10,{margin_v},1
{top_title_style_line}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ass_lines = []
    first_start = None
    last_end = None

    def _escape_ass_text(text):
        return text.replace('\\', r'\\').replace('{', r'\{').replace('}', r'\}')

    # 正则拆分 SRT 块
    srt_parts = re.split(r'\n\s*\n', srt_content.strip())
    for part in srt_parts:
        lines = part.split('\n')
        if len(lines) >= 3:
            # 匹配时间轴 00:00:01,000 --> 00:00:03,000（毫秒可为 1~3 位）
            time_match = re.search(r'(\d+:\d+:\d+),(\d+) --> (\d+:\d+:\d+),(\d+)', lines[1])
            if time_match:
                def ms_to_centisec(ms_str):
                    ms_str = (ms_str or "0").strip()[:3].zfill(3)
                    return min(99, int(ms_str) // 10)
                cs_s = ms_to_centisec(time_match.group(2))
                cs_e = ms_to_centisec(time_match.group(4))
                start = f"{time_match.group(1)}.{cs_s:02d}"
                end = f"{time_match.group(3)}.{cs_e:02d}"
                # ASS 格式 H:MM:SS.cc，小时为 0 时可用单数字
                if start.startswith("00:"):
                    start = start[1:]
                if end.startswith("00:"):
                    end = end[1:]
                text = "\\N".join(_escape_ass_text(t) for t in lines[2:])
                if first_start is None:
                    first_start = start
                last_end = end
                ass_lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")

    # 增加顶部常驻主标题（覆盖字幕时间轴）
    if top_title_text and first_start and last_end:
        title_line = _escape_ass_text(top_title_text)
        ass_lines.insert(0, f"Dialogue: 0,{first_start},{last_end},TopTitle,,0,0,0,,{title_line}")

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
        
        # 成片分辨率（与视频一致时字幕随视频大小适配）
        play_res_x = self._int_param("video_width", 1080, 320, 4096)
        play_res_y = self._int_param("video_height", 1920, 320, 4096)
        style["PlayResX"] = play_res_x
        style["PlayResY"] = play_res_y
        # 以 1080 为参考，按比例缩放字号与边距（与本地 FFmpeg 思路一致）
        ref_height = 1080.0
        scale = min(play_res_x, play_res_y) / ref_height
        scale = max(0.3, min(3.0, scale))
        
        # --- 字号映射并随分辨率缩放 ---
        size_map = {"small": 48, "medium": 72, "large": 96}
        size_key = self.params.get("subtitleFontSize", "medium")
        if str(size_key).isdigit():
            val = int(size_key)
            base_font = 48 if val < 60 else (96 if val > 80 else 72)
        else:
            base_font = size_map.get(size_key, 72)
        style["FontSize"] = max(12, min(150, round(base_font * scale)))
        
        # 颜色转换
        style["PrimaryColour"] = hex_to_ass_color(self.params.get("subtitleColor", base.get("FontColor", "#FFFFFF")))
        style["Outline"] = base.get("Outline", 2)
        style["OutlineColour"] = hex_to_ass_color(self.params.get("subtitleOutlineColor", base.get("OutlineColor", "#000000")))
        style["Alignment"] = 2

        # --- MarginV 按成片高度比例缩放（保持相对位置）---
        pos_map_ref = {"top": 0.85, "middle": 0.5, "bottom": 0.15}
        pos_key = self.params.get("subtitleY", "bottom")
        if str(pos_key).replace('.', '', 1).isdigit():
            y_ratio = float(pos_key)
            margin_v_ref = (1 - y_ratio) * ref_height
        else:
            margin_v_ref = pos_map_ref.get(pos_key, 0.15) * ref_height
        style["MarginV"] = max(10, round(margin_v_ref * play_res_y / ref_height))

        logger.info("ASS 样式(随分辨率适配): PlayRes=%dx%d FontSize=%s MarginV=%s",
                    play_res_x, play_res_y, style["FontSize"], style["MarginV"])
        return style

    def _int_param(self, key, default, lo, hi):
        try:
            v = self.params.get(key)
            if v is None:
                return default
            n = int(v)
            return max(lo, min(hi, n))
        except (TypeError, ValueError):
            return default

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

def build_subtitle_track(subtitle_url, style_params, subtitle_render_mode='effect'):
    if not subtitle_url:
        return None
    if subtitle_render_mode == 'plain':
        # 原有逻辑：只传 SRT，ICE 支持 SubType="srt"
        return {"SubtitleTrackClips": [{"Type": "Subtitle", "SubType": "srt", "FileUrl": subtitle_url}]}
    builder = SubtitleEffectBuilder(subtitle_url, style_params)
    return builder.build_track()

def submit_ims_task(video_url, subtitle_url, output_filename, subtitle_style=None, subtitle_render_mode='effect', voice_url=None, bgm_url=None, main_title_text=None, main_title_config=None):
    """
    提交 IMS 剪辑任务。
    subtitle_render_mode: 'effect' 使用 ASS 字幕特效，'plain' 使用仅 SRT 外挂字幕。
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
        sub_track = build_subtitle_track(subtitle_url, subtitle_style, subtitle_render_mode)
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