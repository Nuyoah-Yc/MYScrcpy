# -*- coding: utf-8 -*-
"""
    devices
    ~~~~~~~~~~~~~~~~~~
    
    Log:
        2026-01-27 0.1.0 Me2sY 创建
"""

__author__ = 'Me2sY'
__version__ = '0.1.0'

__all__ = ['ScreenListDevices']

from dataclasses import dataclass
import threading

from adbutils import adb, AdbDevice
from adbutils.errors import AdbTimeout

from kivy.clock import Clock
from kivy.metrics import dp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDIconButton, MDFabButton
from kivymd.uix.card import MDCard
from kivymd.uix.divider import MDDivider
from kivymd.uix.gridlayout import MDGridLayout
from kivymd.uix.label import MDLabel
from kivymd.uix.textfield import MDTextField, MDTextFieldHintText

from mysc.core.device import MYDevice
from mysc.gui.k.components.base.my_dialog import MYDialogInput
from mysc.gui.k.components.base.my_list import ListItemBase
from mysc.gui.k.components.base.my_screen import MYScreenList
from mysc.gui.k.components.base.my_snack_bar import MYSnackBarWarning, MYSnackBarInfo
from mysc.gui.k.components.screens.connect_modes import ScreenListModes
from mysc.gui.k.defs import init_language, Colors
from mysc.utils.storage import JSONStorage

_ = init_language()


@dataclass
class ScreenDeviceCfg(JSONStorage):

    Prefix = 'APPCFG_'

    auto_reload: bool = True
    reload_timeout: int = 30


class ListItemDevice(ListItemBase):

    @property
    def adb_serial(self) -> str:
        return self.my_device.adb_device.serial

    def __init__(self, sd: 'ScreenListDevices', adb_device: AdbDevice, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.sd = sd

        """
            Device
        """
        self.my_device = MYDevice(adb_device)
        self.is_connected: bool = False

        """
            创建设备Card
        """
        self.card = MDCard(
            style='filled', adaptive_height=True, padding=dp(8), spacing=dp(10),
            theme_bg_color="Custom",
            md_bg_color=Colors.BlueLight if self.my_device.is_tcpip_mode else Colors.Grey ,
        )
        self.add_widget(self.card)

        # 设备信息
        self.card.add_widget(
            MDBoxLayout(
                MDLabel(
                    text=f"{self.my_device.device_info.brand} {self.my_device.device_info.model}",
                    font_style='Label'
                ),
                MDDivider(),
                MDLabel(text=self.my_device.serial_no, font_style='Label'),
                orientation='vertical', size_hint_y=None, height=dp(80)
            )
        )

        self.card.add_widget(MDDivider(orientation='vertical'))

        # 功能区
        self.card.add_widget(
            MDGridLayout(
                MDIconButton(icon='lightbulb-on-outline', on_release=lambda *_args: self.my_device.set_power(True)),
                MDIconButton(icon='file-cog-outline', on_release=lambda *_args: self.sd.cb__screen_list_modes(self.my_device)),
                MDIconButton(icon='wifi-off' if self.my_device.is_tcpip_mode else 'wifi',
                             on_release=lambda *_args: self.cb__set_wifi()),
                # MDIconButton(icon='menu'),
                cols=2,
                size_hint_x=None, width=dp(80), pos_hint={'center_x': 0.5, 'center_y': 0.5}
            )
        )

        # 连接按钮
        self.card.add_widget(
            MDFabButton(
                icon='lan-disconnect' if self.is_connected else 'connection',
                pos_hint={'center_x': 0.5, 'center_y': 0.5},
                on_release=lambda *_args: self.sd.cb__screen_vac(self.my_device)
            )
        )

    def cb__set_wifi(self):
        """
            设置 WIFI
        """
        if self.my_device.is_tcpip_mode:
            self.my_device.disconnect()
            MYSnackBarInfo('Device Disconnected.')
        else:
            self.my_device.adb_device.tcpip(5555)
            MYSnackBarInfo('Device Open Port 5555.')
        self.sd.load_devices()


class ScreenListDevices(MYScreenList):

    TITLE = _('Devices')

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.cfg = ScreenDeviceCfg.load(self.__class__.__name__)
        if self.cfg is None:
            self.cfg = ScreenDeviceCfg(self.__class__.__name__)
            self.cfg.dump()

        self.app_cfg = self.main.app_cfg

    """
        Functions
    """
    def _load_devices(self):
        """
            加载设备
        """

        shown_devices = []

        # 当前显示的设备列表是否有断联的设备
        for device_item in self.my_list.items:
            try:
                serial = device_item.my_device.adb_device.serial
            except RuntimeError:
                Clock.schedule_once(lambda *_args: self.remove_device(device_item.my_device.adb_device))
                continue

            if device_item.my_device.is_alive and serial not in shown_devices:
                shown_devices.append(serial)
            else:
                Clock.schedule_once(lambda *_args: self.remove_device(device_item.my_device.adb_device))

        # 是否有新连接设备
        for adb_device in adb.device_list():
            if adb_device.serial not in shown_devices:
                Clock.schedule_once(lambda *args, dev=adb_device: self.add_device(dev))

    def load_devices(self, *args):
        """
            加载设备
        """
        # 采用 Clock 延迟加载 避免界面刷新异常效果
        Clock.schedule_once(
            lambda *_:
            threading.Thread(target=self._load_devices, daemon=True).start(), 0.8
        )

    def add_device(self, adb_device):
        """
            添加设备
        :param adb_device:
        :return:
        """
        self.my_list.add_list_item(ListItemDevice(self, adb_device))

    def remove_device(self, adb_device):
        """
            移除设备
        :param adb_device:
        :return:
        """
        for item in self.my_list.items:
            if item.my_device.adb_device.serial == adb_device.serial:
                self.my_list.remove_list_item(item)
                break

    def cb__screen_list_modes(self, my_device: MYDevice):
        """
            创建连接模式配置界面
        :param my_device:
        :return:
        """
        sl_modes = ScreenListModes(my_device, nav=self.nav, main=self.main)
        self.manager.add_widget(sl_modes)
        self.manager.current = sl_modes.name

    def cb__screen_vac(self, my_device: MYDevice):
        """
            创建连接Screen
        :param my_device:
        :return:
        """
        connect_kwargs = ScreenListModes.get_device_default_mode(my_device.serial_no)
        self.main.screen_connections.create_vac(my_device, connect_kwargs)

    def cb__connect_to_wireless(self, *args):
        """
            连接 WIFI 设备
        """
        def connect_to_wireless_device(address: str):
            """
                连接无线调试设备
            :param address:
            :return:
            """
            if address is None or address == "": return

            threading.Thread(
                target=connect_thread, args=(address,), daemon=True
            ).start()

        def connect_thread(address: str):
            """
                ADB 无线调试
            :param address:
            :return:
            """
            try:
                print(adb.connect(address, 5))
                self.load_devices()
            except AdbTimeout:
                Clock.schedule_once(
                    lambda dt: MYSnackBarWarning(_('Connect to') + address + _(" Timeout"))
                )

        MYDialogInput(
            'Connect to wireless device',
            connect_to_wireless_device,
            MDTextField(
                MDTextFieldHintText(_('Address')),
                pos_hint={'center_x': 0.5, 'center_y': 0.5},
                multiline=False, mode='filled'
            )
        ).open()

    def cb__set_auto_loading(self, *args):
        """
            自动加载
        :return:
        """
        self.nav_btn_autoload.disabled = not self.nav_btn_autoload.disabled

    def auto_loading(self, *args):
        """
            自动刷新
        :return:
        """
        if self.cfg.auto_reload and self.is_current:
            self.load_devices()

        Clock.schedule_once(self.auto_loading, self.cfg.reload_timeout)

    def on_enter(self, *args):
        """
            进入Screen
        :param args:
        :return:
        """

        self.main.on_main(self.TITLE)

        self.nav.clear_buttons()
        self.nav.add_main_button('refresh', self.load_devices)
        self.nav.add_main_button('wifi-plus', self.cb__connect_to_wireless)

        self.auto_loading()
