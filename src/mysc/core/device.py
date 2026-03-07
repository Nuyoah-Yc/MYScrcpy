# -*- coding: utf-8 -*-
"""
    device
    ~~~~~~~~~~~~~~~~~~
    
    Log:
        2026-01-19 2.0.0 Me2sY
            1. 使用 Json 持久化
            2. 重构功能

        2024-10-13 1.6.6 Me2sY
            1. 修复prop解析错误问题
            2. 降低 UHID 输入版本功能需求至 9

        2024-10-09 1.6.5 Me2sY  适配 MuMu模拟器

        2024.09.18 1.6.0 Me2sY  适配 插件 体系

        2024-09-13 1.5.11 Me2sY 新引入 uiautomator2，在dump/info/screenshot方面使用jsonrpc,速度很快

        2024-09-10 1.5.9 Me2sY  新增文件管理器，支持拷贝、上传、删除等功能

        2024-08-31 1.4.1 Me2sY  改用新KVManager

        2024-08-29 1.4.0 Me2sY  重构，适配 Session 体系

        2024-08-25 0.1.0 Me2sY  重构，拆分VAC至单个连接
"""

__author__ = 'Me2sY'
__version__ = '2.0.0'

__all__ = [
    'JSDeviceInfo',
    'MYDevice'
]

import pathlib
from dataclasses import dataclass
from typing import Optional

from adbutils import AdbDevice, AdbError, adb
from kivy.logger import Logger

from mysc.utils.storage import JSONStorage
from mysc.utils.vector import Coordinate, EnumDirection


@dataclass
class JSDeviceInfo(JSONStorage):
    """
        设备信息表
    """
    StoragePath = pathlib.Path('devices_info')

    serial_no: str
    brand: str = ''
    model: str = ''
    sdk: int = 34
    release: int = 14

    def __repr__(self):
        return f"<Device {self.serial_no}|SDK:{self.sdk}|RELEASE:{self.release}>"

    def __str__(self):
        return f"<Device {self.serial_no:<15}|SDK:{self.sdk}|RELEASE:{self.release}>"

    @property
    def is_scrcpy_supported(self) -> bool:
        return self.sdk > 21 and self.release > 5

    @property
    def is_audio_supported(self) -> bool:
        return self.release >= 12

    @property
    def is_camera_supported(self) -> bool:
        return self.release >= 12

    @property
    def is_uhid_supported(self) -> bool:
        return self.release >= 9


class MYDevice:
    """
        MY Device
    """

    @staticmethod
    def analysis_device(adb_device: AdbDevice) -> JSDeviceInfo:
        """
            通过getprop 快速读取并解析设备信息
        :param adb_device:
        :return:
        """
        serial_no = adb_device.getprop('ro.serialno')

        device_info = JSDeviceInfo.load(serial_no)

        if device_info is None:

            Logger.info(f"MYDevice: Get Device Info.")

            prop_d = {}

            for _ in adb_device.shell('getprop', timeout=1).split('\n'):
                _ = _.replace('\r', '')
                if _[0] != '[' or _[-1] != ']':
                    continue
                try:
                    k, v = _.split(': ')
                except Exception as e:
                    continue

                cmd = "prop_d"
                for _ in k[1:-1].split('.'):
                    cmd += f".setdefault('{_}', {{}})"

                cmd = cmd[:-3] + "'" + v[1:-1] + "')"

                try:
                    exec(cmd)
                except:
                    pass

            try:
                serial_no = prop_d['ro']['serialno']
            except:
                serial_no = adb_device.serial

            try:
                brand = prop_d['ro']['product']['brand']
            except:
                brand = ''

            try:
                model = prop_d['ro']['product']['model']
            except:
                model = ''

            try:
                sdk = int(prop_d['ro']['build']['version']['sdk'])
            except:
                sdk = 34

            try:
                release = prop_d['ro']['build']['version']['release']
            except Exception:
                release = 14

            if release is None or release == '':
                release = 14
            elif '.' in release:
                release = int(release.split('.')[0])
            else:
                release = int(release)

            device_info = JSDeviceInfo(
                serial_no,
                serial_no, brand, model, sdk, release
            )
            device_info.dump()

        return device_info

    def __init__(self, adb_device: AdbDevice):

        self.device_info = self.analysis_device(adb_device)
        self.serial_no = self.device_info.serial_no

        _wm_size = adb_device.window_size()

        self.coord = Coordinate(_wm_size.width, _wm_size.height)
        self.cur_direction: EnumDirection = self.coord.current_direction

        # adb_device 类型
        self.dev_usb = adb_device if adb_device.serial == self.device_info.serial_no else None
        self.dev_net = None if self.dev_usb else adb_device
        self.dev_adb: Optional[AdbDevice] = None

    def __repr__(self):
        return f"{self.device_info}"

    @property
    def adb_device(self) -> AdbDevice:
        """
            Adb Device
        :return:
        """
        if self.dev_adb:
            return self.dev_adb

        try:
            if self.dev_usb and self.dev_usb.shell('echo 1', timeout=0.1):
                self.dev_adb = self.dev_usb
                return self.dev_usb
        except AdbError as e:
            Logger.warning(f"MYDevice: {self.device_info} USB Connection Maybe LOST! Error => {e}")
            self.dev_usb = None

        try:
            if self.dev_net and self.dev_net.shell('echo 1', timeout=0.1):
                self.dev_adb = self.dev_net
                return self.dev_net

        except AdbError as e:
            Logger.warning(f"MYDevice: {self.device_info} Net Connection Maybe LOST! Error => {e}")

        self.dev_adb = None

        raise RuntimeError(f'Device not connected')

    @property
    def is_alive(self) -> bool:
        """
            连接是否断开
        :return:
        """
        try:
            if self.dev_usb and self.dev_usb.shell('echo 1', timeout=1):
                return True

            if self.dev_net and self.dev_net.shell('echo 1', timeout=1):
                return True

        except AdbError as e:
            ...

        return False

    @property
    def wlan_ip(self) -> str | None:
        """
            获取 Wlan IP
        :return:
        """
        try:
            return self.adb_device.wlan_ip()
        except AdbError:
            return None
        except RuntimeError:
            return None

    @property
    def is_tcpip_mode(self) -> bool:
        """
            是否为 TCP/IP调试模式
        :return:
        """
        return self.dev_usb is None

    @property
    def tcpip_port(self) -> int:
        """
            获取设备 TCPIP 端口
        :return:
        """
        # 2024-08-18 Me2sY 修复连接失败导致错误
        try:
            p = self.adb_device.getprop('service.adb.tcp.port')
        except Exception as e:
            p = ''
        if p is None or p == '':
            return -1
        else:
            return int(p)

    def set_power(self, status: bool = True):
        """
            set device power
        :param status:
        :return:
        """
        if self.adb_device.is_screen_on() ^ status:
            self.adb_device.keyevent('POWER')

    def lock(self):
        """
            Lock Device
        :return:
        """
        self.set_power(False)

    def is_locked(self):
        """
            is device locked
        :return:
        """
        return self.adb_device.shell('dumpsys deviceidle | grep "mScreenLocked="').strip().split('=')[1] == 'true'

    def reboot(self):
        """
            重启设备
        :return:
        """
        self.adb_device.reboot()

    def disconnect(self):
        """
            断开连接
        """
        if not self.is_tcpip_mode: return
        adb.disconnect(f"{self.wlan_ip}:{self.tcpip_port}")
