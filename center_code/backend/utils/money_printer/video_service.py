"""
Video composition service for MoneyPrinter-like workflow.
Optimized for local materials: fewer intermediate transcodes.
"""
import gc
import glob
import logging
import os
import random
import re
import shutil
import subprocess
from typing import List

MONEY_PRINTER_DIR = r"D:\short term\money\MoneyPrinterTurbo"

logger = logging.getLogger(__name__)

audio_codec = "aac"
video_codec = "libx264"
fps = 24
video_preset = "veryfast"
video_crf = "28"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}


def _is_image_file(path: str) -> bool:
    return os.path.splitext((path or "").lower())[1] in IMAGE_EXTENSIONS


def _resolve_ffmpeg() -> str:
    ffmpeg_bin = os.environ.get("FFMPEG_PATH", "").strip()
    if ffmpeg_bin and os.path.exists(ffmpeg_bin):
        return ffmpeg_bin
    which = shutil.which("ffmpeg")
    return which or "ffmpeg"


def _auto_standardize_video(src_path: str, width: int, height: int, out_fps: int) -> str:
    """
    Secondary fallback normalization:
    if upload-time normalization failed, try again before composition.
    """
    if _is_image_file(src_path):
        return src_path
    if not src_path or not os.path.exists(src_path):
        return src_path
    if src_path.lower().endswith("_norm.mp4"):
        return src_path

    root, _ = os.path.splitext(src_path)
    norm_path = f"{root}_norm.mp4"
    if os.path.exists(norm_path):
        return norm_path

    ffmpeg_bin = _resolve_ffmpeg()
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,fps={out_fps},format=yuv420p"
    )
    cmd = [
        ffmpeg_bin,
        "-y",
        "-i",
        src_path,
        "-vf",
        vf,
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        norm_path,
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return norm_path
    except Exception as e:
        logger.warning(f"二次自动标准化失败，回退原素材: {src_path}, {e}")
        return src_path


def _parse_srt_items(subtitle_path: str) -> List[tuple]:
    if not subtitle_path or not os.path.exists(subtitle_path):
        return []
    with open(subtitle_path, "r", encoding="utf-8") as f:
        content = f.read()
    if not content.strip():
        return []

    blocks = re.split(r"\r?\n\r?\n+", content.strip())
    items = []

    def _to_seconds(ts: str) -> float:
        hh, mm, rest = ts.split(":")
        ss, ms = rest.split(",")
        return int(hh) * 3600 + int(mm) * 60 + int(ss) + int(ms) / 1000.0

    for block in blocks:
        lines = [ln.rstrip("\r") for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        time_idx = 1 if len(lines) >= 2 and "-->" in lines[1] else 0
        if "-->" not in lines[time_idx]:
            continue
        try:
            start_txt, end_txt = [x.strip() for x in lines[time_idx].split("-->", 1)]
            start_sec = _to_seconds(start_txt)
            end_sec = _to_seconds(end_txt)
        except Exception:
            continue
        text = "\n".join(lines[time_idx + 1 :]).strip()
        if not text:
            continue
        if end_sec <= start_sec:
            end_sec = start_sec + 0.35
        items.append((start_sec, end_sec, text))
    return items


class VideoAspect:
    landscape = "16:9"
    portrait = "9:16"
    square = "1:1"

    def __init__(self, value: str = None):
        self.value = value or self.portrait

    def to_resolution(self):
        if self.value == self.landscape:
            return 1280, 720
        if self.value == self.square:
            return 720, 720
        return 720, 1280


class VideoConcatMode:
    random = "random"
    sequential = "sequential"


class VideoTransitionMode:
    none = None
    shuffle = "Shuffle"
    fade_in = "FadeIn"
    fade_out = "FadeOut"
    slide_in = "SlideIn"
    slide_out = "SlideOut"


class VideoParams:
    def __init__(
        self,
        video_aspect: str = "9:16",
        video_concat_mode: str = "random",
        video_transition_mode: str = None,
        video_clip_duration: int = 5,
        voice_volume: float = 1.0,
        bgm_type: str = "random",
        bgm_file: str = "",
        bgm_volume: float = 0.2,
        subtitle_enabled: bool = True,
        subtitle_position: str = "bottom",
        custom_position: float = 70.0,
        font_name: str = "STHeitiMedium.ttc",
        text_fore_color: str = "#FFFFFF",
        text_background_color: str = "",
        font_size: int = 60,
        stroke_color: str = "#000000",
        stroke_width: float = 0.0,
        n_threads: int = 2,
    ):
        self.video_aspect = video_aspect
        self.video_concat_mode = video_concat_mode
        self.video_transition_mode = video_transition_mode
        self.video_clip_duration = video_clip_duration
        self.voice_volume = voice_volume
        self.bgm_type = bgm_type
        self.bgm_file = bgm_file
        self.bgm_volume = bgm_volume
        self.subtitle_enabled = subtitle_enabled
        self.subtitle_position = subtitle_position
        self.custom_position = custom_position
        self.font_name = font_name
        self.text_fore_color = text_fore_color
        self.text_background_color = text_background_color
        self.font_size = font_size
        self.stroke_color = stroke_color
        self.stroke_width = stroke_width
        self.n_threads = n_threads


class SubClippedVideoClip:
    def __init__(self, file_path, start_time=None, end_time=None, width=None, height=None, duration=None):
        self.file_path = file_path
        self.start_time = start_time
        self.end_time = end_time
        self.width = width
        self.height = height
        self.duration = duration if duration is not None else (end_time - start_time if end_time and start_time else 0)


def _close_clip(clip):
    if clip is None:
        return
    try:
        if hasattr(clip, "reader") and clip.reader is not None:
            clip.reader.close()
        if hasattr(clip, "audio") and clip.audio is not None:
            if hasattr(clip.audio, "reader") and clip.audio.reader is not None:
                clip.audio.reader.close()
            del clip.audio
        if hasattr(clip, "mask") and clip.mask is not None:
            if hasattr(clip.mask, "reader") and clip.mask.reader is not None:
                clip.mask.reader.close()
            del clip.mask
    except Exception:
        pass
    del clip
    gc.collect()


def get_bgm_file(bgm_type: str = "random", bgm_file: str = "") -> str:
    if not bgm_type:
        return ""
    if bgm_file and os.path.exists(bgm_file):
        return bgm_file
    if bgm_type == "random":
        songs_dir = os.path.join(os.path.dirname(__file__), "songs")
        if not os.path.exists(songs_dir):
            songs_dir = os.path.join(MONEY_PRINTER_DIR, "resource", "songs")
        if os.path.exists(songs_dir):
            files = glob.glob(os.path.join(songs_dir, "*.mp3"))
            if files:
                return random.choice(files)
    return ""


def combine_videos(
    combined_video_path: str,
    video_paths: List[str],
    audio_file: str,
    video_aspect: VideoAspect = None,
    video_concat_mode: str = "random",
    video_transition_mode: str = None,
    max_clip_duration: int = 5,
    threads: int = 2,
) -> str:
    from moviepy import AudioFileClip, ColorClip, CompositeVideoClip, ImageClip, VideoFileClip, concatenate_videoclips

    if video_aspect is None:
        video_aspect = VideoAspect()

    aspect = VideoAspect(video_aspect.value if hasattr(video_aspect, "value") else video_aspect)
    video_width, video_height = aspect.to_resolution()
    output_dir = os.path.dirname(combined_video_path)

    audio_duration = 0.0
    try:
        a = AudioFileClip(audio_file)
        audio_duration = float(a.duration or 0.0)
        _close_clip(a)
    except Exception:
        pass

    segs: List[SubClippedVideoClip] = []
    normalized_cache = {}
    for src in video_paths:
        try:
            if _is_image_file(src):
                segs.append(SubClippedVideoClip(src, 0.0, float(max_clip_duration), video_width, video_height, float(max_clip_duration)))
                continue

            norm_src = normalized_cache.get(src)
            if not norm_src:
                norm_src = _auto_standardize_video(src, video_width, video_height, fps)
                normalized_cache[src] = norm_src

            c = VideoFileClip(norm_src)
            src_duration = float(c.duration or 0.0)
            w, h = c.size
            _close_clip(c)

            start = 0.0
            while start < src_duration:
                end = min(start + float(max_clip_duration), src_duration)
                if end - start > 0.1:
                    segs.append(SubClippedVideoClip(norm_src, start, end, w, h, end - start))
                start = end
                if video_concat_mode == VideoConcatMode.sequential:
                    break
        except Exception as e:
            logger.error(f"处理素材失败 {src}: {e}")

    if video_concat_mode == VideoConcatMode.random:
        random.shuffle(segs)

    clips = []
    total = 0.0
    for seg in segs:
        if audio_duration > 0 and total >= audio_duration:
            break
        try:
            if _is_image_file(seg.file_path):
                clip = ImageClip(seg.file_path, duration=float(seg.duration or max_clip_duration or 5))
            else:
                clip = VideoFileClip(seg.file_path).subclipped(seg.start_time, seg.end_time)

            d = float(clip.duration or 0.0)
            w, h = clip.size
            if w != video_width or h != video_height:
                src_ratio = w / h
                dst_ratio = video_width / video_height
                if src_ratio == dst_ratio:
                    clip = clip.resized(new_size=(video_width, video_height))
                else:
                    scale = (video_width / w) if src_ratio > dst_ratio else (video_height / h)
                    nw, nh = int(w * scale), int(h * scale)
                    bg = ColorClip(size=(video_width, video_height), color=(0, 0, 0)).with_duration(d)
                    fg = clip.resized(new_size=(nw, nh)).with_position("center")
                    clip = CompositeVideoClip([bg, fg]).with_duration(d)

            clips.append(clip)
            total += float(clip.duration or 0.0)
        except Exception as e:
            logger.error(f"处理片段失败: {e}")

    if not clips:
        return ""

    if audio_duration > 0 and total < audio_duration:
        base_len = len(clips)
        i = 0
        while total < audio_duration and base_len > 0 and i < 2000:
            dup = clips[i % base_len].copy()
            clips.append(dup)
            total += float(dup.duration or 0.0)
            i += 1

    final_clip = None
    try:
        final_clip = concatenate_videoclips(clips, method="compose")
        final_clip.write_videofile(
            combined_video_path,
            threads=threads,
            logger=None,
            temp_audiofile_path=output_dir,
            audio=False,
            codec=video_codec,
            fps=fps,
            preset=video_preset,
            ffmpeg_params=["-crf", video_crf],
        )
    finally:
        if final_clip is not None:
            _close_clip(final_clip)
        for c in clips:
            _close_clip(c)

    return combined_video_path


def wrap_text(text: str, max_width: int, font: str = "Arial", fontsize: int = 60) -> tuple:
    try:
        from PIL import ImageFont

        font_obj = ImageFont.truetype(font, fontsize)
    except Exception:
        return text, fontsize

    def get_text_size(inner_text):
        left, top, right, bottom = font_obj.getbbox(inner_text.strip())
        return right - left, bottom - top

    width, height = get_text_size(text)
    if width <= max_width:
        return text, height

    words = text.split(" ")
    lines = []
    current_line = ""
    for word in words:
        test_line = current_line + f"{word} "
        test_width, _ = get_text_size(test_line)
        if test_width <= max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line.strip())
            current_line = f"{word} "
    if current_line:
        lines.append(current_line.strip())

    return "\n".join(lines), len(lines) * height


def generate_video(
    video_path: str,
    audio_path: str,
    subtitle_path: str,
    output_file: str,
    params: VideoParams = None,
) -> str:
    from moviepy import AudioFileClip, CompositeAudioClip, CompositeVideoClip, TextClip, VideoFileClip, afx

    if params is None:
        params = VideoParams()
    if not video_path or not os.path.exists(video_path):
        logger.error(f"video not found: {video_path}")
        return ""
    if not audio_path or not os.path.exists(audio_path):
        logger.error(f"audio not found: {audio_path}")
        return ""

    aspect = VideoAspect(params.video_aspect)
    video_width, video_height = aspect.to_resolution()
    output_dir = os.path.dirname(output_file)

    font_path = params.font_name
    if params.subtitle_enabled and subtitle_path:
        font_dir = os.path.join(MONEY_PRINTER_DIR, "resource", "fonts")
        candidate = os.path.join(font_dir, params.font_name)
        if os.path.exists(candidate):
            font_path = candidate

    def create_text_clip(subtitle_item):
        phrase = subtitle_item[1]
        wrapped_txt, _ = wrap_text(phrase, video_width * 0.9, font_path, params.font_size)
        start_time = subtitle_item[0][0]
        end_time = subtitle_item[0][1]
        duration = end_time - start_time
        clip = TextClip(
            text=wrapped_txt,
            font=font_path,
            font_size=params.font_size,
            color=params.text_fore_color,
            bg_color=params.text_background_color if params.text_background_color else None,
            stroke_color=params.stroke_color,
            stroke_width=max(0, int(round(float(params.stroke_width)))),
            duration=duration,
        ).with_start(start_time)

        if params.subtitle_position == "bottom":
            return clip.with_position(("center", video_height * 0.95 - clip.h))
        if params.subtitle_position == "top":
            return clip.with_position(("center", video_height * 0.05))
        if params.subtitle_position == "custom":
            margin = 10
            max_y = video_height - clip.h - margin
            min_y = margin
            custom_y = (video_height - clip.h) * (params.custom_position / 100)
            custom_y = max(min_y, min(custom_y, max_y))
            return clip.with_position(("center", custom_y))
        return clip.with_position(("center", "center"))

    video_clip = VideoFileClip(video_path).without_audio()
    audio_clip = AudioFileClip(audio_path).with_effects([afx.MultiplyVolume(params.voice_volume)])

    if subtitle_path and os.path.exists(subtitle_path) and params.subtitle_enabled:
        text_clips = []
        subtitle_items = _parse_srt_items(subtitle_path)
        video_dur = float(video_clip.duration or 0.0)
        min_dur = 0.2
        for start_sec, end_sec, phrase in subtitle_items:
            start_sec = max(0.0, float(start_sec))
            end_sec = max(start_sec + min_dur, float(end_sec))
            if video_dur > 0:
                if start_sec >= video_dur:
                    start_sec = max(0.0, video_dur - min_dur)
                end_sec = min(video_dur, max(end_sec, start_sec + min_dur))
                if end_sec <= start_sec:
                    continue
            text_clips.append(create_text_clip(((start_sec, end_sec), phrase)))
        if text_clips:
            video_clip = CompositeVideoClip([video_clip, *text_clips])

    bgm_file = get_bgm_file(params.bgm_type, params.bgm_file)
    if bgm_file:
        try:
            bgm_clip = AudioFileClip(bgm_file).with_effects(
                [afx.MultiplyVolume(params.bgm_volume), afx.AudioFadeOut(3), afx.AudioLoop(duration=video_clip.duration)]
            )
            audio_clip = CompositeAudioClip([audio_clip, bgm_clip])
        except Exception as e:
            logger.error(f"add bgm failed: {e}")

    video_clip = video_clip.with_audio(audio_clip)
    video_clip.write_videofile(
        output_file,
        audio_codec=audio_codec,
        temp_audiofile_path=output_dir,
        threads=params.n_threads,
        logger=None,
        fps=fps,
        preset=video_preset,
        ffmpeg_params=["-crf", video_crf],
    )
    _close_clip(video_clip)
    return output_file


if __name__ == "__main__":
    print("video service loaded")
