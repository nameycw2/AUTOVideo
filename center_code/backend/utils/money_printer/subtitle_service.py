"""
字幕生成服务
集成 MoneyPrinterTurbo 的字幕功能
"""
import os
import logging
import re
from typing import List, Optional

MONEY_PRINTER_DIR = r"D:\short term\money\MoneyPrinterTurbo"

logger = logging.getLogger(__name__)

_model = None


def create_subtitle_whisper(
    audio_file: str,
    subtitle_file: str = "",
    model_size: str = "medium",
    device: str = "cpu",
    compute_type: str = "int8",
) -> str:
    """
    Use Whisper to generate subtitles.
    """
    global _model

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        logger.warning("faster_whisper not installed, skip Whisper subtitle")
        return ""

    if not subtitle_file:
        subtitle_file = f"{audio_file}.srt"

    os.environ["HF_HUB_DISABLE_XET"] = "1"
    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    # Optional HF mirror endpoint
    hf_endpoint = os.getenv("HF_ENDPOINT")
    if hf_endpoint:
        os.environ["HF_ENDPOINT"] = hf_endpoint

    # Prefer local base model if present (offline)
    local_root = r"D:\short term\v"
    local_candidates = [
        os.path.join(local_root, "guillaumeklnfaster-whisper-base"),
        os.path.join(local_root, "whisper-base"),
        os.path.join(local_root, "faster-whisper-base"),
        os.path.join(local_root, "base"),
    ]
    local_model_path = ""
    for c in local_candidates:
        if os.path.isfile(os.path.join(c, "model.bin")) and (
            os.path.isfile(os.path.join(c, "tokenizer.json"))
            or os.path.isfile(os.path.join(c, "vocab.json"))
        ):
            local_model_path = c
            break

    # Try requested model, then fall back to smaller ones
    model_candidates = []
    if local_model_path:
        model_candidates.append(local_model_path)
    if model_size:
        model_candidates.append(model_size)
    for fallback in ("base", "small", "medium"):
        if fallback not in model_candidates:
            model_candidates.append(fallback)

    last_error = None
    for candidate in model_candidates:
        try:
            if _model is None or getattr(_model, "_model_id", None) != candidate:
                model_path = os.path.join(os.path.dirname(__file__), "models", f"whisper-{candidate}")
                model_bin_file = os.path.join(model_path, "model.bin")

                if not os.path.isdir(model_path) or not os.path.isfile(model_bin_file):
                    model_path = candidate

                logger.info(f"Load Whisper model: {model_path}, device: {device}")

                _model = WhisperModel(
                    model_size_or_path=model_path,
                    device=device,
                    compute_type=compute_type,
                )
                # remember model id for fallback logic
                try:
                    _model._model_id = candidate
                except Exception:
                    pass

            logger.info(f"Start subtitle generation: {subtitle_file}")
            segments, info = _model.transcribe(
                audio_file,
                beam_size=5,
                word_timestamps=True,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=500),
            )

            logger.info(f"Detected language: '{info.language}', prob: {info.language_probability:.2f}")

            subtitles = []
            for segment in segments:
                words_idx = 0
                words_len = len(segment.words) if segment.words else 0

                seg_start = 0
                seg_end = 0
                seg_text = ""

                if segment.words:
                    is_segmented = False
                    for word in segment.words:
                        if not is_segmented:
                            seg_start = word.start
                            is_segmented = True

                        seg_end = word.end
                        seg_text += word.word

                        if _contains_punctuation(word.word):
                            seg_text = seg_text[:-1]
                            if seg_text:
                                subtitles.append({
                                    "msg": seg_text.strip(),
                                    "start_time": seg_start,
                                    "end_time": seg_end,
                                })
                            is_segmented = False
                            seg_text = ""

                        words_idx += 1

                if seg_text:
                    subtitles.append({
                        "msg": seg_text.strip(),
                        "start_time": seg_start,
                        "end_time": seg_end,
                    })

            idx = 1
            lines = []
            for subtitle in subtitles:
                text_item = subtitle.get("msg")
                if text_item:
                    lines.append(_text_to_srt(
                        idx, text_item, subtitle.get("start_time"), subtitle.get("end_time")
                    ))
                    idx += 1

            sub = "\n".join(lines) + "\n"
            os.makedirs(os.path.dirname(subtitle_file), exist_ok=True)
            with open(subtitle_file, "w", encoding="utf-8") as f:
                f.write(sub)

            logger.info(f"Subtitle file created: {subtitle_file}")
            return subtitle_file

        except Exception as e:
            last_error = e
            logger.error(f"Load/Generate Whisper failed for '{candidate}': {e}")
            # try next smaller model
            _model = None

    logger.error(f"All Whisper model candidates failed: {last_error}")
    return ""

def _contains_punctuation(text: str) -> bool:
    """检查文本是否包含标点符号"""
    punctuations = ".,;:!?。！？，、；："
    return any(p in text for p in punctuations)


def _text_to_srt(idx: int, text: str, start_time: float, end_time: float) -> str:
    """将文本转换为 SRT 格式"""
    start_str = _format_timestamp(start_time)
    end_str = _format_timestamp(end_time)
    return f"{idx}\n{start_str} --> {end_str}\n{text}\n"


def _format_timestamp(seconds: float) -> str:
    """格式化时间戳"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def file_to_subtitles(filename: str) -> List[tuple]:
    """
    从 SRT 文件读取字幕
    
    Args:
        filename: SRT 文件路径
        
    Returns:
        字幕列表 [(index, time, text), ...]
    """
    if not filename or not os.path.isfile(filename):
        return []
    
    times_texts = []
    current_times = None
    current_text = ""
    index = 0
    
    with open(filename, "r", encoding="utf-8") as f:
        for line in f:
            times = re.findall(r"([0-9]*:[0-9]*:[0-9]*,[0-9]*)", line)
            if times:
                current_times = line
            elif line.strip() == "" and current_times:
                index += 1
                times_texts.append((index, current_times.strip(), current_text.strip()))
                current_times, current_text = None, ""
            elif current_times:
                current_text += line
    
    return times_texts


def correct_subtitle(subtitle_file: str, video_script: str) -> bool:
    """
    校正字幕文件
    
    Args:
        subtitle_file: 字幕文件路径
        video_script: 视频脚本
        
    Returns:
        是否进行了校正
    """
    subtitle_items = file_to_subtitles(subtitle_file)
    script_lines = _split_string_by_punctuations(video_script)
    
    corrected = False
    new_subtitle_items = []
    script_index = 0
    subtitle_index = 0
    
    while script_index < len(script_lines) and subtitle_index < len(subtitle_items):
        script_line = script_lines[script_index].strip()
        subtitle_line = subtitle_items[subtitle_index][2].strip()
        
        if script_line == subtitle_line:
            new_subtitle_items.append(subtitle_items[subtitle_index])
            script_index += 1
            subtitle_index += 1
        else:
            combined_subtitle = subtitle_line
            start_time = subtitle_items[subtitle_index][1].split(" --> ")[0]
            end_time = subtitle_items[subtitle_index][1].split(" --> ")[1]
            next_subtitle_index = subtitle_index + 1
            
            while next_subtitle_index < len(subtitle_items):
                next_subtitle = subtitle_items[next_subtitle_index][2].strip()
                if _similarity(script_line, combined_subtitle + " " + next_subtitle) > _similarity(script_line, combined_subtitle):
                    combined_subtitle += " " + next_subtitle
                    end_time = subtitle_items[next_subtitle_index][1].split(" --> ")[1]
                    next_subtitle_index += 1
                else:
                    break
            
            if _similarity(script_line, combined_subtitle) > 0.8:
                logger.warning(f"合并/校正 - 脚本: {script_line}, 字幕: {combined_subtitle}")
                new_subtitle_items.append((
                    len(new_subtitle_items) + 1,
                    f"{start_time} --> {end_time}",
                    script_line,
                ))
                corrected = True
            else:
                logger.warning(f"不匹配 - 脚本: {script_line}, 字幕: {combined_subtitle}")
                new_subtitle_items.append((
                    len(new_subtitle_items) + 1,
                    f"{start_time} --> {end_time}",
                    script_line,
                ))
                corrected = True
            
            script_index += 1
            subtitle_index = next_subtitle_index
    
    while script_index < len(script_lines):
        logger.warning(f"额外脚本行: {script_lines[script_index]}")
        if subtitle_index < len(subtitle_items):
            new_subtitle_items.append((
                len(new_subtitle_items) + 1,
                subtitle_items[subtitle_index][1],
                script_lines[script_index],
            ))
            subtitle_index += 1
        else:
            new_subtitle_items.append((
                len(new_subtitle_items) + 1,
                "00:00:00,000 --> 00:00:00,000",
                script_lines[script_index],
            ))
        script_index += 1
        corrected = True
    
    if corrected:
        with open(subtitle_file, "w", encoding="utf-8") as fd:
            for i, item in enumerate(new_subtitle_items):
                fd.write(f"{i + 1}\n{item[1]}\n{item[2]}\n\n")
        logger.info("字幕已校正")
    else:
        logger.info("字幕无需校正")
    
    return corrected


def _split_string_by_punctuations(text: str) -> List[str]:
    """按标点符号分割字符串"""
    punctuations = ".,;:!?。！？，、；：\n"
    result = []
    current = ""
    
    for char in text:
        current += char
        if char in punctuations:
            if current.strip():
                result.append(current.strip())
            current = ""
    
    if current.strip():
        result.append(current.strip())
    
    return result


def _levenshtein_distance(s1: str, s2: str) -> int:
    """计算编辑距离"""
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    
    if len(s2) == 0:
        return len(s1)
    
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    
    return previous_row[-1]


def _similarity(a: str, b: str) -> float:
    """计算字符串相似度"""
    distance = _levenshtein_distance(a.lower(), b.lower())
    max_length = max(len(a), len(b))
    return 1 - (distance / max_length) if max_length > 0 else 1.0


def create_subtitle(
    audio_file: str,
    subtitle_file: str = "",
    provider: str = "whisper",
    fallback_text: str = "",
    **kwargs
) -> str:
    """
    创建字幕文件
    
    Args:
        audio_file: 音频文件路径
        subtitle_file: 字幕文件保存路径
        provider: 字幕生成提供商
        **kwargs: 额外参数
        
    Returns:
        字幕文件路径
    """
    if provider == "whisper":
        if "model_size" not in kwargs:
            kwargs["model_size"] = os.getenv("WHISPER_MODEL_SIZE", "medium")
        result = create_subtitle_whisper(
            audio_file=audio_file,
            subtitle_file=subtitle_file,
            **kwargs,
        )
        if result:
            return result
        if fallback_text:
            logger.warning("Whisper 未生成字幕，使用文本兜底字幕")
            return create_subtitle_from_text(audio_file, subtitle_file, fallback_text)
        return ""
    else:
        logger.warning(f"不支持的字幕生成提供商: {provider}")
        return ""


def create_subtitle_from_text(audio_file: str, subtitle_file: str, text: str) -> str:
    """使用脚本文本兜底生成字幕（按时长均分）"""
    if not subtitle_file:
        subtitle_file = f"{audio_file}.srt"
    lines = _split_string_by_punctuations(text or "")
    lines = [l.strip() for l in lines if l.strip()]
    if not lines:
        return ""
    try:
        from .voice_service import get_audio_duration
        audio_duration = float(get_audio_duration(audio_file) or 0)
    except Exception:
        audio_duration = 0
    if audio_duration <= 0:
        audio_duration = max(3.0, len(lines) * 2.0)
    per_line = max(1.0, audio_duration / len(lines))
    current = 0.0
    srt_lines = []
    for i, line in enumerate(lines, 1):
        start = current
        end = min(audio_duration, start + per_line)
        srt_lines.append(_text_to_srt(i, line, start, end))
        current = end
    os.makedirs(os.path.dirname(subtitle_file), exist_ok=True)
    with open(subtitle_file, "w", encoding="utf-8") as f:
        f.write("\n".join(srt_lines) + "\n")
    logger.info(f"字幕文件已创建(兜底): {subtitle_file}")
    return subtitle_file


if __name__ == "__main__":
    audio_file = "test.mp3"
    subtitle_file = create_subtitle(audio_file)
    print(f"字幕文件: {subtitle_file}")
