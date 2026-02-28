"""
ASR service selector.

- Default provider: baidu (existing implementation).
- Optional provider: iflytek_lfasr (iFlytek 录音文件转写), which can return timestamps.

Return format:
    text: str
    timestamps: list[dict] | None
        [{"text": str, "start": float, "end": float, "duration": float}, ...]
"""

from __future__ import annotations

import os
from typing import Optional, Tuple, List, Dict


def _get_asr_provider(override: Optional[str] = None) -> str:
    """优先使用传入值，否则从 config 或环境变量读取，保证与 .env 一致。"""
    if override and str(override).strip():
        return str(override).strip().lower()
    try:
        from config import ASR_PROVIDER
        if ASR_PROVIDER and str(ASR_PROVIDER).strip():
            return str(ASR_PROVIDER).strip().lower()
    except Exception:
        pass
    return (os.environ.get("ASR_PROVIDER") or "baidu").strip().lower()


def recognize_text_and_timestamps(
    audio_file_path: str,
    *,
    provider: Optional[str] = None,
    timeout_sec: int = 15 * 60,
) -> Tuple[str, Optional[List[Dict]]]:
    provider = _get_asr_provider(provider)
    import logging
    logging.getLogger(__name__).info(f"ASR 使用提供方: {provider}")

    if provider in ("iflytek", "iflytek_lfasr", "xfyun", "xunfei", "讯飞"):
        from utils.iflytek_lfasr import transcribe_with_timestamps

        return transcribe_with_timestamps(audio_file_path, timeout_sec=timeout_sec)

    # Default: baidu (text-only)
    from utils.baidu_asr import recognize_speech

    text = recognize_speech(audio_file_path)
    return text, None

