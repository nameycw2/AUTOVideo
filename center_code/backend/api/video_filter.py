import os
import subprocess
import imageio_ffmpeg
from flask import current_app

class VideoFilterProcessor:
    @staticmethod
    def get_filter_command(filter_name):
        """
        定义滤镜参数字典 (从 Demo 中迁移过来)
        """
        filters = {
            "vintage": "curves=vintage,eq=saturation=0.8:contrast=1.1",
            "noir": "hue=s=0,eq=contrast=1.3:brightness=-0.05",
            "cyberpunk": "eq=contrast=1.2:saturation=1.5,colorbalance=bs=0.3:rs=0.3:gs=-0.1,unsharp=5:5:1.0",
            "cinematic": "eq=contrast=1.1:saturation=1.2,colorbalance=rm=0.2:bm=-0.2:rs=-0.2:bs=0.2",
            "warm_vignette": "colorbalance=rh=0.1:gh=0.1:bh=-0.2,vignette=PI/4",
            # 如果是原图或未知滤镜，不做处理
            "original": "null"
        }
        return filters.get(filter_name, "null")

    @staticmethod
    def apply_filter(input_full_path, output_full_path, filter_name):
        """
        执行 FFmpeg 命令
        :return: (success: bool, message: str)
        """
        try:
            # 1. 获取 FFmpeg 路径
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            
            # 2. 获取滤镜参数
            vf_string = VideoFilterProcessor.get_filter_command(filter_name)
            
            # 如果是原图，直接复制文件即可（或者跳过）
            if vf_string == "null":
                # 这里为了统一逻辑，还是跑一遍 ffmpeg copy，或者你可以选择直接 shutil.copy
                cmd = [
                    ffmpeg_exe, '-y',
                    '-i', input_full_path,
                    '-c', 'copy', # 直接流复制，不重编码
                    output_full_path
                ]
            else:
                # 应用滤镜
                cmd = [
                    ffmpeg_exe, '-y',
                    '-i', input_full_path,
                    '-vf', vf_string,
                    '-c:v', 'libx264', # 重新编码视频
                    '-c:a', 'copy',    # 复制音频
                    output_full_path
                ]

            # 3. 执行
            # capture_output=True 可以捕获报错信息，方便调试
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            return True, "Success"

        except subprocess.CalledProcessError as e:
            error_msg = f"FFmpeg Error: {e.stderr}"
            print(error_msg) # 打印到控制台方便调试
            return False, error_msg
        except Exception as e:
            return False, str(e)