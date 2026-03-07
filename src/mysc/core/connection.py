# -*- coding: utf-8 -*-
"""
    connection
    ~~~~~~~~~~~~~~~~~~
    
    Log:
        2026-01-17 2.0.0 Me2sY 重构，升级为3.3.4

        2024-09-09 1.5.8 Me2sY  新增自动屏蔽方法

        2024-08-28 1.4.0 Me2sY
            1.创建
            2.优化server启动逻辑，使用clean降低错误发生，同时不同线程推送不同server文件，确保clean不会误删文件
"""

__author__ = 'Me2sY'
__version__ = '2.0.0'

__all__ = ['Connection']

import random
import threading
import time
from typing import ClassVar, Any, Optional, Self
import socket

import adbutils
from adbutils import AdbDevice, AdbConnection
from loguru import logger

from mysc.utils.params import Param


class Connection:
    """
        连接类，
        1.创建 Scrcpy 基础连接
        2.管理连接状态
    """
    SCRCPY_SERVER_NAME = 'scrcpy-server'
    SCRCPY_SERVER_VERSION = '3.3.4'

    PATH_LOCAL_SCRCPY_SERVER_JAR = Param.PATH_LIBS.joinpath(SCRCPY_SERVER_NAME)
    PATH_PUSH_SCRCPY: ClassVar[str] = f"/data/local/tmp/{SCRCPY_SERVER_NAME}"

    # 启动指令
    START_CMD: ClassVar[list[str]] = [
        'app_process', '/', 'com.genymobile.scrcpy.Server', SCRCPY_SERVER_VERSION
    ]
    # 参数
    START_ARGS: ClassVar[dict[str, Any]] = {
        'log_level': 'debug',
        # 采用 forward 通讯模式，PC为Client
        'tunnel_forward': True,
        'send_frame_meta': False,
        'stay_awake': True
    }

    @staticmethod
    def get_random_scid() -> str:
        """
            <SCID> is a 31-bit random number,
            so that it does not fail when several scrcpy instances start "at the same time" for the same device.
        :return: SCID
        """
        return format(random.randint(0, 0x7FFFFFFF), '08x')

    @classmethod
    def connect(
            cls, adb_device: AdbDevice, connection_kwargs: dict,
            auto_exclude: bool = True, time_out: int = 5
    ) -> Optional[Self]:
        """
            创建连接
        :return:
        """

        scid = cls.get_random_scid()

        # 采用每个进程独立scrcpy - server_SCID, 避免clean导致 scrcpy-server 自动删除
        path_push = cls.PATH_PUSH_SCRCPY + f"_{scid}"

        # 推送scrcpy-server至device
        adb_device.sync.push(cls.PATH_LOCAL_SCRCPY_SERVER_JAR, path_push)

        logger.debug(f"| > Push scrcpy-server {cls.SCRCPY_SERVER_VERSION} from {cls.PATH_LOCAL_SCRCPY_SERVER_JAR} to {path_push}")

        # 拼接连接命令
        cmd_list = [f'CLASSPATH={path_push}'] + cls.START_CMD

        connection_kwargs.update(cls.START_ARGS)
        connection_kwargs['scid'] = scid

        # 单一连接模式
        if auto_exclude:
            if connection_kwargs.get('video', False):
                connection_kwargs['audio'] = False
                connection_kwargs['control'] = False
            elif connection_kwargs.get('audio', False):
                connection_kwargs['video'] = False
                connection_kwargs['control'] = False
            elif connection_kwargs.get('control', False):
                connection_kwargs['video'] = False
                connection_kwargs['audio'] = False
            else:
                raise ValueError(f"Must have only one Video/Audio/Control True when auto_exclude mode.")

        for key, value in connection_kwargs.items():
            cmd_list += [f'{str(key).lower()}={str(value).lower()}']

        logger.debug(f"| > Create Connect Command Ready. ")
        logger.debug(f"| > {' '.join(cmd_list)}")

        # 启动 scrcpy-server 进程
        try:
            stream = adb_device.shell(cmd_list, stream=True, timeout=time_out)
        except adbutils.AdbError as e:
            logger.error(f"| × Making Stream Error with {e}")
            return None

        # 创建 连接
        wait_ms = 10
        conn = None
        for _ in range(time_out * 1000 // wait_ms):
            try:
                # 创建 forward 连接
                conn = adb_device.create_connection(adbutils.Network.LOCAL_ABSTRACT, f"scrcpy_{scid}")
                break
            except adbutils.AdbError:
                time.sleep(wait_ms / 1000)

        # 创建连接失败
        if conn is None:
            logger.error('| × Failed to Create Socket.')
            return None

        # Dummy Data 校验
        if conn.recv(1) != b'\x00':
            logger.error('| × Dummy Data Error.')
            return None

        device_name = conn.recv(64).decode('utf-8').rstrip('\x00')

        return cls(scid, device_name, stream, conn)

    def __init__(self, scid: str, device_name: str, connection_stream: AdbConnection, conn: socket.socket):
        """
            创建单连接
        """
        self.scid: str = scid
        self.device_name: str = device_name
        self.is_connected: bool = True

        self.stream: AdbConnection = connection_stream
        self.conn: socket.socket = conn

        threading.Thread(target=self._load_stream, daemon=True).start()

    def disconnect(self):
        """
            关闭连接
        :return:
        """
        self.is_connected = False
        try:
            self.conn.shutdown(2)
            self.conn.close()
        except Exception as e:
            ...

        try:
            self.stream.close()
        except Exception as e:
            ...

    def _load_stream(self):
        """
            读取回报数据
        :return:
        """
        msg = ''
        while self.is_connected and not self.stream.closed:
            try:
                w = self.stream.read_string(1)
                if w == b'':
                    logger.warning(f"Stream Lost Connection")
                    break
                if w == '\n':
                    logger.info(f"{self.device_name:>16} => {msg}")
                    if msg.lower().strip().find('killed') != -1:
                        self.disconnect()
                        raise ConnectionAbortedError()
                    msg = ''
                else:
                    msg += w
            except adbutils.AdbError:
                break
            except (ConnectionAbortedError, OSError):
                logger.warning(f"| ! Stream Lost Connection")
                break
            except Exception as e:
                logger.error(f"{self.device_name:<32} Stream Exception => {e}")

    def recv(self, buf_size: int) -> bytes:
        """
            Recv bytes
        :param buf_size:
        :return:
        """
        return self.conn.recv(buf_size) if self.is_connected else b''

    def send(self, data: bytes):
        """
            Send bytes
        :param data:
        :return:
        """
        self.is_connected and self.conn.send(data)


if __name__ == '__main__':
    from adbutils import adb
    device = adb.device_list()[0]
    connection = Connection.connect(device, {'video': True})
    print(connection.device_name, connection.scid, '已连接')
    print(connection.recv(1024))
    connection.disconnect()





