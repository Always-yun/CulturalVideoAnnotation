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
    r_frame_rate: Optional[float] = None  # 标称基准帧率（文件元数据原始录制帧率）
    avg_frame_rate: Optional[float] = None  # 实际平均帧率（技术属性层帧率）
    fps_ratio: Optional[float] = None  # 帧率比值 = 实际平均帧率 / 标称基准帧率
    speed_status: Optional[str] = None  # 播放速度状态：正常/慢放/快放
    
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
            'chroma_subsampling': self.chroma_subsampling,
            'r_frame_rate': self.r_frame_rate,
            'avg_frame_rate': self.avg_frame_rate,
            'fps_ratio': self.fps_ratio,
            'speed_status': self.speed_status
        }


class VideoProcessor:
    """视频处理器，负责视频元数据获取和预处理"""
    
    def __init__(self, use_ffmpeg: bool = True, 
                 speed_threshold_low: float = 0.85, 
                 speed_threshold_high: float = 1.15):
        """
        初始化视频处理器
        
        Args:
            use_ffmpeg: 是否使用ffmpeg获取元数据
            speed_threshold_low: 慢放判定阈值（ratio低于此值判定为慢放）
            speed_threshold_high: 快放判定阈值（ratio高于此值判定为快放）
        """
        self.use_ffmpeg = use_ffmpeg
        self.speed_threshold_low = speed_threshold_low
        self.speed_threshold_high = speed_threshold_high
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
                
                metadata.r_frame_rate = self._parse_fps(video_stream.get('r_frame_rate'))
                metadata.avg_frame_rate = self._parse_fps(video_stream.get('avg_frame_rate'))
                
                metadata.fps = metadata.avg_frame_rate if metadata.avg_frame_rate else metadata.r_frame_rate
                
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
            
            # 计算帧率比值和播放速度状态
            metadata.fps_ratio, metadata.speed_status = self._detect_speed_status(
                metadata.r_frame_rate, metadata.avg_frame_rate
            )
            
            return metadata
            
        except ffmpeg.Error as e:
            print(f"获取视频元数据失败: {e.stderr.decode('utf8')}")
            return VideoMetadata()
        except Exception as e:
            print(f"处理视频元数据时出错: {str(e)}")
            return VideoMetadata()
    
    def _detect_speed_status(self, r_frame_rate: Optional[float], 
                             avg_frame_rate: Optional[float]) -> Tuple[Optional[float], Optional[str]]:
        """
        检测视频播放速度状态
        
        指标定义：
        - 标称基准帧率: r_frame_rate（文件元数据原始录制帧率）
        - 实际平均帧率: avg_frame_rate（实际fps，技术属性层帧率按这个标）
        
        判定规则：
        ratio = 实际平均帧率 / 标称基准帧率
        ratio接近1 → 正常；ratio低于阈值→慢放；ratio高于阈值→快放
        
        Args:
            r_frame_rate: 标称基准帧率
            avg_frame_rate: 实际平均帧率
        
        Returns:
            (帧率比值, 播放速度状态)
        """
        if r_frame_rate is None or avg_frame_rate is None:
            return None, None
        
        if r_frame_rate <= 0:
            return None, None
        
        fps_ratio = avg_frame_rate / r_frame_rate
        
        if fps_ratio < self.speed_threshold_low:
            return fps_ratio, "慢放"
        elif fps_ratio > self.speed_threshold_high:
            return fps_ratio, "快放"
        else:
            return fps_ratio, "正常"
    
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
            浮点数格式的帧率（保留两位小数）
        """
        if not fps_str:
            return None
        
        try:
            if '/' in fps_str:
                numerator, denominator = fps_str.split('/')
                return round(float(numerator) / float(denominator), 2)
            else:
                return round(float(fps_str), 2)
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
    
    def compress_video_for_api(self, video_path: str, max_size_mb: float = 10.0) -> str:
        """
        压缩视频以适应API限制
        
        GLM-4 API对视频输入有大小限制，此方法会自动压缩过大的视频。
        
        Args:
            video_path: 原始视频文件路径
            max_size_mb: 目标最大文件大小(MB)
        
        Returns:
            压缩后的视频文件路径（如果不需要压缩则返回原路径）
        """
        file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
        
        if file_size_mb <= max_size_mb:
            print(f"--- 视频大小 {file_size_mb:.2f} MB 在限制范围内，无需压缩 ---")
            return video_path
        
        print(f"--- 视频大小 {file_size_mb:.2f} MB 超过限制 {max_size_mb} MB，开始压缩 ---")
        
        try:
            metadata = self.get_video_metadata(video_path)
            target_bitrate_kbps = int((max_size_mb * 1024 * 8) / (metadata.duration if metadata.duration else 10))
            
            compressed_path = video_path.replace('.mp4', '_compressed.mp4')
            if os.path.exists(compressed_path):
                os.remove(compressed_path)
            
            cmd = [
                'ffmpeg', '-i', video_path,
                '-c:v', 'libx264',
                '-b:v', f'{target_bitrate_kbps}k',
                '-preset', 'ultrafast',
                '-crf', '28',
                '-y',
                compressed_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                new_size_mb = os.path.getsize(compressed_path) / (1024 * 1024)
                print(f"--- 视频压缩完成: {new_size_mb:.2f} MB ---")
                return compressed_path
            else:
                print(f"--- 视频压缩失败: {result.stderr} ---")
                return video_path
                
        except Exception as e:
            print(f"--- 视频压缩异常: {str(e)} ---")
            return video_path
    
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