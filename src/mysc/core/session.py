# -*- coding: utf-8 -*-
"""
    session
    ~~~~~~~~~~~~~~~~~~
    
    Log:
        2026-01-20 0.1.0 Me2sY 创建
"""

__author__ = 'Me2sY'
__version__ = '0.1.0'

__all__ = [
    'Session'
]

from typing import Callable, Optional, Self

from adbutils import AdbDevice
from loguru import logger

from mysc.core.audio import AudioKwargs, AudioAdapter
from mysc.core.control import ControlKwargs, ControlAdapter
from mysc.core.device import MYDevice
from mysc.core.video import VideoKwargs, VideoAdapter


class Session:
    """
        Scrcpy Connect Session
    """
    def __init__(
            self,
            device: AdbDevice | MYDevice,
            video_kwargs: VideoKwargs = None,
            audio_kwargs: AudioKwargs = None,
            control_kwargs: ControlKwargs = None,
            frame_update_callback: Optional[Callable] = None
    ):
        self.device = MYDevice(device) if isinstance(device, AdbDevice) else device
        _adb_device = self.device.adb_device

        self.ca = ControlAdapter(control_kwargs).connect(_adb_device) if control_kwargs else None

        if audio_kwargs and not self.device.device_info.is_audio_supported:
            logger.warning(f"| ! Audio Not Supported on this device!")
            self.aa = None
        else:
            self.aa = AudioAdapter(audio_kwargs).connect(_adb_device) if audio_kwargs else None

        if video_kwargs._camera_kwargs is not None and not self.device.device_info.is_camera_supported:
            logger.warning(f"| ! Camera Not Supported on this device!")
            self.va = None
        else:
            self.va = VideoAdapter(
                video_kwargs, frame_update_callback=frame_update_callback
            ).connect(_adb_device) if video_kwargs else None

        if self.ca is None and self.aa is None and self.va is None:
            raise RuntimeError(f"At Least One Adapter Required!")

        self.is_running = True

    def __del__(self):
        try:
            self.disconnect()
        except:
            ...

    def disconnect(self):
        """
            断开连接
        """
        try:
            self.ca and self.ca.disconnect()
        except Exception as e:
            ...

        try:
            self.aa and self.aa.disconnect()
        except Exception as e:
            ...

        try:
            self.va and self.va.disconnect()
        except Exception as e:
            ...

        self.is_running = False

    @classmethod
    def from_dict(cls, device, kwargs_dict: dict, frame_update_callback: Optional[Callable] = None) -> Self:
        """
            从 dict 加载
        :param device:
        :param kwargs_dict:
        :param frame_update_callback:
        :return:
        """
        video_kwargs = VideoKwargs.load(**kwargs_dict)
        audio_kwargs = AudioKwargs.load(**kwargs_dict)
        control_kwargs = ControlKwargs.load(**kwargs_dict)
        return cls(
            device=device,
            video_kwargs=video_kwargs,
            audio_kwargs=audio_kwargs,
            control_kwargs=control_kwargs,
            frame_update_callback=frame_update_callback
        )
