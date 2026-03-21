"""
视频处理模块
负责视频元数据获取、预处理和格式转换
"""

import os
import subprocess
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass
import ffmpeg


@dataclass
class VideoMetadata:
    """视频元数据类"""
    duration: Optional[float] = None
    fps: Optional[float] = None
    resolution: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    codec: Optional[str] = None
    bitrate: Optional[str] = None
    aspect_ratio: Optional[str] = None
    pixel_format: Optional[str] = None
    dynamic_range: Optional[str] = None  # SDR / HDR / HDR10 / Dolby Vision / HLG
    chroma_subsampling: Optional[str] = None  # 4:2:0 / 4:2:2 / 4:4:4
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'duration': self.duration,
            'fps': self.fps,
            'resolution': self.resolution,
            'width': self.width,
            'height': self.height,
            'codec': self.codec,
            'bitrate': self.bitrate,
            'aspect_ratio': self.aspect_ratio,
            'pixel_format': self.pixel_format,
            'dynamic_range': self.dynamic_range,
            'chroma_subsampling': self.chroma_subsampling
        }


class VideoProcessor:
    """视频处理器，负责视频元数据获取和预处理"""
    
    def __init__(self, use_ffmpeg: bool = True):
        """
        初始化视频处理器
        
        Args:
            use_ffmpeg: 是否使用ffmpeg获取元数据
        """
        self.use_ffmpeg = use_ffmpeg
        self._check_ffmpeg_available()
    
    def _check_ffmpeg_available(self):
        """检查ffmpeg是否可用"""
        try:
            import subprocess
            result = subprocess.run(['ffmpeg', '-version'], 
                               capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                return
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            pass
            
        if self.use_ffmpeg:
            print("警告: ffmpeg不可用，将禁用元数据获取功能")
            self.use_ffmpeg = False
    
    def get_video_metadata(self, video_path: str) -> VideoMetadata:
        """
        获取视频元数据
        
        Args:
            video_path: 视频文件路径
        
        Returns:
            VideoMetadata对象，包含视频的元数据信息
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"视频文件不存在: {video_path}")
        
        if not self.use_ffmpeg:
            return VideoMetadata()
        
        try:
            probe = ffmpeg.probe(video_path)
            video_stream = self._find_video_stream(probe)
            
            metadata = VideoMetadata()
            
            if video_stream:
                metadata.duration = float(probe.get('format', {}).get('duration', 0))
                metadata.fps = self._parse_fps(video_stream.get('r_frame_rate'))
                metadata.width = int(video_stream.get('width', 0))
                metadata.height = int(video_stream.get('height', 0))
                metadata.codec = video_stream.get('codec_name', 'unknown')
                metadata.bitrate = video_stream.get('bit_rate', 'unknown')
                metadata.pixel_format = video_stream.get('pix_fmt', 'unknown')
                
                if metadata.width and metadata.height:
                    metadata.resolution = f"{metadata.width}x{metadata.height}"
                    metadata.aspect_ratio = self._calculate_aspect_ratio(
                        metadata.width, metadata.height
                    )
            
            format_info = probe.get('format', {})
            if not metadata.bitrate and format_info.get('bit_rate'):
                metadata.bitrate = format_info['bit_rate']
            
            # 检测动态范围和色度采样
            if video_stream:
                metadata.dynamic_range = self._detect_dynamic_range(video_stream)
                metadata.chroma_subsampling = self._detect_chroma_subsampling(video_stream)
            
            return metadata
            
        except ffmpeg.Error as e:
            print(f"获取视频元数据失败: {e.stderr.decode('utf8')}")
            return VideoMetadata()
        except Exception as e:
            print(f"处理视频元数据时出错: {str(e)}")
            return VideoMetadata()
    
    def _find_video_stream(self, probe: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        从probe结果中找到视频流
        
        Args:
            probe: ffmpeg probe结果
        
        Returns:
            视频流信息字典，如果没有找到则返回None
        """
        streams = probe.get('streams', [])
        for stream in streams:
            if stream.get('codec_type') == 'video':
                return stream
        return None
    
    def _parse_fps(self, fps_str: Optional[str]) -> Optional[float]:
        """
        解析帧率字符串
        
        Args:
            fps_str: 帧率字符串，格式为"numerator/denominator"
        
        Returns:
            浮点数格式的帧率
        """
        if not fps_str:
            return None
        
        try:
            if '/' in fps_str:
                numerator, denominator = fps_str.split('/')
                return float(numerator) / float(denominator)
            else:
                return float(fps_str)
        except (ValueError, ZeroDivisionError):
            return None
    
    def _calculate_aspect_ratio(self, width: int, height: int) -> str:
        """
        计算宽高比
        
        Args:
            width: 视频宽度
            height: 视频高度
        
        Returns:
            宽高比字符串，如"16:9"
        """
        def gcd(a, b):
            while b:
                a, b = b, a % b
            return a
        
        if width == 0 or height == 0:
            return "unknown"
        
        divisor = gcd(width, height)
        return f"{width // divisor}:{height // divisor}"
    
    def _detect_dynamic_range(self, video_stream: Dict[str, Any]) -> str:
        """
        检测视频动态范围 (SDR/HDR)
        
        通过色彩空间、传输函数、像素格式等判断
        
        Args:
            video_stream: 视频流信息
        
        Returns:
            动态范围类型: SDR, HDR, HDR10, Dolby Vision, HLG
        """
        pixel_format = video_stream.get('pix_fmt', '')
        color_space = video_stream.get('color_space', '')
        color_transfer = video_stream.get('color_transfer', '')
        color_primaries = video_stream.get('color_primaries', '')
        
        # 组合所有色彩相关信息
        color_info = f"{color_space} {color_transfer} {color_primaries} {pixel_format}".lower()
        
        # Dolby Vision 检测
        if 'dolby' in color_info or 'dovi' in pixel_format.lower():
            return "Dolby Vision"
        
        # HDR10 / PQ 检测
        if 'smpte2084' in color_info or 'pq' in color_transfer.lower():
            return "HDR10"
        
        # HLG 检测
        if 'arib-std-b67' in color_info or 'hlg' in color_transfer.lower():
            return "HLG"
        
        # BT.2020 色彩空间通常是 HDR
        if 'bt2020' in color_info:
            return "HDR"
        
        # 通过位深度判断
        bits = video_stream.get('bits_per_raw_sample')
        if bits and int(bits) > 8:
            # 高位深可能是 HDR
            if 'bt2020' in color_info or 'smpte2084' in color_info:
                return "HDR"
        
        # 像素格式中包含 10bit/12bit
        if any(x in pixel_format for x in ['10le', '10be', '12le', '12be']):
            if 'bt2020' in color_space.lower():
                return "HDR"
        
        # 常见的 SDR 标识
        sdr_indicators = ['bt709', 'smpte170m', 'bt601', 'iec61966-2-1']
        for indicator in sdr_indicators:
            if indicator in color_info:
                return "SDR"
        
        # 默认返回 SDR（大多数视频）
        return "SDR"
    
    def _detect_chroma_subsampling(self, video_stream: Dict[str, Any]) -> str:
        """
        检测色度采样方式 (4:2:0 / 4:2:2 / 4:4:4)
        
        Args:
            video_stream: 视频流信息
        
        Returns:
            色度采样方式字符串
        """
        pixel_format = video_stream.get('pix_fmt', '').lower()
        
        # 4:2:0 格式列表
        subsampling_420 = [
            'yuv420p', 'nv12', 'nv21', 'yuvj420p',
            'p010le', 'p010be', 'p016le', 'p016be',
            'yuv420p10le', 'yuv420p10be', 'yuv420p12le', 'yuv420p12be',
            'yuv420p16le', 'yuv420p16be',
        ]
        
        # 4:2:2 格式列表
        subsampling_422 = [
            'yuv422p', 'yuvj422p', 'uyvy422', 'yuyv422', 'yvyu422',
            'nv16', 'p210le', 'p210be', 'p216le', 'p216be',
            'yuv422p10le', 'yuv422p10be', 'yuv422p12le', 'yuv422p12be',
        ]
        
        # 4:4:4 格式列表
        subsampling_444 = [
            'yuv444p', 'yuvj444p', 'rgb24', 'bgr24',
            'gbrp', '0rgb', 'rgb0', '0bgr', 'bgr0',
            'yuv444p10le', 'yuv444p10be', 'yuv444p12le', 'yuv444p12be',
            'gbrp10le', 'gbrp10be', 'gbrp12le', 'gbrp12be',
        ]
        
        # 4:0:0 (灰度)
        subsampling_400 = [
            'gray', 'gray8', 'gray10le', 'gray10be', 'gray12le', 'gray12be',
            'yuv400p', 'yuvj400p',
        ]
        
        if any(fmt in pixel_format for fmt in subsampling_420):
            return "4:2:0"
        elif any(fmt in pixel_format for fmt in subsampling_422):
            return "4:2:2"
        elif any(fmt in pixel_format for fmt in subsampling_444):
            return "4:4:4"
        elif any(fmt in pixel_format for fmt in subsampling_400):
            return "4:0:0 (灰度)"
        
        # 通过 chroma_location 辅助判断
        chroma_location = video_stream.get('chroma_location', '').lower()
        if chroma_location in ['left', 'topleft', 'top', 'bottom', 'bottomleft']:
            # 通常是 4:2:0
            return "4:2:0"
        
        # 尝试从像素格式名称推断
        if '422' in pixel_format:
            return "4:2:2"
        elif '444' in pixel_format:
            return "4:4:4"
        elif '420' in pixel_format:
            return "4:2:0"
        
        return "4:2:0 (默认)"
    
    def validate_video(self, video_path: str) -> Tuple[bool, str]:
        """
        验证视频文件是否有效
        
        Args:
            video_path: 视频文件路径
        
        Returns:
            (是否有效, 错误信息)
        """
        if not os.path.exists(video_path):
            return False, f"视频文件不存在: {video_path}"
        
        if not os.path.isfile(video_path):
            return False, f"路径不是文件: {video_path}"
        
        if not video_path.lower().endswith(('.mp4', '.avi', '.mov', '.mkv', '.flv', '.webm')):
            return False, f"不支持的视频格式: {video_path}"
        
        try:
            metadata = self.get_video_metadata(video_path)
            if metadata.duration and metadata.duration <= 0:
                return False, "视频时长无效"
            
            return True, "视频验证通过"
            
        except Exception as e:
            return False, f"视频验证失败: {str(e)}"
    
    def get_video_info_string(self, video_path: str) -> str:
        """
        获取视频信息的格式化字符串
        
        Args:
            video_path: 视频文件路径
        
        Returns:
            格式化的视频信息字符串
        """
        metadata = self.get_video_metadata(video_path)
        
        info_lines = [
            f"视频路径: {video_path}",
            f"文件名: {os.path.basename(video_path)}",
        ]
        
        if metadata.duration:
            info_lines.append(f"时长: {metadata.duration:.2f}秒")
        if metadata.fps:
            info_lines.append(f"帧率: {metadata.fps:.2f} FPS")
        if metadata.resolution:
            info_lines.append(f"分辨率: {metadata.resolution}")
        if metadata.aspect_ratio:
            info_lines.append(f"宽高比: {metadata.aspect_ratio}")
        if metadata.codec:
            info_lines.append(f"编码: {metadata.codec}")
        if metadata.pixel_format:
            info_lines.append(f"像素格式: {metadata.pixel_format}")
        
        return "\n".join(info_lines)
    
    def prepare_video_input(self, video_path: str, fps: float = 0.5, 
                           max_frames: Optional[int] = None) -> Dict[str, Any]:
        """
        准备视频输入数据
        
        Args:
            video_path: 视频文件路径
            fps: 采样帧率
            max_frames: 最大帧数限制
        
        Returns:
            包含视频输入信息的字典
        """
        metadata = self.get_video_metadata(video_path)
        
        video_input = {
            "type": "video",
            "video": video_path,
            "fps": fps,
        }
        
        if max_frames:
            video_input["max_frames"] = max_frames
        
        return video_input