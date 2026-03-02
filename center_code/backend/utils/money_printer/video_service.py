"""
视频合成服务
集成 MoneyPrinterTurbo 的视频合成功能
"""
import os
import logging
import random
import glob
import gc
import shutil
import re
from typing import List, Optional

MONEY_PRINTER_DIR = r"D:\short term\money\MoneyPrinterTurbo"

logger = logging.getLogger(__name__)

audio_codec = "aac"
video_codec = "libx264"
fps = 30


def _parse_srt_items(subtitle_path: str) -> List[tuple]:
    """
    Parse SRT into [(start_sec, end_sec, text), ...].
    Be tolerant to missing trailing blank line and multiline subtitle text.
    """
    if not subtitle_path or not os.path.exists(subtitle_path):
        return []

    with open(subtitle_path, "r", encoding="utf-8") as f:
        content = f.read()

    if not content.strip():
        return []

    blocks = re.split(r"\r?\n\r?\n+", content.strip())
    items: List[tuple] = []

    def _to_seconds(ts: str) -> float:
        hh, mm, rest = ts.split(":")
        ss, ms = rest.split(",")
        return int(hh) * 3600 + int(mm) * 60 + int(ss) + int(ms) / 1000.0

    for block in blocks:
        lines = [ln.rstrip("\r") for ln in block.splitlines() if ln.strip() != ""]
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
        text_lines = lines[time_idx + 1 :]
        text = "\n".join([x for x in text_lines if x]).strip()
        if not text:
            continue
        if end_sec <= start_sec:
            end_sec = start_sec + 0.35
        items.append((start_sec, end_sec, text))

    return items


class VideoAspect:
    """视频比例"""
    landscape = "16:9"
    portrait = "9:16"
    square = "1:1"
    
    def __init__(self, value: str = None):
        self.value = value or self.portrait
    
    def to_resolution(self):
        if self.value == self.landscape:
            return 1920, 1080
        elif self.value == self.portrait:
            return 1080, 1920
        elif self.value == self.square:
            return 1080, 1080
        return 1080, 1920


class VideoConcatMode:
    """视频拼接模式"""
    random = "random"
    sequential = "sequential"


class VideoTransitionMode:
    """视频转场模式"""
    none = None
    shuffle = "Shuffle"
    fade_in = "FadeIn"
    fade_out = "FadeOut"
    slide_in = "SlideIn"
    slide_out = "SlideOut"


class VideoParams:
    """视频参数"""
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
    """子剪辑视频片段"""
    def __init__(self, file_path, start_time=None, end_time=None, width=None, height=None, duration=None):
        self.file_path = file_path
        self.start_time = start_time
        self.end_time = end_time
        self.width = width
        self.height = height
        self.duration = duration if duration is not None else (end_time - start_time if end_time and start_time else 0)


def _close_clip(clip):
    """关闭视频剪辑，释放资源"""
    if clip is None:
        return
    
    try:
        if hasattr(clip, 'reader') and clip.reader is not None:
            clip.reader.close()
        
        if hasattr(clip, 'audio') and clip.audio is not None:
            if hasattr(clip.audio, 'reader') and clip.audio.reader is not None:
                clip.audio.reader.close()
            del clip.audio
        
        if hasattr(clip, 'mask') and clip.mask is not None:
            if hasattr(clip.mask, 'reader') and clip.mask.reader is not None:
                clip.mask.reader.close()
            del clip.mask
        
        if hasattr(clip, 'clips') and clip.clips:
            for child_clip in clip.clips:
                if child_clip is not clip:
                    _close_clip(child_clip)
        
        if hasattr(clip, 'clips'):
            clip.clips = []
            
    except Exception as e:
        logger.error(f"关闭剪辑失败: {str(e)}")
    
    del clip
    gc.collect()


def _delete_files(files: List[str]):
    """删除文件"""
    if isinstance(files, str):
        files = [files]
    
    for file in files:
        try:
            os.remove(file)
        except Exception:
            pass


def get_bgm_file(bgm_type: str = "random", bgm_file: str = "") -> str:
    """
    获取背景音乐文件
    
    Args:
        bgm_type: 背景音乐类型
        bgm_file: 指定的背景音乐文件
        
    Returns:
        背景音乐文件路径
    """
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
    """
    合并视频片段
    
    Args:
        combined_video_path: 输出视频路径
        video_paths: 视频片段路径列表
        audio_file: 音频文件路径
        video_aspect: 视频比例
        video_concat_mode: 拼接模式
        video_transition_mode: 转场模式
        max_clip_duration: 最大片段时长
        threads: 线程数
        
    Returns:
        输出视频路径
    """
    from moviepy import (
        AudioFileClip,
        ColorClip,
        CompositeVideoClip,
        VideoFileClip,
        concatenate_videoclips,
        vfx,
    )
    
    if video_aspect is None:
        video_aspect = VideoAspect()
    
    audio_clip = AudioFileClip(audio_file)
    audio_duration = audio_clip.duration
    _close_clip(audio_clip)
    
    logger.info(f"音频时长: {audio_duration} 秒")
    logger.info(f"最大片段时长: {max_clip_duration} 秒")
    
    output_dir = os.path.dirname(combined_video_path)
    aspect = VideoAspect(video_aspect.value if hasattr(video_aspect, 'value') else video_aspect)
    video_width, video_height = aspect.to_resolution()
    
    processed_clips = []
    subclipped_items = []
    video_duration = 0

    raw_transition_mode = (video_transition_mode or "").strip()
    transition_alias = {
        "fade": "fade",
        "fadein": "fade",
        "fadeout": "fade",
        "slide": "slide",
        "slidein": "slide",
        "slideout": "slide",
    }
    transition_mode = transition_alias.get(raw_transition_mode.lower(), "")
    
    for video_path in video_paths:
        try:
            clip = VideoFileClip(video_path)
            clip_duration = clip.duration
            clip_w, clip_h = clip.size
            _close_clip(clip)
            
            start_time = 0
            while start_time < clip_duration:
                end_time = min(start_time + max_clip_duration, clip_duration)
                if clip_duration - start_time >= max_clip_duration:
                    subclipped_items.append(SubClippedVideoClip(
                        file_path=video_path,
                        start_time=start_time,
                        end_time=end_time,
                        width=clip_w,
                        height=clip_h
                    ))
                start_time = end_time
                if video_concat_mode == VideoConcatMode.sequential:
                    break
        except Exception as e:
            logger.error(f"处理视频失败 {video_path}: {str(e)}")
    
    if video_concat_mode == VideoConcatMode.random:
        random.shuffle(subclipped_items)
    
    logger.info(f"共 {len(subclipped_items)} 个片段")
    
    for i, subclipped_item in enumerate(subclipped_items):
        if video_duration > audio_duration:
            break
        
        try:
            clip = VideoFileClip(subclipped_item.file_path).subclipped(
                subclipped_item.start_time, subclipped_item.end_time
            )
            clip_duration = clip.duration
            clip_w, clip_h = clip.size
            
            if clip_w != video_width or clip_h != video_height:
                clip_ratio = clip_w / clip_h
                video_ratio = video_width / video_height
                
                if clip_ratio == video_ratio:
                    clip = clip.resized(new_size=(video_width, video_height))
                else:
                    if clip_ratio > video_ratio:
                        scale_factor = video_width / clip_w
                    else:
                        scale_factor = video_height / clip_h
                    
                    new_width = int(clip_w * scale_factor)
                    new_height = int(clip_h * scale_factor)
                    
                    background = ColorClip(size=(video_width, video_height), color=(0, 0, 0)).with_duration(clip_duration)
                    clip_resized = clip.resized(new_size=(new_width, new_height)).with_position("center")
                    clip = CompositeVideoClip([background, clip_resized])
            
            if clip.duration > max_clip_duration:
                clip = clip.subclipped(0, max_clip_duration)
            
            clip_file = os.path.join(output_dir, f"temp-clip-{i+1}.mp4")
            clip.write_videofile(clip_file, logger=None, fps=fps, codec=video_codec)
            
            _close_clip(clip)
            
            processed_clips.append(SubClippedVideoClip(
                file_path=clip_file,
                duration=clip_duration,
                width=clip_w,
                height=clip_h
            ))
            video_duration += clip_duration
            
        except Exception as e:
            logger.error(f"处理片段失败: {str(e)}")
    
    if video_duration < audio_duration:
        logger.warning(f"???? ({video_duration:.2f}s) ?????? ({audio_duration:.2f}s)?????")
        base_clips = processed_clips.copy()
        if base_clips:
            while video_duration < audio_duration:
                for clip in base_clips:
                    if video_duration >= audio_duration:
                        break
                    processed_clips.append(clip)
                    video_duration += clip.duration

    if not processed_clips:
        logger.warning("没有可用片段")
        return ""
    
    if len(processed_clips) == 1:
        shutil.copy(processed_clips[0].file_path, combined_video_path)
        _delete_files([c.file_path for c in processed_clips])
        return combined_video_path
    
    temp_merged_video = os.path.join(output_dir, "temp-merged-video.mp4")
    temp_merged_next = os.path.join(output_dir, "temp-merged-next.mp4")
    
    shutil.copy(processed_clips[0].file_path, temp_merged_video)
    
    for i, clip in enumerate(processed_clips[1:], 1):
        logger.info(f"合并片段 {i}/{len(processed_clips)-1}")
        
        try:
            base_clip = VideoFileClip(temp_merged_video)
            next_clip = VideoFileClip(clip.file_path)
            
            # Keep transition short and adaptive so it works for short clips as well.
            transition_dur = min(
                0.35,
                max(0.08, float(base_clip.duration or 0.0) * 0.2),
                max(0.08, float(next_clip.duration or 0.0) * 0.2),
            )

            if transition_mode == "fade":
                base_fade = base_clip.with_effects([vfx.FadeOut(transition_dur)])
                next_fade = next_clip.with_effects([vfx.FadeIn(transition_dur)])
                merged_clip = concatenate_videoclips(
                    [base_fade, next_fade],
                    method="compose",
                    padding=-transition_dur,
                )
            elif transition_mode == "slide":
                slide_start = max(0.0, float(base_clip.duration or 0.0) - transition_dur)
                base_slide = base_clip.with_position(
                    lambda t, _s=slide_start, _d=transition_dur, _w=video_width: (
                        -int(_w * min(max((t - _s) / _d, 0.0), 1.0)),
                        "center",
                    )
                )
                next_slide = next_clip.with_start(slide_start).with_position(
                    lambda t, _d=transition_dur, _w=video_width: (
                        int(_w * (1.0 - min(max(t / _d, 0.0), 1.0))),
                        "center",
                    )
                )
                merged_clip = CompositeVideoClip(
                    [base_slide, next_slide],
                    size=(video_width, video_height),
                ).with_duration(float(base_clip.duration or 0.0) + float(next_clip.duration or 0.0) - transition_dur)
            else:
                merged_clip = concatenate_videoclips([base_clip, next_clip])
            
            merged_clip.write_videofile(
                filename=temp_merged_next,
                threads=threads,
                logger=None,
                temp_audiofile_path=output_dir,
                audio_codec=audio_codec,
                fps=fps,
            )
            
            _close_clip(base_clip)
            _close_clip(next_clip)
            _close_clip(merged_clip)
            
            _delete_files(temp_merged_video)
            os.rename(temp_merged_next, temp_merged_video)
            
        except Exception as e:
            logger.error(f"合并片段失败: {str(e)}")
            continue
    
    os.rename(temp_merged_video, combined_video_path)
    _delete_files([c.file_path for c in processed_clips])
    
    logger.info("视频合并完成")
    return combined_video_path


def wrap_text(text: str, max_width: int, font: str = "Arial", fontsize: int = 60) -> tuple:
    """文本换行"""
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
    
    result = "\n".join(lines)
    return result, len(lines) * height


def generate_video(
    video_path: str,
    audio_path: str,
    subtitle_path: str,
    output_file: str,
    params: VideoParams = None,
) -> str:
    """
    生成最终视频
    
    Args:
        video_path: 合并后的视频路径
        audio_path: 音频路径
        subtitle_path: 字幕路径
        output_file: 输出文件路径
        params: 视频参数
        
    Returns:
        输出文件路径
    """
    from moviepy import (
        AudioFileClip,
        CompositeAudioClip,
        CompositeVideoClip,
        TextClip,
        VideoFileClip,
        afx,
    )
    
    if params is None:
        params = VideoParams()

    if not video_path or not os.path.exists(video_path):
        logger.error(f"视频文件不存在: {video_path}")
        return ""
    if not audio_path or not os.path.exists(audio_path):
        logger.error(f"音频文件不存在: {audio_path}")
        return ""
    
    aspect = VideoAspect(params.video_aspect)
    video_width, video_height = aspect.to_resolution()
    
    logger.info(f"生成视频: {video_width} x {video_height}")
    logger.info(f"  视频: {video_path}")
    logger.info(f"  音频: {audio_path}")
    logger.info(f"  字幕: {subtitle_path}")
    logger.info(f"  输出: {output_file}")
    
    output_dir = os.path.dirname(output_file)
    
    font_path = ""
    if params.subtitle_enabled and subtitle_path:
        font_dir = os.path.join(MONEY_PRINTER_DIR, "resource", "fonts")
        font_path = os.path.join(font_dir, params.font_name)
        if not os.path.exists(font_path):
            font_path = params.font_name
        logger.info(f"  字体: {font_path}")
    
    def create_text_clip(subtitle_item):
        phrase = subtitle_item[1]
        max_width = video_width * 0.9
        wrapped_txt, txt_height = wrap_text(phrase, max_width, font_path, params.font_size)
        
        start_time = subtitle_item[0][0]
        end_time = subtitle_item[0][1]
        duration = end_time - start_time
        
        _clip = TextClip(
            text=wrapped_txt,
            font=font_path,
            font_size=params.font_size,
            color=params.text_fore_color,
            bg_color=params.text_background_color if params.text_background_color else None,
            stroke_color=params.stroke_color,
            stroke_width=max(0.0, float(params.stroke_width)),
            duration=duration,
        )
        
        _clip = _clip.with_start(start_time)
        
        if params.subtitle_position == "bottom":
            _clip = _clip.with_position(("center", video_height * 0.95 - _clip.h))
        elif params.subtitle_position == "top":
            _clip = _clip.with_position(("center", video_height * 0.05))
        elif params.subtitle_position == "custom":
            margin = 10
            max_y = video_height - _clip.h - margin
            min_y = margin
            custom_y = (video_height - _clip.h) * (params.custom_position / 100)
            custom_y = max(min_y, min(custom_y, max_y))
            _clip = _clip.with_position(("center", custom_y))
        else:
            _clip = _clip.with_position(("center", "center"))
        
        return _clip
    
    video_clip = VideoFileClip(video_path).without_audio()
    audio_clip = AudioFileClip(audio_path).with_effects(
        [afx.MultiplyVolume(params.voice_volume)]
    )

    if subtitle_path and os.path.exists(subtitle_path) and params.subtitle_enabled:
        text_clips = []
        subtitle_items = _parse_srt_items(subtitle_path)
        video_dur = float(video_clip.duration or 0.0)
        min_dur = 0.2
        for start_sec, end_sec, phrase in subtitle_items:
            # Protect tail subtitles: if cue start drifts slightly beyond clip end,
            # clamp it back so the last line is still visible.
            start_sec = max(0.0, float(start_sec))
            end_sec = max(start_sec + min_dur, float(end_sec))
            if video_dur > 0:
                if start_sec >= video_dur:
                    start_sec = max(0.0, video_dur - min_dur)
                end_sec = min(video_dur, max(end_sec, start_sec + min_dur))
                if end_sec <= start_sec:
                    continue
            clip = create_text_clip(((start_sec, end_sec), phrase))
            text_clips.append(clip)
        if text_clips:
            video_clip = CompositeVideoClip([video_clip, *text_clips])
    
    bgm_file = get_bgm_file(params.bgm_type, params.bgm_file)
    if bgm_file:
        try:
            bgm_clip = AudioFileClip(bgm_file).with_effects([
                afx.MultiplyVolume(params.bgm_volume),
                afx.AudioFadeOut(3),
                afx.AudioLoop(duration=video_clip.duration),
            ])
            audio_clip = CompositeAudioClip([audio_clip, bgm_clip])
        except Exception as e:
            logger.error(f"添加背景音乐失败: {str(e)}")
    
    video_clip = video_clip.with_audio(audio_clip)
    video_clip.write_videofile(
        output_file,
        audio_codec=audio_codec,
        temp_audiofile_path=output_dir,
        threads=params.n_threads,
        logger=None,
        fps=fps,
    )
    
    _close_clip(video_clip)
    
    return output_file


if __name__ == "__main__":
    print("视频合成服务已加载")
