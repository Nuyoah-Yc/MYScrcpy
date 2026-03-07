# -*- coding: utf-8 -*-
"""
    mouse_handler
    ~~~~~~~~~~~~~~~~~~
    
    Log:
        2026-01-30 0.1.0 Me2sY 创建
"""

__author__ = 'Me2sY'
__version__ = '0.1.0'

__all__ = [
    'EnumMouseMode',
    'MYMouseController'
]

from dataclasses import dataclass, asdict
from enum import StrEnum
import time
from typing import Optional

from kivy.core.window import Window
from kivy.graphics import Color, Ellipse
from kivy.input.providers.mouse import MouseMotionEvent
from kivy.logger import Logger
from kivy.metrics import Metrics
from kivy.utils import platform
from kivymd.uix.widget import MDWidget

from pynput import mouse

from mysc.core.control import ControlAdapter
from mysc.core.device import MYDevice
from mysc.gui.k.components.base.my_snack_bar import MYSnackBarWarning, MYSnackBarInfo
from mysc.gui.k.components.base.my_radial_menu import MYRadialMenu
from mysc.utils.storage import JSONStorage
from mysc.utils.vector import ScalePointR
from mysc.utils.keys import EnumAction, ADBKeyCode
from mysc.gui.k.defs import init_language, CombineColors

_ = init_language()


class EnumMouseMode(StrEnum):
    Mouse = 'Mouse'
    Proxy = 'Proxy'


@dataclass
class JSMouse(JSONStorage):
    Prefix = 'Mouse'

    mode: EnumMouseMode = EnumMouseMode.Proxy
    touch_id_main: int = 0x413
    touch_id_wheel: int = 0x413 + 50
    touch_id_sec: int = 0x413 + 100

    running: bool = True

    um_mouse_id: int = 2
    um_move_speed: float = 1.5

    assistant_point_size: int = 16


@dataclass(slots=True)
class MouseButtonStatus:
    """
        鼠标按键状态
    """
    left_button: bool = False
    right_button: bool = False
    middle_button: bool = False


class MouseMode:

    def __init__(self, cfg: JSMouse, ca: ControlAdapter, is_supported: bool):
        """
            UHID 鼠标处理器
        :param cfg:
        :param ca:
        :param is_supported:
        """
        self.cfg = cfg
        self.ca: ControlAdapter = ca

        self.is_supported = is_supported

        self.is_activated: bool = False

        if self.is_supported and self.ca:
            self.mouse_controller = mouse.Controller()
            self.mb_status: MouseButtonStatus = MouseButtonStatus()
            self.ca.f_uhid_mouse_create(mouse_id=self.cfg.um_mouse_id)
            self.x: int = 1
            self.y: int = 1

    def activate(self):
        """
            激活 UHID 鼠标
        :return:
        """
        if self.is_supported and not self.is_activated:

            # Macosx 获取坐标与其他系统不同
            if platform == 'macosx':
                self.x = Window.width / Metrics.density / 2 + Window.left
                self.y = Window.height / Metrics.density / 2 + Window.top
            else:
                self.x = Window.left * Metrics.density + Window.width // 2
                self.y = Window.top * Metrics.density + Window.height // 2

            self.mouse_controller.position = (self.x, self.y)

            Window.bind(mouse_pos=self.move)
            Window.show_cursor = False
            Window.grab_mouse()

            self.is_activated = True

            return True

        else:
            Logger.warning(f"UHID Mouse Not Supported!")
            return False

    def deactivate(self):
        """
            取消激活
        :return:
        """
        if self.is_supported and self.is_activated:
            Window.unbind(mouse_pos=self.move)
            Window.ungrab_mouse()
            Window.show_cursor = True
            self.mb_status = MouseButtonStatus()
            self.is_activated = False
            self.cfg.dump()

    def move(self, instance, pos, *args, **kwargs):
        """
            监测 Windows Mouse Pos 改变事件
        :param instance:
        :param pos:
        :param args:
        :return:
        """
        pos = self.mouse_controller.position

        if 'dx' in kwargs and 'dy' in kwargs:
            dx, dy = kwargs['dx'], kwargs['dy']
        else:
            # 计算偏移值
            dx, dy = pos[0] - self.x, pos[1] - self.y

        if 'dx' not in kwargs:
            # 锁定归位
            self.mouse_controller.position = (self.x, self.y)

        try:
            self.ca.f_uhid_mouse_input(
                min(max(int(dx * self.cfg.um_move_speed), -127), 127),
                min(max(int(dy * self.cfg.um_move_speed), -127), 127),
                **asdict(self.mb_status), ignore_repeat_check=True)
        except:
            ...

    def touch_down(self, touch):
        """
            按键事件，配置mb_status
        :param touch:
        :return:
        """
        if not self.is_activated:
            return

        btn = {
            'left': 'left_button',
            'right': 'right_button',
            'middle': 'middle_button'
        }.get(touch.button, None)

        if btn:
            setattr(self.mb_status, btn, True)

        self.ca.f_uhid_mouse_input(
            0, 0,
            **asdict(self.mb_status),
            wheel_motion=0 if touch.button not in ['scrolldown', 'scrollup'] else
            (1 if touch.button == 'scrolldown' else -1),
        )

    def touch_up(self, touch):
        """
            按键释放
        :param touch:
        :return:
        """
        if not self.is_activated:
            return

        btn = {
            'left': 'left_button',
            'right': 'right_button',
            'middle': 'middle_button'
        }.get(touch.button, None)

        if btn:
            setattr(self.mb_status, btn, False)

        self.ca.f_uhid_mouse_input(0, 0, **asdict(self.mb_status))


class AssistantPoint:

    def __init__(self, cfg: JSMouse, ca: ControlAdapter, control_layer: MDWidget):
        """
            辅助点
        :param cfg:
        :param ca:
        :param control_layer:
        """
        self.cfg = cfg
        self.ca: ControlAdapter = ca
        self.control_layer = control_layer

        self.is_activated: bool = False

        self.pos: tuple[int, int] = (0, 0)

        self.spr: Optional[ScalePointR] = None
        self.center_spr: Optional[ScalePointR] = None
        self.next_spr: Optional[ScalePointR] = None

    def activate(self, pos, spr: ScalePointR):
        """
            激活辅助点
        :param pos:
        :param spr:
        :return:
        """
        self.is_activated and self.deactivate()

        self.is_activated = True

        self.pos = pos
        self.spr = spr

        with self.control_layer.canvas.after:
            Color(0xff, 0xa5, 0)
            self.ellipse = Ellipse(
                pos=(self.pos[0] - self.cfg.assistant_point_size / 2, self.pos[1] - self.cfg.assistant_point_size / 2),
                size=(self.cfg.assistant_point_size, self.cfg.assistant_point_size),
            )

    def deactivate(self):
        """
            失活辅助点
        :return:
        """
        self.is_activated = False
        try:
            self.control_layer.canvas.after.remove(self.ellipse)
        except:
            ...

    def on_touch_move(self, touch):
        """

        :param touch:
        :return:
        """
        if not self.is_activated or touch.button != 'left': return

        main_next_spr = touch.ud['spr']

        next_spr_x = 2 * self.center_spr.x - main_next_spr.x
        next_spr_y = 2 * self.center_spr.y - main_next_spr.y

        self.next_spr = ScalePointR(next_spr_x, next_spr_y, main_next_spr.r)

        self.ca.f_touch_spr(
            EnumAction.MOVE, self.next_spr, self.cfg.touch_id_sec
        )

    def on_touch_down(self, touch):
        """
            主键按下，同步按下
        :param touch:
        :return:
        """
        if not self.is_activated or touch.button != 'left': return

        self.center_spr = ScalePointR(
            (self.spr.x + touch.ud['spr'].x) / 2,
            (self.spr.y + touch.ud['spr'].y) / 2,
            self.spr.r
        )
        self.ca.f_touch_spr(EnumAction.DOWN, self.spr, self.cfg.touch_id_sec)

    def on_touch_up(self, touch):
        """
            主键释放，随之释放
        :param touch:
        :return:
        """
        if not self.is_activated or touch.button != 'left': return

        self.ca.f_touch_spr(EnumAction.UP, self.next_spr, self.cfg.touch_id_sec)


class WheelHandler:

    def __init__(self, cfg: JSMouse, ca: ControlAdapter, control_layer):
        """
            滚轮控制器
        :param cfg:
        :param ca:
        """
        self.cfg = cfg
        self.ca: ControlAdapter = ca
        self.control_layer: MDWidget = control_layer

    def on_touch(self, touch: MouseMotionEvent):
        """
            Wheel
            翻页功能
            Ctrl + Wheel 放大缩小功能

            滚轮采用模拟触控上滑方式
        :param touch:
        :return:
        """
        if touch.button not in ['scrollup', 'scrolldown']: return
        if not self.control_layer.collide_point(*touch.pos): return

        is_swipe = 'ctrl' in Window.modifiers
        spr = touch.ud['spr']

        if is_swipe:

            # 创建第二个点 用于缩放
            if touch.button == 'scrollup':
                spr2 = spr + ScalePointR(
                    0.2, -0.2, spr.r
                )
            else:
                spr2 = spr + ScalePointR(
                    0.05, -0.05, spr.r
                )

            self.ca.f_touch_spr(EnumAction.DOWN, spr, self.cfg.touch_id_wheel)
            self.ca.f_touch_spr(EnumAction.DOWN, spr2, self.cfg.touch_id_wheel + 5)

            for _ in range(30):
                _spr = spr2 + ScalePointR(
                    0.004 * _ * (-1 if touch.button == 'scrollup' else 1),
                    0.004 * _ * (1 if touch.button == 'scrollup' else -1),
                    spr.r
                )
                self.ca.f_touch_spr(EnumAction.MOVE, _spr, self.cfg.touch_id_wheel + 5)
                time.sleep(0.005)

            self.ca.f_touch_spr(EnumAction.UP, _spr, self.cfg.touch_id_wheel + 5)
            self.ca.f_touch_spr(EnumAction.UP, spr, self.cfg.touch_id_wheel)

        else:
            # 模拟滑动模式
            self.ca.f_touch_spr(EnumAction.DOWN, spr, self.cfg.touch_id_wheel)
            for step in range(20):
                _last_spr = spr + ScalePointR(
                    0, 0.002 * step * (1 if touch.button == 'scrolldown' else -1), spr.r
                )
                self.ca.f_touch_spr(
                    EnumAction.MOVE,
                    _last_spr,
                    self.cfg.touch_id_wheel
                )
                time.sleep(0.001)
            self.ca.f_touch_spr(EnumAction.UP, _last_spr, self.cfg.touch_id_wheel)


class TouchMode:

    def __init__(self, cfg: JSMouse, ca: ControlAdapter):
        """
            触摸处理器
        :param cfg:
        :param ca:
        """
        self.cfg = cfg
        self.ca: ControlAdapter = ca

    def on_touch_down(self, touch: MouseMotionEvent):
        """
            按下
        :param touch:
        :return:
        """
        if touch.button == 'left':
            self.ca.f_touch_spr(
                EnumAction.DOWN, touch.ud['spr'], self.cfg.touch_id_main
            )

    def on_touch_move(self, touch: MouseMotionEvent):
        """
            移动
        :param touch:
        :return:
        """
        if touch.button == 'left':
            self.ca.f_touch_spr(
                EnumAction.MOVE, touch.ud['spr'], self.cfg.touch_id_main
            )

    def on_touch_up(self, touch: MouseMotionEvent):
        """
            释放
        :param touch:
        :return:
        """
        if touch.button == 'left':
            self.ca.f_touch_spr(
                EnumAction.UP, touch.ud['spr'], self.cfg.touch_id_main
            )


class MYMouseController:

    def __init__(self, control_layer):

        self.control_layer = control_layer
        self.ca: ControlAdapter = control_layer.ca

        self.is_activated: bool = True

        self.my_device: MYDevice = self.control_layer.my_device

        self.cfg_cls = JSMouse.get_cls(StoragePath=self.control_layer.screen.cfg.StoragePath)
        self.cfg: JSMouse = self.cfg_cls.load(self.control_layer.screen.cfg.save_key)
        if self.cfg is None:
            self.cfg = self.cfg_cls(save_key=self.control_layer.screen.cfg.save_key)

        self.touch_handler = TouchMode(self.cfg, self.ca)
        self.wheel_handler = WheelHandler(self.cfg, self.ca, self.control_layer)
        self.uhid_mouse_handler = MouseMode(self.cfg, self.ca, self.my_device.device_info.is_uhid_supported)
        self.assistant_point = AssistantPoint(self.cfg,  self.ca, self.control_layer)

        self.radial_menu = MYRadialMenu(
            self.cb__radial_select,
            ["SPoint", "SShot", "...", "Switch", "Back", "Home"]
        )

    def update_btn_style(self):
        """
            更新控制按键风格
        :return:
        """
        self.switch_btn.theme_bg_color = 'Custom'
        self.switch_btn.theme_icon_color = 'Custom'

        _color = CombineColors.blue if self.cfg.mode == EnumMouseMode.Mouse else CombineColors.orange

        self.switch_btn.icon = 'mouse' if self.cfg.mode == EnumMouseMode.Mouse else 'gesture-tap'
        self.switch_btn.md_bg_color = _color.value[0]
        self.switch_btn.icon_color = _color.value[1]

    def activate(self):
        """
            激活
        :return:
        """
        if not self.is_activated: return

        if self.cfg.mode == EnumMouseMode.Mouse:
            if not self.uhid_mouse_handler.activate():
                self.cfg.mode = EnumMouseMode.Proxy

        self.switch_btn = self.control_layer.nav.add_main_button('mouse', lambda caller: self.switch_mode())
        self.update_btn_style()

        if self.radial_menu not in self.control_layer.children:
            self.control_layer.add_widget(self.radial_menu, canvas='after')

    def deactivate(self):
        """
            失活
        :return:
        """
        if not self.is_activated: return

        if self.cfg.mode == EnumMouseMode.Mouse:
            self.uhid_mouse_handler.deactivate()
        else:
            self.assistant_point.deactivate()

        self.switch_btn in self.control_layer.nav.children and self.control_layer.nav.remove_widget(self.switch_btn)

    def switch_mode(self, mode: Optional[EnumMouseMode] = None):
        """
            切换鼠标模式
        :param mode:
        :return:
        """
        if mode:
            # 当前模式，无需切换
            if mode == self.cfg.mode:
                return
        else:
            self.cfg.mode = EnumMouseMode.Proxy if self.cfg.mode == EnumMouseMode.Mouse else EnumMouseMode.Mouse

        if self.cfg.mode == EnumMouseMode.Mouse:
            if not self.control_layer.my_device.device_info.is_uhid_supported:
                MYSnackBarWarning(_('Device Not Support UHID Mode!'))
                self.cfg.mode = EnumMouseMode.Proxy
            else:
                # 激活 UHID 模式
                self.uhid_mouse_handler.activate()

        else:
            # 激活 Touch 模式
            self.uhid_mouse_handler.deactivate()

        self.update_btn_style()

        self.cfg.dump()

        MYSnackBarInfo(
            _('Mouse Touch Mode. Mouse Middle Switch') if self.cfg.mode == EnumMouseMode.Proxy
            else _('Mouse UHID Mode. Mouse Middle Key Switch'),
            color=CombineColors.blue if self.cfg.mode == EnumMouseMode.Mouse else CombineColors.orange,
        )

    def on_touch_down(self, touch: MouseMotionEvent):
        """
            绑定触摸按下事件
        :param touch:
        :return:
        """
        if self.cfg.mode == EnumMouseMode.Proxy:
            if touch.button == 'middle':
                self.switch_mode()
                return

            self.touch_handler.on_touch_down(touch)
            self.assistant_point.on_touch_down(touch)

            if touch.button == 'right':
                self.radial_menu.open_menu(touch.ud['local_pos'], touch.ud['spr'])

        elif self.cfg.mode == EnumMouseMode.Mouse:
            if touch.button == 'middle':
                self.switch_mode()
            else:
                self.uhid_mouse_handler.touch_down(touch)

    def on_touch_up(self, touch: MouseMotionEvent):
        """
            绑定触摸释放事件
        :param touch:
        :return:
        """
        if self.cfg.mode == EnumMouseMode.Proxy:
            self.touch_handler.on_touch_up(touch)
            self.wheel_handler.on_touch(touch)
            self.assistant_point.on_touch_up(touch)

            if touch.button == 'right':
                self.radial_menu.close_menu()

        elif self.cfg.mode == EnumMouseMode.Mouse:
            self.uhid_mouse_handler.touch_up(touch)

    def on_touch_move(self, touch: MouseMotionEvent):
        """
            绑定触摸移动事件
        :param touch:
        :return:
        """
        if self.cfg.mode == EnumMouseMode.Proxy:
            self.touch_handler.on_touch_move(touch)
            self.assistant_point.on_touch_move(touch)
            self.radial_menu.on_mouse_move(touch.ud['local_pos'])

    def cb__radial_select(self, item_index: int, item_name: str):
        """
            功能回调
        :param item_index:
        :param item_name:
        :return:
        """
        if item_name == 'SPoint':
            if self.assistant_point.is_activated:
                self.assistant_point.deactivate()
            else:
                self.assistant_point.activate(
                    (
                        self.radial_menu.center_x,
                        self.radial_menu.center_y
                    ),
                    self.radial_menu.spr
                )

        elif item_name == 'Back':
            self.my_device.adb_device.keyevent(ADBKeyCode.BACK)

        elif item_name == 'Home':
            self.my_device.adb_device.keyevent(ADBKeyCode.HOME)

        elif item_name == 'Switch':
            self.my_device.adb_device.keyevent(ADBKeyCode.APP_SWITCH)

        elif item_name == 'SShot':
            self.my_device.adb_device.keyevent(ADBKeyCode.KB_PRINTSCREEN)