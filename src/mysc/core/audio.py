# -*- coding: utf-8 -*-
"""
    audio
    ~~~~~~~~~~~~~~~~~~
    
    Log:
        2026-01-18 2.0.0 Me2sY
            1.重构，分离AudioPlayer/AudioAdapter，移除AudioPlayer
            2.使用 pyav 解析 opus flac 减少引用

        2024-09-18 1.6.0 Me2sY  适配插件体系，支持输出 last_pcm

        2024-09-09 1.5.8 Me2sY  新增raw_stream

        2024-09-05 1.5.4 Me2sY 优化pyaudio引入，适配termux

        2024-09-04 1.5.3 Me2sY
            1.新增 Opus解析
            2.重构类结构

        2024-08-31 1.4.1 Me2sY  修复Linux下缺陷

        2024-08-28 1.4.0 Me2sY  创建，优化 Player/Adapter 结构

        2024-08-25 0.1.0 Me2sY
            1.从connect中分离，独占连接
            2.预初始化播放器，降低声音延迟
"""

__author__ = 'Me2sY'
__version__ = '2.0.0'

__all__ = [
    'AudioKwargs', 'AudioAdapter'
]

from dataclasses import dataclass
from enum import StrEnum
import threading
from typing import ClassVar, Optional, Callable, Self

from adbutils import AdbDevice
import av
from loguru import logger

from mysc.core.connection import Connection
from mysc.core.defs import ConnectKwargs, Adapter


@dataclass
class AudioKwargs(ConnectKwargs):
    """
        Audio Args
    """

    class EnumAudioSource(StrEnum):
        OUTPUT = "output"
        PLAYBACK = "playback"
        MIC = "mic"
        MIC_UNPROCESSED = "mic_unprocessed"
        MIC_CAMCORDER = "mic_camcorder"
        MIC_VOICE_RECOGNITION = "mic_voice_recognition"
        MIC_VOICE_COMMUNICATION = "mic_voice_communication"
        VOICE_CALL = "voice_call"
        VOICE_CALL_UPLINK = "voice_call_uplink"
        VOICE_CALL_DOWNLINK = "voice_call_downlink"
        VOICE_PERFORMANCE = "voice_performance"

    class EnumAudioCodec(StrEnum):
        """
            AAC 暂不支持
            FLAC 延迟较大，不推荐
        """
        OPUS = "opus"
        FLAC = "flac"
        RAW = "raw"

    buffer_size: ClassVar[int] = 2048

    audio: bool = True

    audio_source: Optional[EnumAudioSource] = None
    audio_codec: Optional[EnumAudioCodec] = EnumAudioCodec.OPUS

    audio_bit_rate: Optional[int] = None
    audio_buffer: Optional[int] = None
    audio_output_buffer: Optional[int] = None

    def __post_init__(self):
        if self.audio_source and self.audio_source not in self.EnumAudioSource:
            raise TypeError(f"Invalid audio source: {self.audio_source}")

        if self.audio_codec and self.audio_codec not in self.EnumAudioCodec:
            raise TypeError(f"Invalid audio codec: {self.audio_codec}")

        if self.audio_codec == self.EnumAudioCodec.FLAC:
            logger.warning(f"| ! FLAC 编解码延迟较大，建议选择OPUS或RAW")

    def __bool__(self):
        return self.audio


class AudioAdapter(Adapter):
    """
        Audio Adapter
    """
    def __init__(
            self,
            audio_kwargs: Optional[AudioKwargs] = AudioKwargs(),
            frame_update_callback: Optional[Callable[[bytes], None]] = None,
            cb__disconnect: Optional[Callable] = None
    ):
        """
            音频适配器
        :param audio_kwargs:
        :param frame_update_callback:
        :param cb__disconnect:
        """
        super().__init__(audio_kwargs)

        self.codec: Optional[AudioKwargs.EnumAudioCodec] = None

        self.frame_update_callback: Optional[Callable[[bytes], None]] = frame_update_callback

        self.last_raw_pcm: Optional[bytes] = None

        self.cb__disconnect = cb__disconnect

    def connect(self, adb_device: AdbDevice, *args, **kwargs) -> Self:
        """
            连接
        :param adb_device:
        :param args:
        :param kwargs:
        :return:
        """
        logger.debug(f"| > Audio Args | {self.connect_kwargs}")

        self.connection = Connection.connect(adb_device, self.connect_kwargs)
        self.decode_header()
        self.is_running = True

        threading.Thread(target=self.thread_main, daemon=True).start()

        return self

    def disconnect(self):
        """
            断开连接
        :return:
        """
        self.is_running = False
        self.connection.disconnect()

    def decode_header(self):
        """
            解析头，并选择合适的解码器
        :return:
        """
        self.codec = AudioKwargs.EnumAudioCodec(
            self.connection.recv(4).replace(b'\x00', b'').decode().lower()
        )

        # 去除Scrcpy FLAC 无效头
        if self.codec == AudioKwargs.EnumAudioCodec.FLAC:
            self.connection.recv(34)
            logger.warning(f"| ! FLAC 模式延迟较大，建议选用RAW或OPUS编解码")

    def thread_main(self):
        """
            解析音频流
        :return:
        """
        # 原始 PCM 格式
        if self.codec == AudioKwargs.EnumAudioCodec.RAW:
            while self.is_running:
                try:
                    self.last_raw_pcm = self.connection.recv(self._kwargs.buffer_size)
                    self.frame_update_callback and self.frame_update_callback(self.last_raw_pcm)
                except OSError:
                    self.is_running = False
                    self.cb__disconnect and self.cb__disconnect()
                except Exception as e:
                    logger.warning(f"| ! Exception while parsing! > {e}")

        # OPUS/FLAC
        # FLAC实测存在较大延迟，不推荐使用
        # AAC 暂不支持
        elif self.codec in [AudioKwargs.EnumAudioCodec.OPUS, AudioKwargs.EnumAudioCodec.FLAC]:
            # 定义解码器
            codec = av.CodecContext.create(self.codec, 'r')

            # OPUS 转变格式为 s16
            resampler = av.audio.resampler.AudioResampler(format='s16', layout='stereo', rate=48000)

            while self.is_running:
                try:
                    packets = codec.parse(self.connection.recv(self._kwargs.buffer_size))
                    for packet in packets:
                        for frame in codec.decode(packet):
                            resampled_frames = resampler.resample(frame)
                            for pcm_frame in resampled_frames:
                                self.last_raw_pcm = pcm_frame.to_ndarray().tobytes()
                                self.frame_update_callback and self.frame_update_callback(self.last_raw_pcm)
                except OSError:
                    self.is_running = False
                    self.cb__disconnect and self.cb__disconnect()
                except Exception as e:
                    logger.warning(f"| ! Exception while parsing! > {e}")

        logger.info(f"| - Decode Audio stream closed.")

    def get_last_pcm(self) -> bytes:
        """
            最后一帧 pcm 数据
        :return:
        """
        return self.last_raw_pcm
