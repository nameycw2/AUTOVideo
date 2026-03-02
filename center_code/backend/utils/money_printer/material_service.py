"""
Video material fetch service for money-printer.
"""
import os
import random
import logging
from typing import List, Optional
from urllib.parse import urlencode
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning

logger = logging.getLogger(__name__)


class VideoAspect:
    """Video aspect ratio."""
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


class MaterialInfo:
    """Material item info."""
    def __init__(self):
        self.provider = "pexels"
        self.url = ""
        self.duration = 0


class VideoConcatMode:
    """Video concatenation mode."""
    random = "random"
    sequential = "sequential"


_proxy = None


def _verify_ssl() -> bool:
    v = (os.environ.get("MATERIAL_VERIFY_SSL", "true") or "true").strip().lower()
    return v in ("1", "true", "yes", "on")


def _search_overfetch_ratio() -> float:
    try:
        return max(1.0, float((os.environ.get("MATERIAL_SEARCH_OVERFETCH_RATIO", "1.25") or "1.25").strip()))
    except Exception:
        return 1.25


def _pexels_min_width(aspect_value: str) -> int:
    if aspect_value == "16:9":
        return 1280
    return 720


def _download_workers() -> int:
    try:
        return max(1, int((os.environ.get("MATERIAL_DOWNLOAD_WORKERS", "4") or "4").strip()))
    except Exception:
        return 4


def _download_retries() -> int:
    try:
        return max(1, int((os.environ.get("MATERIAL_DOWNLOAD_RETRIES", "2") or "2").strip()))
    except Exception:
        return 2


def _get_proxy():
    global _proxy
    if _proxy is None:
        _proxy = {}
    return _proxy


def get_api_key(cfg_key: str, api_key: str = None) -> str:
    """
    闂佸吋鍎抽崲鑼躲亹?API Key
    
    Args:
        cfg_key: 闂備焦婢樼粔鍫曟偪閸℃稒鐓ユい鏂垮悑閸?
        api_key: 闂佺儵鏅涢悺銊ф暜鐎涙ê顕遍柣妯诲絻瀵娊鏌?API Key
        
    Returns:
        API Key
    """
    if api_key:
        return api_key
    
    if cfg_key == "pexels_api_keys":
        return os.environ.get("PEXELS_API_KEY", "")
    elif cfg_key == "pixabay_api_keys":
        return os.environ.get("PIXABAY_API_KEY", "")
    
    return ""


def search_videos_pexels(
    search_term: str,
    minimum_duration: int,
    video_aspect: VideoAspect = None,
    pexels_api_key: str = None,
) -> List[MaterialInfo]:
    """
    婵?Pexels 闂佺懓鍚嬬划搴ㄥ磼閵娧勫枂闁糕剝渚楅弳?
    
    Args:
        search_term: 闂佺懓鍚嬬划搴ㄥ磼閵娾晛绀傞柟鎯板Г閺嗘盯鎮?        minimum_duration: 闂佸搫鐗冮崑鎾绘倶韫囨挾绠叉俊鐐插€垮褰掑礌閿涘嫮顦╃紓浣割槹鐢亞妲?        video_aspect: 闁荤喐鐟ュΛ婵嬨€傜捄鐩掓帡寮崜褌绱?
        pexels_api_key: Pexels API Key
        
    Returns:
        缂備浇浜慨闈涱焽濡ゅ懎绀嗘俊銈呭閳?    """
    if video_aspect is None:
        video_aspect = VideoAspect()
    
    aspect = VideoAspect(video_aspect.value if hasattr(video_aspect, 'value') else video_aspect)
    video_orientation = "portrait" if aspect.value == "9:16" else "landscape"
    video_width, video_height = aspect.to_resolution()
    min_width = _pexels_min_width(aspect.value)
    
    try:
        api_key = get_api_key("pexels_api_keys", pexels_api_key)
    except ValueError as e:
        logger.error(str(e))
        return []
    
    headers = {
        "Authorization": api_key,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    
    params = {"query": search_term, "per_page": 20, "orientation": video_orientation}
    query_url = f"https://api.pexels.com/videos/search?{urlencode(params)}"
    
    proxy = _get_proxy()
    logger.info(f"闂佺懓鍚嬬划搴ㄥ磼閵娧勫枂闁糕剝渚楅弳? {query_url}")
    
    try:
        verify_ssl = _verify_ssl()
        if not verify_ssl:
            warnings.simplefilter("ignore", InsecureRequestWarning)
        r = requests.get(query_url, headers=headers, proxies=proxy, verify=verify_ssl, timeout=(15, 45))
        response = r.json()
        video_items = []
        
        if "videos" not in response:
            logger.error(f"闂佺懓鍚嬬划搴ㄥ磼閵娧勫枂闁糕剝渚楅弳銉ヮ熆閹壆绨块悷? {response}")
            return video_items
        
        videos = response["videos"]
        for v in videos:
            duration = v["duration"]
            if duration < minimum_duration:
                continue
            
            video_files = v["video_files"]
            picked = None
            fallback = None
            for video in video_files:
                w = int(video["width"])
                h = int(video["height"])
                # Keep orientation consistent
                if aspect.value == "9:16" and h < w:
                    continue
                if aspect.value == "16:9" and w < h:
                    continue
                if w >= min_width:
                    if picked is None or (w * h) < (int(picked["width"]) * int(picked["height"])):
                        picked = video
                else:
                    if fallback is None or (w * h) > (int(fallback["width"]) * int(fallback["height"])):
                        fallback = video
            selected = picked or fallback
            if selected:
                item = MaterialInfo()
                item.provider = "pexels"
                item.url = selected["link"]
                item.duration = duration
                video_items.append(item)
        
        return video_items
    except Exception as e:
        logger.error(f"闂佺懓鍚嬬划搴ㄥ磼閵娧勫枂闁糕剝渚楅弳銉ヮ熆閹壆绨块悷? {str(e)}")
        return []


def search_videos_pixabay(
    search_term: str,
    minimum_duration: int,
    video_aspect: VideoAspect = None,
    pixabay_api_key: str = None,
) -> List[MaterialInfo]:
    """
    婵?Pixabay 闂佺懓鍚嬬划搴ㄥ磼閵娧勫枂闁糕剝渚楅弳?
    
    Args:
        search_term: 闂佺懓鍚嬬划搴ㄥ磼閵娾晛绀傞柟鎯板Г閺嗘盯鎮?        minimum_duration: 闂佸搫鐗冮崑鎾绘倶韫囨挾绠叉俊鐐插€垮褰掑礌閿涘嫮顦╃紓浣割槹鐢亞妲?        video_aspect: 闁荤喐鐟ュΛ婵嬨€傜捄鐩掓帡寮崜褌绱?
        pixabay_api_key: Pixabay API Key
        
    Returns:
        缂備浇浜慨闈涱焽濡ゅ懎绀嗘俊銈呭閳?    """
    if video_aspect is None:
        video_aspect = VideoAspect()
    
    aspect = VideoAspect(video_aspect.value if hasattr(video_aspect, 'value') else video_aspect)
    video_width, video_height = aspect.to_resolution()
    
    try:
        api_key = get_api_key("pixabay_api_keys", pixabay_api_key)
    except ValueError as e:
        logger.error(str(e))
        return []
    
    params = {
        "q": search_term,
        "video_type": "all",
        "per_page": 50,
        "key": api_key,
    }
    query_url = f"https://pixabay.com/api/videos/?{urlencode(params)}"
    
    proxy = _get_proxy()
    logger.info(f"闂佺懓鍚嬬划搴ㄥ磼閵娧勫枂闁糕剝渚楅弳? {query_url}")
    
    try:
        verify_ssl = _verify_ssl()
        if not verify_ssl:
            warnings.simplefilter("ignore", InsecureRequestWarning)
        r = requests.get(query_url, proxies=proxy, verify=verify_ssl, timeout=(15, 45))
        response = r.json()
        video_items = []
        
        if "hits" not in response:
            logger.error(f"闂佺懓鍚嬬划搴ㄥ磼閵娧勫枂闁糕剝渚楅弳銉ヮ熆閹壆绨块悷? {response}")
            return video_items
        
        videos = response["hits"]
        for v in videos:
            duration = v["duration"]
            if duration < minimum_duration:
                continue
            
            video_files = v["videos"]
            for video_type in video_files:
                video = video_files[video_type]
                w = int(video["width"])
                if w >= video_width:
                    item = MaterialInfo()
                    item.provider = "pixabay"
                    item.url = video["url"]
                    item.duration = duration
                    video_items.append(item)
                    break
        
        return video_items
    except Exception as e:
        logger.error(f"闂佺懓鍚嬬划搴ㄥ磼閵娧勫枂闁糕剝渚楅弳銉ヮ熆閹壆绨块悷? {str(e)}")
        return []


def save_video(video_url: str, save_dir: str = "") -> str:
    """
    濞ｅ洦绻傞悺銊ф喆閸℃侗鏆ラ柛鎺斿濠€浼村捶?
    Args:
        video_url: 閻熸瑥妫濋。绂猂L
        save_dir: 濞ｅ洦绻傞悺銊╂儎椤旇偐绉?

    Returns:
        闁哄牜鍓欏﹢鎾棘閸ワ附顐介悹渚灠缁?
    """
    import hashlib

    if not save_dir:
        save_dir = os.path.join(os.path.dirname(__file__), "cache_videos")

    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    url_without_query = video_url.split("?")[0]
    url_hash = hashlib.md5(url_without_query.encode()).hexdigest()
    video_id = f"vid-{url_hash}"
    video_path = os.path.join(save_dir, f"{video_id}.mp4")

    if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
        logger.info(f"閻熸瑥妫濋。璺侯啅閹绘帞鎽犻柛? {video_path}")
        return video_path

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    proxy = _get_proxy()
    verify_ssl = _verify_ssl()
    if not verify_ssl:
        warnings.simplefilter("ignore", InsecureRequestWarning)

    for attempt in range(1, _download_retries() + 1):
        try:
            with open(video_path, "wb") as f:
                with requests.get(
                    video_url,
                    headers=headers,
                    proxies=proxy,
                    verify=verify_ssl,
                    timeout=(20, 120),
                    stream=True,
                ) as r:
                    r.raise_for_status()
                    for chunk in r.iter_content(chunk_size=1024 * 256):
                        if chunk:
                            f.write(chunk)

            if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
                try:
                    from moviepy.video.io.VideoFileClip import VideoFileClip
                    clip = VideoFileClip(video_path)
                    duration = clip.duration
                    fps = clip.fps
                    clip.close()
                    if duration > 0 and fps > 0:
                        return video_path
                except Exception as e:
                    try:
                        os.remove(video_path)
                    except Exception:
                        pass
                    logger.warning(f"闁哄啰濮甸弲銉ф喆閸℃侗鏆ラ柡鍌氭矗濞? {video_path} => {str(e)}")
        except Exception as e:
            try:
                if os.path.exists(video_path):
                    os.remove(video_path)
            except Exception:
                pass
            if attempt >= _download_retries():
                logger.error(f"濞戞挸顑堝ù鍥╂喆閸℃侗鏆ュ鎯扮簿鐟? {str(e)}")
            else:
                logger.warning(f"濞戞挸顑堝ù鍥╂喆閸℃侗鏆ュ鎯扮簿鐟欙箓鏁嶅畝鍕閻犲洦娲滈?{attempt}/{_download_retries()} 婵? {str(e)}")

    return ""


def download_videos(
    task_id: str,
    search_terms: List[str],
    source: str = "pexels",
    video_aspect: VideoAspect = None,
    video_contact_mode: str = "random",
    audio_duration: float = 0.0,
    max_clip_duration: int = 5,
    pexels_api_key: str = None,
    pixabay_api_key: str = None,
    save_dir: str = None,
) -> List[str]:
    """
    婵炴垶鎸搁鍫澝归崶鈺傚枂闁糕剝渚楅弳銉х磼鏉堚晛校婵?    
    Args:
        task_id: 婵炲濮鹃褎鎱ㄩ悜鐡?
        search_terms: 闂佺懓鍚嬬划搴ㄥ磼閵娾晛绀傞柟鎯板Г閺嗘盯鎮归崶褏孝闁割煈浜為幃?        source: 缂備浇浜慨闈涱焽濡ゅ懎绾ч柕澶涘閻栭亶鏌ㄥ☉妯绘exels/pixabay闂?        video_aspect: 闁荤喐鐟ュΛ婵嬨€傜捄鐩掓帡寮崜褌绱?
        video_contact_mode: 闂佺懓鍢查崥瀣暜閺夋嚦鐔煎灳瀹曞洨顢?
        audio_duration: 闂傚倸锕ユ繛濠囥€傞崼鏇炵睄闁割偅娲樺В?
        max_clip_duration: 闂佸搫鐗冮崑鎾愁熆閸棗鎳庨。缁樼箾閸繄浠涙俊鐐插€垮?        pexels_api_key: Pexels API Key
        pixabay_api_key: Pixabay API Key
        save_dir: 婵烇絽娲︾换鍌炴偤閵娾晜鍎庢い鏃囧亹缁?
        
    Returns:
        闂佸搫鐗滈崜娆忥耿鐎靛憡鍠嗛柛鈩冧緱閺嗐儵鎮规笟顖氱仩缂佸墎鍋ゅ畷姘旈崟鈹惧亾?    """
    if video_aspect is None:
        video_aspect = VideoAspect()
    
    valid_video_items = []
    valid_video_urls = []
    found_duration = 0.0
    
    search_videos = search_videos_pexels if source == "pexels" else search_videos_pixabay
    
    for search_term in search_terms:
        kwargs = {
            "search_term": search_term,
            "minimum_duration": max_clip_duration,
            "video_aspect": video_aspect,
        }
        if source == "pexels":
            kwargs["pexels_api_key"] = pexels_api_key
        else:
            kwargs["pixabay_api_key"] = pixabay_api_key
        
        video_items = search_videos(**kwargs)
        logger.info(f"闂佺懓鐏氶崕鎶藉春?{len(video_items)} 婵炴垶鎼╂禍锝夛綖鐎ｎ偓绱?'{search_term}'")
        
        for item in video_items:
            if item.url not in valid_video_urls:
                valid_video_items.append(item)
                valid_video_urls.append(item.url)
                found_duration += item.duration
        need = max(0.0, float(audio_duration))
        if need > 0 and found_duration >= need * _search_overfetch_ratio():
            logger.info(
                f"Enough candidates found, stop searching early: found={found_duration:.2f}s, need={need:.2f}s"
            )
            break
    
    logger.info(
        f"Found {len(valid_video_items)} candidate videos, target={audio_duration}s, found={found_duration}s"
    )
    
    video_paths = []
    
    if save_dir is None:
        save_dir = os.path.join(os.path.dirname(__file__), "tasks", task_id, "materials")
    
    if video_contact_mode == "random":
        random.shuffle(valid_video_items)
    
    # Download in parallel to reduce wait time on remote CDN.
    need = max(1, int((max(0.0, float(audio_duration)) / max(1.0, float(max_clip_duration))) + 1))
    candidate_count = min(len(valid_video_items), max(need * 2, need + 2))
    candidates = valid_video_items[:candidate_count]
    workers = min(_download_workers(), max(1, len(candidates)))

    duration_by_url = {item.url: float(item.duration or 0.0) for item in candidates}
    downloaded = {}
    if workers <= 1:
        for item in candidates:
            saved_video_path = save_video(video_url=item.url, save_dir=save_dir)
            if saved_video_path:
                downloaded[item.url] = saved_video_path
    else:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {
                ex.submit(save_video, item.url, save_dir): item.url
                for item in candidates
            }
            for fut in as_completed(futures):
                url = futures[fut]
                try:
                    path = fut.result()
                    if path:
                        downloaded[url] = path
                except Exception as e:
                    logger.error(f"Download failed: {str(e)}")

    total_duration = 0.0
    for item in candidates:
        saved_video_path = downloaded.get(item.url)
        if not saved_video_path:
            continue
        video_paths.append(saved_video_path)
        total_duration += min(max_clip_duration, duration_by_url.get(item.url, 0.0))
        if total_duration > audio_duration:
            break
    
    logger.info(f"Download complete, total {len(video_paths)} videos")
    return video_paths


def download_videos_by_segments(
    task_id: str,
    segments: List[dict],
    source: str = "pexels",
    video_aspect: VideoAspect = None,
    pexels_api_key: str = None,
    pixabay_api_key: str = None,
    save_dir: str = None,
    default_min_duration: int = 4,
) -> List[str]:
    """
    Download materials per subtitle segment in order.
    Each segment item: {"term": str, "duration": float}
    """
    if video_aspect is None:
        video_aspect = VideoAspect()
    if save_dir is None:
        save_dir = os.path.join(os.path.dirname(__file__), "tasks", task_id, "materials")

    search_videos = search_videos_pexels if source == "pexels" else search_videos_pixabay
    out_paths: List[str] = []
    segment_items = [s for s in (segments or []) if isinstance(s, dict)]
    if not segment_items:
        return out_paths

    for seg in segment_items:
        term = str(seg.get("term", "") or "").strip()
        if not term:
            continue
        try:
            dur = float(seg.get("duration", 0.0) or 0.0)
        except Exception:
            dur = 0.0
        min_d = max(2, int(round(dur))) if dur > 0 else int(default_min_duration)
        kwargs = {
            "search_term": term,
            "minimum_duration": min_d,
            "video_aspect": video_aspect,
        }
        if source == "pexels":
            kwargs["pexels_api_key"] = pexels_api_key
        else:
            kwargs["pixabay_api_key"] = pixabay_api_key

        candidates = search_videos(**kwargs)
        if not candidates:
            logger.warning(f"No candidate video for segment term: {term}")
            continue

        chosen = candidates[0]
        path = save_video(chosen.url, save_dir=save_dir)
        if path:
            out_paths.append(path)

    logger.info(f"Segment-aligned download complete, total {len(out_paths)} videos")
    return out_paths


def get_video_sources() -> List[dict]:
    """
    闂佸吋鍎抽崲鑼躲亹閸ヮ剙缁╂い鏍ㄧ☉閻︻噣鏌ｉ妸銉ヮ伂妞ゎ偄顑嗛敍鎰板箣閻樻妲洪梺鍝勵槹閸旀牕顭囬棃娑掓敠?    
    Returns:
        闂佸搫顦崕鑼姳椤曗偓瀹曟艾螖閸曗斁鍋?    """
    return [
        {"id": "pexels", "name": "Pexels", "requires_api_key": True},
        {"id": "pixabay", "name": "Pixabay", "requires_api_key": True},
    ]


def search_videos(
    search_term: str,
    source: str = "pexels",
    minimum_duration: int = 5,
    video_aspect: VideoAspect = None,
    pexels_api_key: str = None,
    pixabay_api_key: str = None,
) -> List[MaterialInfo]:
    """
    闂佺懓鍚嬬划搴ㄥ磼閵娧勫枂闁糕剝渚楅弳銉х磼鏉堚晛校婵炲吋顨婇弫宥夊醇閵忋垹鐓氭繛鎴炴尨閸嬫捇鏌熼幁鎺戝姎鐟滅増鐩弫?    
    Args:
        search_term: 闂佺懓鍚嬬划搴ㄥ磼閵娾晛绀傞柟鎯板Г閺嗘盯鎮?        source: 缂備浇浜慨闈涱焽濡ゅ懎绾ч柕澶涘閻栭亶鏌ㄥ☉妯绘exels/pixabay闂?        minimum_duration: 闂佸搫鐗冮崑鎾绘倶韫囨挾绠叉俊鐐插€垮褰掑礌閿涘嫮顦╃紓浣割槹鐢亞妲?        video_aspect: 闁荤喐鐟ュΛ婵嬨€傜捄鐩掓帡寮崜褌绱?
        pexels_api_key: Pexels API Key
        pixabay_api_key: Pixabay API Key
        
    Returns:
        缂備浇浜慨闈涱焽濡ゅ懎绀嗘俊銈呭閳?    """
    if source == "pixabay":
        return search_videos_pixabay(
            search_term=search_term,
            minimum_duration=minimum_duration,
            video_aspect=video_aspect,
            pixabay_api_key=pixabay_api_key,
        )
    else:
        return search_videos_pexels(
            search_term=search_term,
            minimum_duration=minimum_duration,
            video_aspect=video_aspect,
            pexels_api_key=pexels_api_key,
        )


if __name__ == "__main__":
    videos = download_videos(
        task_id="test123",
        search_terms=["nature", "sunset"],
        audio_duration=30,
        source="pexels"
    )
    print(videos)

