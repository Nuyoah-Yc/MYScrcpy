# -*- coding: utf-8 -*-
"""
    audio player
    ~~~~~~~~~~~~~~~~~~
    
    Log:
        2026-02-03 0.1.0 Me2sY 从 core.audio中分离，降低core的耦合度
"""

__author__ = 'Me2sY'
__version__ = '0.1.0'

__all__ = [
    'AudioPlayer'
]

from typing import ClassVar, Optional, Any

import pyaudio
from mysc.core.audio import AudioAdapter, AudioKwargs


class AudioPlayer:
    """
        Audio Player
        Use pyaudio
    """

    RATE: ClassVar[int] = 48000
    CHANNELS: ClassVar[int] = 2
    FORMAT: ClassVar[int] = pyaudio.paInt16
    FRAMES_PER_BUFFER: ClassVar[int] = 512

    def __init__(self):

        self._player = None
        self.stream = None

        # Default Device
        self.device_index = None
        self.is_ready: bool = False
        self.is_muted: bool = False

        self.rate = self.RATE
        self.channels = self.CHANNELS
        self.format = self.FORMAT
        self.frames_per_buffer = self.FRAMES_PER_BUFFER
        self.output = True

    def __del__(self):
        self.stop()

    def start(self, **kwargs):
        """
            启动播放器
        :param kwargs:
        :return:
        """
        self.stop()
        self.setup_player(**kwargs)

    def setup_player(
            self,
            rate: int = None, channels: int = None,
            audio_format: int = None, frames_per_buffer: int = None,
            output: bool = None,
            device_index: int | None = None,
            is_muted: bool = False,
    ):
        """
            设置播放器
        :param rate:
        :param channels:
        :param audio_format:
        :param frames_per_buffer:
        :param output:
        :param device_index:
        :param is_muted:
        :return:
        """
        try:
            self.stop()
        except OSError:
            ...
        except Exception as e:
            print(e)

        self._player = pyaudio.PyAudio()

        self.rate = rate if rate else self.rate
        self.channels = channels if channels else self.channels
        self.format = audio_format if audio_format else self.format
        self.frames_per_buffer = frames_per_buffer if frames_per_buffer else self.frames_per_buffer
        self.output = output if output is not None else self.output

        self.stream = self._player.open(
            rate=self.rate, channels=self.channels, format=self.format,
            frames_per_buffer=self.frames_per_buffer, output=self.output,
            output_device_index=device_index
        )
        self.device_index = device_index
        self.is_ready = True
        self.is_muted = is_muted

    def stop(self):
        """
            停止播放进程
        :return:
        """
        self.is_ready = False
        try:
            self._player.terminate()
        except:
            ...

    def play(self, raw_pcm_bytes: bytes):
        """
            播放
        :param raw_pcm_bytes:
        :return:
        """
        self.is_ready and not self.is_muted and self.stream.write(raw_pcm_bytes)

    def set_mute(self, mute: bool = True):
        """
            设置静音
        :param mute:
        :return:
        """
        self.is_muted = mute

    def switch_mute(self):
        """
            切换静音
        :return:
        """
        self.is_muted = not self.is_muted

    def select_device(self, device_index: Optional[int], **kwargs):
        """
            选择设备
        :param device_index:
        :param kwargs:
        :return:
        """
        # 静音设备
        _mute = self.is_muted
        self.set_mute(True)

        # 重新设置 player
        self.setup_player(device_index=device_index, **kwargs)

        # 恢复切换前状态
        self.set_mute(_mute)

    @property
    def current_output_device_info(self) -> Optional[dict[str, Any]]:
        """
            获取当前外放设备信息
        :return:
        """
        if not self.is_ready:
            return None

        if self.device_index is None:
            _p = pyaudio.PyAudio()
            self.device_index = _p.get_default_output_device_info()['index']
            _p.terminate()

        return self.get_output_device_info_by_index(self.device_index)

    @staticmethod
    def get_default_device():
        """
            获取默认外放设备
        :return:
        """
        _p = pyaudio.PyAudio()
        info = _p.get_default_output_device_info()
        _p.terminate()
        return info

    @staticmethod
    def get_output_devices() -> list[dict]:
        """
            获取播放设备信息列表
        :return:
        """
        _p = pyaudio.PyAudio()
        _devices = []
        for index in range(_p.get_device_count()):
            info = _p.get_device_info_by_index(index)
            if info['maxOutputChannels'] > 0 and info['hostApi'] == 0:
                _devices.append(info)
        _p.terminate()
        return _devices

    @staticmethod
    def get_device_index_by_name(device_name: str) -> Optional[int]:
        """
            通过设备名获取设备Index
        :param device_name:
        :return:
        """
        _devices = AudioPlayer.get_output_devices()
        for _ in _devices:
            if _['name'] == device_name:
                return _['index']
        return None

    @staticmethod
    def get_output_device_info_by_index(index: int) -> Optional[dict[str, Any]]:
        """
            获取设备信息
        :param index:
        :return:
        """
        devices = AudioPlayer.get_output_devices()
        for _device in devices:
            if _device['index'] == index:
                return _device
        return None



if __name__ == '__main__':
    import time
    from adbutils import adb
    device = adb.device_list()[0]

    player = AudioPlayer()
    player.start()

    va = AudioAdapter(
        AudioKwargs(audio_codec=AudioKwargs.EnumAudioCodec.OPUS, audio_source=AudioKwargs.EnumAudioSource.MIC),
        frame_update_callback=player.play
    )
    va.connect(device)

    while True:
        time.sleep(1)
