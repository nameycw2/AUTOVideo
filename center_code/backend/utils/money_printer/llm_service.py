"""
LLM content generation service for money-printer.
"""

import json
import logging
import os
import re
from typing import List

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3


def _get_deepseek_api_key() -> str:
    return os.environ.get("DEEPSEEK_API_KEY", "")


def _call_deepseek_api(prompt: str, api_key: str = None) -> str:
    from openai import OpenAI

    key = api_key or _get_deepseek_api_key()
    if not key:
        raise ValueError("DEEPSEEK_API_KEY is not configured")

    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    model_name = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

    client = OpenAI(api_key=key, base_url=base_url)
    response = client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": prompt}],
    )
    return (response.choices[0].message.content or "").strip()


def generate_script(
    video_subject: str,
    language: str = "",
    paragraph_number: int = 1,
    api_key: str = None,
    **kwargs,
) -> str:
    prompt = f"""
# Role: Video Script Generator

## Goals:
Generate a short video script for the given subject.

## Constraints:
1. Return plain text only, no markdown/title.
2. Keep it concise and direct.
3. Do not mention this prompt.
4. Use the same language as the subject unless language is explicitly provided.

## Context:
- subject: {video_subject}
- paragraphs: {max(1, int(paragraph_number or 1))}
- language: {language or 'auto'}
""".strip()

    last_error = ""
    for i in range(_MAX_RETRIES):
        try:
            result = _call_deepseek_api(prompt, api_key=api_key)
            if result and not result.startswith("Error:"):
                cleaned = result.replace("*", "").replace("#", "").strip()
                return cleaned
        except Exception as e:
            last_error = str(e)
            logger.warning(f"generate_script retry {i+1}: {last_error}")

    logger.error(f"generate_script failed: {last_error}")
    return ""


def generate_terms(
    video_subject: str,
    video_script: str,
    amount: int = 5,
    keywords: str = "",
    source: str = "pexels",
    api_key: str = None,
    **kwargs,
) -> List[str]:
    amount = max(3, int(amount or 5))
    src = (source or "").strip().lower()
    force_english = src in ("pexels", "pixabay")
    language_rule = "All terms must be in English." if force_english else "Terms can be in English or Chinese."

    def _parse_terms_response(raw: str) -> List[str]:
        if not raw:
            return []
        text = raw.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
        match = re.search(r"\[[\s\S]*\]", text)
        candidate = match.group(0) if match else text
        candidate = candidate.replace("'", "'").replace("'", "'")
        candidate = candidate.replace('"', '"').replace('"', '"')
        candidate = re.sub(r",\s*]", "]", candidate)
        if "'" in candidate and '"' not in candidate:
            candidate = candidate.replace("'", '"')
        try:
            data = json.loads(candidate)
        except Exception:
            return []
        if not isinstance(data, list):
            return []
        return [str(x).strip() for x in data if str(x).strip()]

    def _normalize_terms(items: List[str]) -> List[str]:
        out: List[str] = []
        seen = set()
        for it in items or []:
            t = re.sub(r"\s+", " ", str(it or "").strip())
            t = re.sub(r"[^\w\s\-]", " ", t, flags=re.UNICODE)
            t = re.sub(r"\s+", " ", t).strip(" -_")
            if not t:
                continue
            words = t.split()
            if len(words) > 4:
                t = " ".join(words[:4])
            key = t.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(t)
            if len(out) >= amount:
                break
        return out

    prompt = f"""
# Role: Video Search Terms Generator

## Goals:
Generate {amount} search terms for stock footage retrieval.

## Constraints:
1. Return JSON array of strings only.
2. Each term should be 1-4 words.
3. Terms must be concrete visual scenes/objects/actions.
4. Terms must be highly relevant to the script.
5. {language_rule}
6. Prefer user keywords when provided.

## Context:
Subject: {video_subject}
User Keywords: {keywords}
Script: {video_script}
""".strip()

    last_error = ""
    terms: List[str] = []
    fallback_api_key = _get_deepseek_api_key()
    tried_fallback = False

    for i in range(_MAX_RETRIES):
        try:
            raw = _call_deepseek_api(prompt, api_key=api_key)
            if raw.startswith("Error:"):
                logger.warning(raw)
                continue
            terms = _normalize_terms(_parse_terms_response(raw))
            if terms:
                break
        except Exception as e:
            last_error = str(e)
            if (
                not tried_fallback
                and api_key
                and fallback_api_key
                and fallback_api_key != api_key
                and ("Authentication" in last_error or "401" in last_error)
            ):
                api_key = fallback_api_key
                tried_fallback = True
                continue
            logger.warning(f"generate_terms retry {i+1}: {last_error}")

    if not terms and last_error:
        logger.error(f"generate_terms failed: {last_error}")
    return terms


def get_llm_providers() -> List[dict]:
    return [{"id": "deepseek", "name": "DeepSeek", "requires_api_key": True}]


def generate_terms_by_sentences(
    video_subject: str,
    sentences: List[str],
    keywords: str = "",
    source: str = "pexels",
    api_key: str = None,
    **kwargs,
) -> List[str]:
    clean_sentences = [re.sub(r"\s+", " ", (s or "").strip()) for s in (sentences or [])]
    clean_sentences = [s for s in clean_sentences if s]
    if not clean_sentences:
        return []

    src = (source or "").strip().lower()
    force_english = src in ("pexels", "pixabay")
    language_rule = "All terms must be in English." if force_english else "Terms can be in English or Chinese."

    numbered = "\n".join([f"{i+1}. {s}" for i, s in enumerate(clean_sentences)])
    prompt = f"""
# Role: Sentence-to-Visual-Term Mapper

## Goal:
For each sentence, output one stock-footage search term.

## Constraints:
1. Return a JSON array of strings only.
2. Array length must equal sentence count.
3. Each term should be 1-4 words.
4. Terms must be concrete visual scenes/objects/actions.
5. {language_rule}
6. Prefer user keywords if they are relevant.

## Context:
Subject: {video_subject}
User Keywords: {keywords}
Sentences:
{numbered}
""".strip()

    try:
        raw = _call_deepseek_api(prompt, api_key=api_key)
    except Exception as e:
        logger.warning(f"generate_terms_by_sentences failed: {e}")
        return []

    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    m = re.search(r"\[[\s\S]*\]", text)
    candidate = m.group(0) if m else text
    candidate = candidate.replace("'", "'").replace("'", "'")
    candidate = candidate.replace('"', '"').replace('"', '"')
    candidate = re.sub(r",\s*]", "]", candidate)
    if "'" in candidate and '"' not in candidate:
        candidate = candidate.replace("'", '"')
    try:
        data = json.loads(candidate)
    except Exception:
        return []
    if not isinstance(data, list):
        return []

    out: List[str] = []
    for i, s in enumerate(clean_sentences):
        term = str(data[i]).strip() if i < len(data) else ""
        term = re.sub(r"\s+", " ", term)
        term = re.sub(r"[^\w\s\-]", " ", term, flags=re.UNICODE)
        term = re.sub(r"\s+", " ", term).strip(" -_")
        if not term:
            token = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
            token = re.sub(r"\s+", " ", token).strip()
            term = " ".join(token.split()[:4]) if token else "lifestyle"
        out.append(term)
    return out


def analyze_script_content(
    video_script: str,
    api_key: str = None
) -> List[dict]:
    """
    分析脚本内容，提取关键内容并生成对应的搜索关键词
    
    Args:
        video_script: 视频脚本
        api_key: DeepSeek API Key（可选）
        
    Returns:
        关键内容列表，每个元素包含 content 和 search_terms
    """
    prompt = f"""
# Role: Script Content Analyzer

## Goals:
Analyze the video script and extract key content segments that should correspond to specific video footage.

## Constraints:
1. Identify distinct segments in the script that describe different scenes, objects, or activities.
2. For each segment, generate 3-5 search terms that would help find relevant stock video footage.
3. Return the results as a JSON array of objects, each containing:
   - "content": the text segment from the script
   - "search_terms": an array of 3-5 English search terms
4. Only return the JSON array, no other text.
5. The search terms must be in English and directly related to the content segment.

## Output Example:
[
  {{
    "content": "地道川菜以其麻辣鲜香的独特风味闻名于世，是中国八大菜系之一。",
    "search_terms": ["sichuan cuisine", "chinese food", "spicy dishes"]
  }},
  {{
    "content": "招牌水煮鱼是川菜中的经典菜品，鱼肉鲜嫩，汤汁麻辣可口。",
    "search_terms": ["fish dish", "sichuan boiled fish", "spicy fish"]
  }}
]

## Script to Analyze:
{video_script}
    """.strip()

    logger.info("分析脚本内容...")

    for i in range(_MAX_RETRIES):
        try:
            response = _call_deepseek_api(prompt=prompt, api_key=api_key)

            if response.startswith("Error:"):
                logger.error(f"分析脚本失败: {response}")
                return []

            segments = json.loads(response)
            if not isinstance(segments, list):
                logger.error("响应不是数组")
                continue

            valid_segments = []
            for segment in segments:
                if isinstance(segment, dict) and "content" in segment and "search_terms" in segment:
                    if isinstance(segment["search_terms"], list):
                        valid_segments.append(segment)

            if valid_segments:
                logger.info(f"脚本分析完成，提取了 {len(valid_segments)} 个关键内容段")
                return valid_segments

        except json.JSONDecodeError as e:
            logger.warning(f"解析 JSON 失败: {str(e)}")
        except Exception as e:
            logger.warning(f"分析脚本失败: {str(e)}")

        if i < _MAX_RETRIES - 1:
            logger.warning(f"分析脚本失败，重试 {i + 1}")

    logger.error("脚本分析失败，返回空结果")
    return []


if __name__ == "__main__":
    script = generate_script(video_subject="test subject", language="zh-CN", paragraph_number=1)
    print("script:")
    print(script)
    print(generate_terms(video_subject="test subject", video_script=script, source="pexels"))
