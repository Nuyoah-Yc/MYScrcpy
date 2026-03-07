# -*- coding: utf-8 -*-
"""
    video
    ~~~~~~~~~~~~~~~~~~
    
    Log:
        2026-01-17 2.0.0 Me2sY  重构

        2024-09-23 1.6.0 Me2sY  新增更新 Callback 方法

        2024-09-09 1.5.8 Me2sY  新增raw_stream

        2024-08-28 1.4.0 Me2sY  优化调整功能结构

        2024-08-25 0.1.0 Me2sY  创建，分离Scrcpy.connect，Video独自连接
"""

__author__ = 'Me2sY'
__version__ = '2.0.0'

__all__ = [
    'CameraKwargs', 'VideoKwargs', 'VideoAdapter'
]

from dataclasses import dataclass
from enum import StrEnum
import struct
import threading
import time
from typing import Optional, Callable, ClassVar, Self, Type, Any

from adbutils import AdbDevice
import av
from loguru import logger
import numpy as np
from PIL.Image import Image

from mysc.core.connection import Connection
from mysc.core.defs import ConnectKwargs, Adapter
from mysc.utils.vector import Coordinate, Point


@dataclass
class CameraKwargs(ConnectKwargs):
    """
        Video Camera Args
    """

    class EnumCameraFacing(StrEnum):
        FRONT = "front"
        BACK = "back"
        EXTERNAL = "external"

    camera_ar: Optional[str] = None
    camera_facing: Optional[EnumCameraFacing] = None
    camera_fps: Optional[int] = None
    camera_high_speed: Optional[bool] = None
    camera_id: Optional[int] = None
    camera_size: Optional[str] = None

    def __post_init__(self):
        if self.camera_id and self.camera_id < 0:
            raise ValueError(f"Camera ID Error")

        if self.camera_fps and self.camera_fps <= 0:
            raise ValueError(f"Camera Fps must be greater than 0")


@dataclass
class VideoKwargs(ConnectKwargs):
    """
        Video Args
    """
    class EnumVideoCodec(StrEnum):
        """
            暂不支持 AV1 解码
        """
        H264 = "h264"
        H265 = "h265"

    class EnumVideoSource(StrEnum):
        DISPLAY = "display"
        CAMERA = "camera"

    buffer_size: ClassVar[int] = 131072

    video: bool = True

    video_codec: Optional[EnumVideoCodec] = EnumVideoCodec.H264

    video_buffer: Optional[int] = None
    video_encoder: Optional[str] = None

    max_fps: Optional[int] = None
    max_size: Optional[int] = None

    video_bit_rate: Optional[int] = None
    crop: Optional[str] = None

    video_source: Optional[EnumVideoSource] = EnumVideoSource.DISPLAY

    _camera_kwargs: Optional[CameraKwargs] = None

    def __post_init__(self):
        if self.video_codec and self.video_codec not in self.EnumVideoCodec:
            raise ValueError(f"Video Codec Not Supported.")
        if self.max_fps is not None and self.max_fps <= 0:
            raise ValueError(f"Max Fps must be greater than 0")
        if self.max_size is not None and self.max_size < 0:
            raise ValueError(f"Max size Error")

    def to_kwargs(self) -> dict:
        """
            若定义 _camera_args
            则视频源为 Camera
        """
        kwargs = super().to_kwargs()

        # 相机源 则改变参数
        if self._camera_kwargs:
            kwargs.update(self._camera_kwargs.to_kwargs())
        return kwargs

    def to_items(self) -> list[tuple[str, Type, Optional[Any]]]:
        """
            涉及 Camera
        """
        items = super().to_items()
        name, camera_cls, camera_kwargs = items.pop(-1)
        if camera_kwargs is None:
            camera_kwargs = CameraKwargs()
        items += camera_kwargs.to_items()
        return items

    @classmethod
    def load(cls, **kwargs) -> Self:
        """
            加载参数，同时加载Camera参数
        :param kwargs:
        :return:
        """
        _vk = super().load(**kwargs)
        camera_kwargs = CameraKwargs.load(**kwargs)
        _vk._camera_kwargs = camera_kwargs
        return _vk

    def __bool__(self):
        return self.video

    @property
    def crop_(self) -> Optional[tuple[Coordinate, Point]]:
        """
            Crop 模式
        :return:
        """
        if self.crop is None or self.crop == '':
            return None

        try:
            w, h, x, y = self.crop.split(':')
        except ValueError:
            return None

        return Coordinate(int(w), int(h)), Point(int(x), int(y))


class VideoAdapter(Adapter):
    """
        Video Adapter
    """
    CODE_AV_MAP = {
        VideoKwargs.EnumVideoCodec.H264: 'h264',
        VideoKwargs.EnumVideoCodec.H265: 'hevc',
    }

    def __init__(self,
                 video_kwargs: Optional[VideoKwargs] = VideoKwargs(),
                 frame_update_callback: Optional[Callable] = None,
                 cb__disconnect: Optional[Callable] = None
                 ):
        """
            视频适配器
        :param video_kwargs:
        :param frame_update_callback:
        """
        super().__init__(video_kwargs)

        self.codec: Optional[VideoKwargs.EnumVideoCodec] = None

        # 设置回调函数
        self.frame_update_callback: Optional[Callable] = frame_update_callback

        self.frame_n: int = 0
        self.last_frame: Optional[av.VideoFrame] = None

        # 断开回调函数
        self.cb__disconnect = cb__disconnect

        self.is_paused: bool = False

    def connect(self, adb_device: AdbDevice) -> Self:
        """
            发起连接
        :param adb_device:
        :return:
        """
        logger.debug(f"| > Video Args | {self.connect_kwargs}")

        self.connection = Connection.connect(adb_device, self.connect_kwargs)
        if self.decode_header():
            self.is_running = True
        else:
            logger.error(f"| × Video Connect Failed!")
            return

        threading.Thread(target=self.thread_main, daemon=True).start()

        return self

    def disconnect(self):
        """
            断开连接
        :return:
        """
        self.is_running = False
        self.last_frame = None
        self.frame_n = 0
        self.connection.disconnect()

    def decode_header(self):
        """
            解析 Scrcpy Video header
        :return:
        """
        try:
            header_format = '>4sII'
            codec, width, height = struct.unpack(header_format, self.connection.recv(struct.calcsize(header_format)))
            codec = codec.replace(b'\x00', b'').decode('utf-8')
            self.codec = VideoKwargs.EnumVideoCodec(codec)
            logger.info(f"| - Video Stream Use Codec: {self.codec} with wh: {width} x {height}")
            return True

        except struct.error:
            self.is_running = False
            logger.error(f"| × Decode Video Header Error")
            return False

    def thread_main(self):
        """
            视频流解析主进程
            使用 pyav 进行视频帧解析
        :return:
        """
        # 创建context
        codec = av.CodecContext.create(self.CODE_AV_MAP.get(self.codec), 'r')

        # 解析
        while self.is_running:
            try:
                # 解析packets
                packets = codec.parse(self.connection.recv(self._kwargs.buffer_size))
                if self.is_paused:
                    time.sleep(0.0001)
                    continue

                for packet in packets:
                    # 解析 VideoFrame
                    for _frame in codec.decode(packet):
                        self.last_frame = _frame
                        self.frame_n += 1
                        self.frame_update_callback and self.frame_update_callback(self.frame_n, _frame)
            except OSError:
                self.is_running = False
                self.cb__disconnect and self.cb__disconnect()
            except Exception as e:
                logger.warning(f"| ! Exception while parsing! > {e}")

        logger.info(f"| - Decode Video stream closed.")

    def get_ndarray(self, frame_format: str = 'rgb24') -> Optional[np.ndarray]:
        """
            获取 frame ndarray
        :return:
        """
        if self.last_frame:
            return self.last_frame.to_ndarray(format=frame_format)
        else:
            return None

    def get_image(self) -> Optional[Image]:
        """
            获取 PIL.Image
        :return:
        """
        if self.last_frame:
            return self.last_frame.to_image()
        else:
            return None

    def get_frame(self) -> Optional[av.VideoFrame]:
        """
            获取 VideoFrame
        :return:
        """
        return self.last_frame

    @property
    def coordinate(self) -> Coordinate:
        """
            获取 Frame坐标系
        :return:
        """
        return Coordinate(self.last_frame.width, self.last_frame.height)

    @property
    def is_ready(self) -> bool:
        """
            是否就绪
        :return:
        """
        return self.last_frame is not None

    def get_buffer(self, _format='rgb24'):
        """
            返回ndarray
        :param _format:
        :return:
        """
        return self.last_frame.to_ndarray(format=_format).ravel()


if __name__ == '__main__':
    """
        Demo
    """
    from adbutils import adb
    device = adb.device_list()[0]

    GET_VIDEO = False

    def frame_callback(frame_n:int, frame: av.VideoFrame):
        global GET_VIDEO
        if GET_VIDEO: return
        else: GET_VIDEO = True
        frame.to_image().show()

    va = VideoAdapter(
        VideoKwargs(
            video_codec=VideoKwargs.EnumVideoCodec.H264, max_fps=15,
            # Use Camera
            video_source=VideoKwargs.EnumVideoSource.CAMERA,
            _camera_kwargs=CameraKwargs(camera_id=0)
        ),
        frame_update_callback=frame_callback
    )
    va.connect(device)

    time.sleep(2)
    va.disconnect()

