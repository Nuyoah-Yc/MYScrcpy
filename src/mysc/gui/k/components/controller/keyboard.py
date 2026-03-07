# -*- coding: utf-8 -*-
"""
    keyboard
    ~~~~~~~~~~~~~~~~~~
    
    Log:
        2026-02-09 0.1.0 Me2sY 创建
"""

__author__ = 'Me2sY'
__version__ = '0.1.0'

__all__ = [
    'EnumKeyboardMode', 'JSKeyboard',
    'ActionCallback', 'MYKeyboardController'
]

from dataclasses import dataclass, field
from enum import StrEnum
import pathlib
import threading
from typing import Optional, Callable, Self

from kivy.core.window import Window

from mysc.core.control import ControlAdapter, KeyboardWatcher
from mysc.core.device import MYDevice
from mysc.gui.k.components.base.my_navigation import MYNavigation
from mysc.gui.k.components.base.my_snack_bar import MYSnackBarInfo
from mysc.gui.k.defs import init_language, CombineColors
from mysc.utils.keys import UnifiedKeys, UnifiedKey, ADBKeyCode, EnumAction
from mysc.utils.storage import JSONStorage
from mysc.gui.k import KeyMapper

_ = init_language()


class EnumKeyboardMode(StrEnum):
    Keyboard = 'Keyboard'
    Proxy = 'Proxy'


@dataclass
class JSKeyboard(JSONStorage):
    Prefix = 'KB_'

    mode: EnumKeyboardMode = EnumKeyboardMode.Keyboard
    uk_keyboard_id: int = 1
    uk_mode_switch_key: int = UnifiedKeys.UK_KB_F8.code


@dataclass
class ActionCallback:
    """
        Keyboard Action Callback
    """
    action: EnumAction
    key_code: int
    uk: UnifiedKey
    modifiers: list[UnifiedKey] = field(default_factory=list)


class InputMode:

    def __init__(self, keyboard_id: int, my_device: MYDevice, ca: Optional[ControlAdapter] = None):
        """
            输入模式，
            若支持 uhid，则使用 uhid 模式输入
            否则模拟 ADB 模式
        :param keyboard_id:
        :param my_device:
        :param ca:
        """
        self.my_device = my_device
        self.ca = ca

        self.keyboard_id = keyboard_id
        self.is_supported = self.my_device.device_info.is_uhid_supported

        # 创建 键盘按键监视器
        self.watcher = KeyboardWatcher(self.uhid_send)
        self.watcher.clear()

        # 创建 UHID 键盘
        if self.is_supported and self.ca:
            self.ca.f_uhid_keyboard_create(keyboard_id=self.keyboard_id)

    def uhid_send(self, modifiers, key_scan_codes):
        """
            UHID Key 发送方法
        :param modifiers:
        :param key_scan_codes:
        :return:
        """
        if not self.is_supported or self.ca is None: return

        self.ca.f_uhid_keyboard_input(
            keyboard_id=self.keyboard_id, modifiers=modifiers, key_scan_codes=key_scan_codes
        )

    def key_down(self, uk: UnifiedKey):
        """
            按键按下
        :param uk:
        :return:
        """
        if self.is_supported and self.ca:
            self.watcher.key_pressed(uk)
        else:
            # 组合键时通过Window.modifiers判断
            if uk not in [
                UnifiedKeys.UK_KB_CONTROL, UnifiedKeys.UK_KB_CONTROL_L, UnifiedKeys.UK_KB_CONTROL_R,
                UnifiedKeys.UK_KB_SHIFT, UnifiedKeys.UK_KB_SHIFT_L, UnifiedKeys.UK_KB_SHIFT_R,
                UnifiedKeys.UK_KB_ALT, UnifiedKeys.UK_KB_ALT_L, UnifiedKeys.UK_KB_ALT_R
            ]:
                self.adb_keydown(uk)

    def key_up(self, uk: UnifiedKey):
        """
            按键释放
        :param uk:
        :return:
        """
        self.watcher.key_release(uk)

    def adb_keydown(self, key: UnifiedKey):
        """
            ADB 模拟组合键
        :param key:
        :return:
        """
        func_down = ''

        for _ in Window.modifiers:
            fn = {
                'ctrl': ADBKeyCode.KB_CONTROL_L,
                'shift': ADBKeyCode.KB_SHIFT_L,
                'alt': ADBKeyCode.KB_ALT_L,
            }.get(_, None)
            if fn:
                func_down += f'{fn}'

        if func_down:
            t = self.my_device.adb_device.shell
            args = (f"input keycombination {func_down} {KeyMapper.uk2adb(key)}", )

        else:
            t = self.my_device.adb_device.keyevent
            args = (KeyMapper.uk2adb(key), )

        threading.Thread(target=t, args=args, daemon=True).start()


class MYKeyboardController:

    def __init__(
            self,
            my_device: MYDevice, mode, nav: MYNavigation,
            ca: Optional[ControlAdapter] = None,
            cb__proxy: Optional[Callable[[Self, ActionCallback], None]] = None,
    ):
        self.my_device = my_device
        self.mode = mode
        self.nav = nav
        self.ca = ca
        self.cb__proxy = cb__proxy

        self.cfg_cls = JSKeyboard.get_cls(StoragePath=pathlib.Path(f"{self.my_device.serial_no}"))
        self.cfg: JSKeyboard = self.cfg_cls.load(self.mode.save_key)
        if self.cfg is None:
            self.cfg = self.cfg_cls(save_key=self.mode.save_key)

        self.input_mode = InputMode(self.cfg.uk_keyboard_id, self.my_device, self.ca)

        # 预留按键
        self.reserved_keys: dict[UnifiedKey, Callable[[ActionCallback], None]] = {
            UnifiedKeys.get_by_code(self.cfg.uk_mode_switch_key): lambda
                ac: ac.action == EnumAction.UP and self.switch_mode(),
        }

    def switch_mode(self, mode: Optional[EnumKeyboardMode] = None):
        """
            切换工作模式
        :param mode:
        :return:
        """
        if mode is None:
            self.cfg.mode = EnumKeyboardMode.Keyboard if (
                    self.cfg.mode == EnumKeyboardMode.Proxy
            ) else EnumKeyboardMode.Proxy

        else:
            self.cfg.mode = mode

        self.cfg.dump()

        self.update_btn_style()

        MYSnackBarInfo(
            f"{_('Input') if self.cfg.mode == EnumKeyboardMode.Keyboard else _('Proxy')}" + _('Mode. Press F8 Switch Mode.'),
            color=CombineColors.orange if self.cfg.mode == EnumKeyboardMode.Keyboard else CombineColors.blue,
        )

    def activate(self):
        """
            激活
        :return:
        """
        # 添加控制按钮
        self.switch_btn = self.nav.add_main_button('keyboard', lambda caller: self.switch_mode())

        # 设置按钮样式
        self.switch_btn.theme_bg_color = 'Custom'
        self.switch_btn.theme_icon_color = 'Custom'
        self.update_btn_style()

    def deactivate(self):
        """
            失活
        :return:
        """
        self.cfg.dump()

    def update_btn_style(self):
        """
            更新按钮样式
        :return:
        """
        _color = CombineColors.orange if self.cfg.mode == EnumKeyboardMode.Proxy else CombineColors.blue

        self.switch_btn.icon = 'controller' if self.cfg.mode == EnumKeyboardMode.Proxy else 'keyboard'
        self.switch_btn.md_bg_color = _color.value[0]
        self.switch_btn.icon_color = _color.value[1]

    def on_key_down(self, uk: UnifiedKey, keycode: int, modifiers):
        """
            按键按下
        :param uk:
        :param keycode:
        :param modifiers:
        :return:
        """
        # 预留键位
        if uk in self.reserved_keys: self.reserved_keys[uk](
            ActionCallback(action=EnumAction.DOWN, uk=uk, modifiers=modifiers, key_code=keycode)
        )

        # 键盘输入模式
        elif self.cfg.mode == EnumKeyboardMode.Keyboard: self.input_mode.key_down(uk)

        # Proxy 模式
        elif self.cfg.mode == EnumKeyboardMode.Proxy and self.cb__proxy: self.cb__proxy(
            self, ActionCallback(action=EnumAction.DOWN, uk=uk, modifiers=modifiers, key_code=keycode)
        )

    def on_key_up(self, uk: UnifiedKey, keycode: int, modifiers):
        """
            按键释放
        :param uk:
        :param keycode:
        :param modifiers:
        :return:
        """
        # 预留键位
        if uk in self.reserved_keys: self.reserved_keys[uk](
            ActionCallback(action=EnumAction.UP, uk=uk, modifiers=modifiers, key_code=keycode)
        )

        # 键盘输入模式
        elif self.cfg.mode == EnumKeyboardMode.Keyboard: self.input_mode.key_up(uk)

        # Proxy 模式
        elif self.cfg.mode == EnumKeyboardMode.Proxy and self.cb__proxy: self.cb__proxy(
            self, ActionCallback(action=EnumAction.UP, uk=uk, modifiers=modifiers, key_code=keycode)
        )

    def register_key_callback(self, key: UnifiedKey, callback: Callable):
        """
            注册按键回调
        :param key:
        :param callback:
        :return:
        """
        self.reserved_keys[key] = callback
