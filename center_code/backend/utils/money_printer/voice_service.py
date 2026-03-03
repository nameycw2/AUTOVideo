"""
语音合成服务
集成 MoneyPrinterTurbo 的 TTS 功能
支持阿里云 DashScope CosyVoice TTS
"""
import os
import logging
import math
import subprocess
import uuid
from typing import Union, Optional, List, Tuple

logger = logging.getLogger(__name__)


def get_alibaba_voices_for_frontend(language: str = "zh") -> List[dict]:
    """
    获取前端可用的阿里云音色列表
    
    Args:
        language: 语言过滤（zh/en）
        
    Returns:
        音色列表
    """
    from utils.dashscope_tts import list_voices_for_frontend
    return list_voices_for_frontend()


def tts_alibaba(
    text: str,
    voice_name: str,
    voice_rate: float,
    voice_file: str,
    voice_volume: float = 1.0,
) -> bool:
    """
    使用阿里云 DashScope CosyVoice TTS 合成语音
    
    Args:
        text: 要合成的文本
        voice_name: 音色名称
        voice_rate: 语速（0.5-2.0）
        voice_file: 输出文件路径
        voice_volume: 音量（0.0-1.0）
        
    Returns:
        是否成功
    """
    try:
        from utils.dashscope_tts import synthesize_speech, resolve_voice
        
        voice_name = resolve_voice(voice_name)
        
        speed = int((voice_rate - 0.5) / 1.5 * 15)
        speed = max(0, min(15, speed))
        
        volume = int(voice_volume * 15)
        
        audio_bytes = synthesize_speech(
            text=text,
            voice=voice_name,
            speed=speed,
            volume=volume,
            audio_format="mp3",
        )
        
        os.makedirs(os.path.dirname(voice_file), exist_ok=True)
        
        with open(voice_file, "wb") as f:
            f.write(audio_bytes)
        
        if os.path.exists(voice_file) and os.path.getsize(voice_file) > 0:
            logger.info(f"阿里云 TTS 合成成功: {voice_file}")
            return True
        else:
            logger.error(f"阿里云 TTS 合成失败: 文件为空")
            return False
            
    except Exception as e:
        logger.error(f"阿里云 TTS 合成失败: {str(e)}")
        return False


def tts_alibaba_with_timestamps(
    text: str,
    voice_name: str,
    voice_rate: float,
    voice_file: str,
    voice_volume: float = 1.0,
) -> Tuple[bool, List]:
    """
    使用阿里云 TTS 生成音频 + 句级时间戳。
    """
    try:
        from utils.dashscope_tts import synthesize_speech_with_timestamps, resolve_voice

        voice_name = resolve_voice(voice_name)
        speed = int((voice_rate - 0.5) / 1.5 * 15)
        speed = max(0, min(15, speed))
        volume = int(voice_volume * 15)

        audio_bytes, timestamps = synthesize_speech_with_timestamps(
            text=text,
            voice=voice_name,
            speed=speed,
            volume=volume,
            audio_format="mp3",
        )

        os.makedirs(os.path.dirname(voice_file), exist_ok=True)
        with open(voice_file, "wb") as f:
            f.write(audio_bytes)

        if os.path.exists(voice_file) and os.path.getsize(voice_file) > 0:
            logger.info(f"阿里云 TTS(带时间戳) 合成成功: {voice_file}, timestamps={len(timestamps)}")
            return True, (timestamps or [])
        logger.error("阿里云 TTS(带时间戳) 合成失败: 输出文件为空")
        return False, []
    except Exception as e:
        logger.error(f"阿里云 TTS(带时间戳) 合成失败: {str(e)}")
        return False, []


def _split_text(text: str, max_chars: int = 500) -> List[str]:
    """Split text into chunks within max_chars."""
    if not text:
        return []
    punctuations = "。！？；!?;\n"
    sentences = []
    buf = ""
    for ch in text:
        buf += ch
        if ch in punctuations:
            if buf.strip():
                sentences.append(buf.strip())
            buf = ""
    if buf.strip():
        sentences.append(buf.strip())
    chunks = []
    current = ""
    for s in sentences:
        if len(s) > max_chars:
            # hard split long sentence
            for i in range(0, len(s), max_chars):
                part = s[i:i + max_chars].strip()
                if part:
                    chunks.append(part)
            continue
        if not current:
            current = s
            continue
        if len(current) + 1 + len(s) <= max_chars:
            current = f"{current} {s}"
        else:
            chunks.append(current)
            current = s
    if current:
        chunks.append(current)
    return chunks


def tts_alibaba_chunked(
    text: str,
    voice_name: str,
    voice_rate: float,
    voice_file: str,
    voice_volume: float = 1.0,
    max_chars: int = 500,
) -> bool:
    """Chunked TTS for long text, then concatenate via ffmpeg."""
    chunks = _split_text(text, max_chars=max_chars)
    if not chunks:
        return False
    out_dir = os.path.dirname(voice_file)
    os.makedirs(out_dir, exist_ok=True)
    part_files = []
    for idx, chunk in enumerate(chunks, 1):
        part_path = os.path.join(out_dir, f"tts_part_{uuid.uuid4().hex}_{idx}.mp3")
        ok = tts_alibaba(chunk, voice_name, voice_rate, part_path, voice_volume)
        if not ok:
            logger.error("分段 TTS 失败")
            return False
        part_files.append(part_path)
    # concat with ffmpeg
    list_path = os.path.join(out_dir, f"tts_concat_{uuid.uuid4().hex}.txt")
    try:
        with open(list_path, "w", encoding="utf-8") as f:
            for p in part_files:
                safe_path = p.replace("\\", "/")
                f.write(f"file '{safe_path}'\n")
        ffmpeg = os.environ.get("FFMPEG_PATH") or "ffmpeg"
        cmd = [
            ffmpeg, "-y",
            "-f", "concat", "-safe", "0",
            "-i", list_path,
            "-c", "copy",
            voice_file
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error(f"ffmpeg 合并音频失败: {result.stderr}")
            return False
        if os.path.exists(voice_file) and os.path.getsize(voice_file) > 0:
            return True
        return False
    finally:
        try:
            if os.path.exists(list_path):
                os.remove(list_path)
        except Exception:
            pass


def get_all_azure_voices(filter_locals: List[str] = None) -> List[str]:
    """
    获取所有 Azure TTS 音色
    
    Args:
        filter_locals: 语言过滤列表（如 ["zh-CN", "en-US"]）
        
    Returns:
        音色列表
    """
    azure_voices_str = """
Name: zh-CN-XiaoxiaoNeural
Gender: Female

Name: zh-CN-XiaoyiNeural
Gender: Female

Name: zh-CN-YunjianNeural
Gender: Male

Name: zh-CN-YunxiNeural
Gender: Male

Name: zh-CN-YunxiaNeural
Gender: Male

Name: zh-CN-YunyangNeural
Gender: Male

Name: zh-CN-liaoning-XiaobeiNeural
Gender: Female

Name: zh-CN-shaanxi-XiaoniNeural
Gender: Female

Name: en-US-JennyNeural
Gender: Female

Name: en-US-GuyNeural
Gender: Male

Name: en-US-AriaNeural
Gender: Female

Name: en-US-DavisNeural
Gender: Male

Name: en-US-AmberNeural
Gender: Female

Name: en-US-AnaNeural
Gender: Female

Name: en-US-AshleyNeural
Gender: Female

Name: en-US-BrandonNeural
Gender: Male

Name: en-US-ChristopherNeural
Gender: Male

Name: en-US-CoraNeural
Gender: Female

Name: en-US-ElizabethNeural
Gender: Female

Name: en-US-EricNeural
Gender: Male

Name: en-US-MichelleNeural
Gender: Female

Name: en-US-MonicaNeural
Gender: Female

Name: en-US-SaraNeural
Gender: Female

Name: en-US-TonyNeural
Gender: Male
    """.strip()
    
    import re
    voices = []
    pattern = re.compile(r"Name:\s*(.+)\s*Gender:\s*(.+)\s*", re.MULTILINE)
    matches = pattern.findall(azure_voices_str)
    
    for name, gender in matches:
        if filter_locals and any(name.lower().startswith(fl.lower()) for fl in filter_locals):
            voices.append(f"{name}-{gender}")
        elif not filter_locals:
            voices.append(f"{name}-{gender}")
    
    voices.sort()
    return voices


def get_azure_voices_for_frontend(language: str = "zh") -> List[dict]:
    """
    获取前端可用的 Azure 音色列表
    
    Args:
        language: 语言过滤（zh/en）
        
    Returns:
        音色列表
    """
    filter_locals = ["zh-CN"] if language == "zh" else ["en-US"]
    voices = get_all_azure_voices(filter_locals)
    
    result = []
    for voice in voices:
        parts = voice.rsplit("-", 1)
        if len(parts) == 2:
            name, gender = parts
            result.append({
                "id": name,
                "name": f"{name} ({'女声' if gender == 'Female' else '男声'})",
                "gender": gender,
                "language": "zh-CN" if name.startswith("zh-CN") else "en-US"
            })
    
    return result


def parse_voice_name(name: str) -> str:
    """解析音色名称"""
    name = name.replace("-Female", "").replace("-Male", "").strip()
    return name


def is_azure_v2_voice(voice_name: str) -> str:
    """检查是否是 Azure V2 音色"""
    voice_name = parse_voice_name(voice_name)
    if voice_name.endswith("-V2"):
        return voice_name.replace("-V2", "").strip()
    return ""


def tts_edge(
    text: str,
    voice_name: str,
    voice_rate: float,
    voice_file: str,
    voice_volume: float = 1.0,
) -> bool:
    """
    使用 Edge TTS 合成语音
    
    Args:
        text: 要合成的文本
        voice_name: 音色名称
        voice_rate: 语速（0.5-2.0）
        voice_file: 输出文件路径
        voice_volume: 音量（0.0-1.0）
        
    Returns:
        是否成功
    """
    try:
        import edge_tts
        
        voice_name = parse_voice_name(voice_name)
        
        rate_str = f"+{int((voice_rate - 1) * 100)}%" if voice_rate > 1 else f"{int((voice_rate - 1) * 100)}%"
        
        communicate = edge_tts.Communicate(text, voice_name, rate=rate_str)
        
        os.makedirs(os.path.dirname(voice_file), exist_ok=True)
        
        import asyncio
        asyncio.run(communicate.save(voice_file))
        
        if os.path.exists(voice_file) and os.path.getsize(voice_file) > 0:
            logger.info(f"语音合成成功: {voice_file}")
            return True
        else:
            logger.error(f"语音合成失败: 文件为空")
            return False
            
    except Exception as e:
        logger.error(f"Edge TTS 合成失败: {str(e)}")
        return False


def tts_azure(
    text: str,
    voice_name: str,
    voice_rate: float,
    voice_file: str,
    voice_volume: float = 1.0,
    azure_api_key: str = None,
    azure_region: str = None,
) -> bool:
    """
    使用 Azure TTS 合成语音
    
    Args:
        text: 要合成的文本
        voice_name: 音色名称
        voice_rate: 语速
        voice_file: 输出文件路径
        voice_volume: 音量
        azure_api_key: Azure API Key
        azure_region: Azure 区域
        
    Returns:
        是否成功
    """
    try:
        import azure.cognitiveservices.speech as speechsdk
        
        if azure_api_key is None:
            azure_api_key = os.environ.get("AZURE_TTS_KEY")
        if azure_region is None:
            azure_region = os.environ.get("AZURE_TTS_REGION", "eastasia")
        
        if not azure_api_key:
            raise ValueError("Azure TTS API Key 未设置")
        
        voice_name = parse_voice_name(voice_name)
        
        speech_config = speechsdk.SpeechConfig(subscription=azure_api_key, region=azure_region)
        speech_config.speech_synthesis_voice_name = voice_name
        
        rate_str = f"{voice_rate:.2f}"
        ssml = f"""
        <speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="zh-CN">
            <voice name="{voice_name}">
                <prosody rate="{rate_str}">
                    {text}
                </prosody>
            </voice>
        </speak>
        """
        
        synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=None)
        result = synthesizer.speak_ssml_async(ssml).get()
        
        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            os.makedirs(os.path.dirname(voice_file), exist_ok=True)
            with open(voice_file, "wb") as f:
                f.write(result.audio_data)
            logger.info(f"Azure TTS 合成成功: {voice_file}")
            return True
        else:
            logger.error(f"Azure TTS 合成失败: {result.reason}")
            return False
            
    except Exception as e:
        logger.error(f"Azure TTS 合成失败: {str(e)}")
        return False


def tts(
    text: str,
    voice_name: str,
    voice_rate: float,
    voice_file: str,
    voice_volume: float = 1.0,
    provider: str = "alibaba",
    **kwargs
) -> bool:
    """
    TTS 语音合成
    
    Args:
        text: 要合成的文本
        voice_name: 音色名称
        voice_rate: 语速
        voice_file: 输出文件路径
        voice_volume: 音量
        provider: TTS 提供商（alibaba/edge/azure）
        **kwargs: 额外参数
        
    Returns:
        是否成功
    """
    if provider == "alibaba":
        if text and len(text) > 500:
            logger.warning("TTS 文本过长，使用分段合成")
            return tts_alibaba_chunked(text, voice_name, voice_rate, voice_file, voice_volume)
        return tts_alibaba(text, voice_name, voice_rate, voice_file, voice_volume)
    elif provider == "azure":
        return tts_azure(text, voice_name, voice_rate, voice_file, voice_volume, **kwargs)
    else:
        return tts_edge(text, voice_name, voice_rate, voice_file, voice_volume)


def get_audio_duration(audio_file: str) -> float:
    """
    获取音频时长
    
    Args:
        audio_file: 音频文件路径
        
    Returns:
        时长（秒）
    """
    try:
        from moviepy.audio.io.AudioFileClip import AudioFileClip
        clip = AudioFileClip(audio_file)
        duration = float(clip.duration or 0.0)
        clip.close()
        return max(0.0, duration)
    except Exception as e:
        logger.error(f"获取音频时长失败: {str(e)}")
        return 0


def get_voices(language: str = "zh", provider: str = "alibaba") -> List[dict]:
    """
    获取可用的音色列表
    
    Args:
        language: 语言（zh/en）
        provider: TTS 提供商
        
    Returns:
        音色列表
    """
    if provider == "alibaba":
        return get_alibaba_voices_for_frontend(language)
    elif provider == "azure":
        return get_azure_voices_for_frontend(language)
    else:
        return get_azure_voices_for_frontend(language)


if __name__ == "__main__":
    voices = get_voices("zh")
    print(f"可用音色: {len(voices)} 个")
    for v in voices[:5]:
        print(f"  - {v['name']}")
