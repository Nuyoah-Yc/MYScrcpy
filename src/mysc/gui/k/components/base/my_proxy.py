# -*- coding: utf-8 -*-
"""
    按键代理
    ~~~~~~~~~~~~~~~~~~
    
    Log:
        2026-02-12 0.1.0 Me2sY 创建
"""

__author__ = 'Me2sY'
__version__ = '0.1.0'

__all__ = [
    'EnumMode', 'JSProxyGroup',
    'Proxy', 'ProxyDict',
    'ProxyGroup',
]

from dataclasses import dataclass, field
from enum import StrEnum
from functools import wraps, partial
import math
import pathlib
import random
import time
from typing import ClassVar, Optional, Any, Callable, Self

from kivy._clock import ClockEvent
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Line
from kivy.input.providers.mouse import MouseMotionEvent
from kivy.metrics import dp, Metrics
from kivy.uix.modalview import ModalView
from kivy.utils import platform
from kivymd.uix.badge import MDBadge
from kivymd.uix.button import MDButton, MDButtonText
from kivymd.uix.dialog import (
    MDDialog, MDDialogHeadlineText, MDDialogContentContainer, MDDialogButtonContainer, MDDialogSupportingText
)
from kivymd.uix.dropdownitem import MDDropDownItem, MDDropDownItemText
from kivymd.uix.gridlayout import MDGridLayout
from kivymd.uix.label import MDIcon, MDLabel
from kivymd.uix.menu import MDDropdownMenu
from kivymd.uix.progressindicator import MDCircularProgressIndicator
from kivymd.uix.selectioncontrol import MDCheckbox
from kivymd.uix.slider import MDSlider, MDSliderHandle
from kivymd.uix.textfield import MDTextField, MDTextFieldHintText
from kivymd.uix.widget import MDWidget

import numpy as np

from pynput.mouse import Controller as MouseController, Listener as MouseListener, Button

from mysc.core.control import ControlAdapter
from mysc.gui.k import KeyMapper
from mysc.gui.k.components.base.my_snack_bar import MYSnackBarError, MYSnackBarWarning
from mysc.gui.k.defs import init_language, CombineColors, Colors
from mysc.utils.keys import UnifiedKey, UnifiedKeys, EnumAction
from mysc.utils.storage import JSONStorage
from mysc.utils.vector import ScalePointR, EnumDirection

_ = init_language()


@dataclass
class JSProxyGroup(JSONStorage):

    StoragePath = pathlib.Path('proxies')

    is_default: bool = False

    proxies: list[dict[str, Any]] = field(default_factory=list)


class SetUKButton(MDButton):

    def __init__(
            self, uk: UnifiedKey, key_changed_callback: Callable[[Optional[UnifiedKey]], bool], **kwargs):
        """
            设置按键控件
        :param uk:
        :param key_changed_callback:
        :param kwargs:
        """
        kwargs.setdefault('style', 'filled')
        super().__init__(**kwargs)

        self.uk: UnifiedKey = uk
        self.key_changed_callback: Callable = key_changed_callback

        self.btn_text = MDButtonText(
            text=_('Bind') if self.uk is UnifiedKeys.UK_UNKNOWN else (
                str(self.uk.value) if self.uk.value is not None else str(self.uk.name)
            )
        )
        self.add_widget(self.btn_text)

        self.bind(on_release=self.bind_key)

    def bind_key(self, *args):
        """
            绑定按键
        :return:
        """
        mv = ModalView(auto_dismiss=False)
        mv.add_widget(
            MDLabel(text=_('Press Key.\nEsc to escape.'), halign='center', theme_text_color='Custom', text_color='white'))
        mv.add_widget(
            MDCircularProgressIndicator(size_hint=(.3, .3))
        )

        def mouse(instance, touch):
            """
                鼠标按键
            :param instance:
            :param touch:
            :return:
            """
            mv.dismiss()
            _keyboard.unbind(on_key_down=_callback)
            _keyboard.release()

            try:
                set_key({
                    'left': UnifiedKeys.UK_MOUSE_L,
                    'right': UnifiedKeys.UK_MOUSE_R,
                    'middle': UnifiedKeys.UK_MOUSE_WHEEL,
                    'scrollup': UnifiedKeys.UK_MOUSE_WHEEL_UP,
                    'scrolldown': UnifiedKeys.UK_MOUSE_WHEEL_DOWN,
                }.get(touch.button))
            except KeyError:
                ...

        mv.bind(on_touch_down=mouse)

        mv.open()

        def _callback(*_args):
            """
                停止键盘响应，判断是否为esc并发起回调
            :param args:
            :return:
            """
            _keyboard.unbind(on_key_down=_callback)
            _keyboard.release()
            mv.dismiss()

            if _args[1][1] not in ['escape', 'F1']:
                set_key(KeyMapper.ky2uk(_args[1][0]))
            else:
                set_key(self.uk)

        def set_key(uk: UnifiedKey):
            """
                设置按键
            :param uk:
            :return:
            """
            if uk == self.uk:
                MYSnackBarWarning(_('Not Changed'))
                return

            if self.key_changed_callback(uk):
                self.uk = uk
                self.btn_text.text = str(uk.value) if uk.value is not None else str(uk.name)

        # 注册键盘响应
        _keyboard = Window.request_keyboard(lambda *_args: ..., mv, 'text', False)
        _keyboard.bind(on_key_down=_callback)


class SettingDialog(MDDialog):

    def __init__(self, indicator_type_name: str, **kwargs):
        """
            设置窗口
        :param kwargs:
        """
        super().__init__(**kwargs)

        self.add_widget(MDDialogHeadlineText(text=_('Button')))
        self.add_widget(MDDialogSupportingText(text=indicator_type_name))

        self.container = MDDialogContentContainer(orientation='vertical', spacing=dp(10))
        self.add_widget(self.container)

        self.add_widget(
            MDDialogButtonContainer(
                MDWidget(), MDButton(MDButtonText(text=_('Close')), style='text', on_release=self.dismiss),
            )
        )

    def save(self, *args):
        raise NotImplementedError()


class Proxy(MDWidget):

    NAME: ClassVar[str] = _('Indicator')
    ICON_COLOR: ClassVar[str] = Colors.Orange
    ICON: ClassVar[str] = 'gesture-tap'
    TYPE_KEY: ClassVar[str] = ''

    # 调整按键随机范围
    SIM_X_UNIFORM_A: ClassVar[float] = -0.01
    SIM_X_UNIFORM_B: ClassVar[float] = 0.01
    SIM_Y_UNIFORM_A: ClassVar[float] = -0.01
    SIM_Y_UNIFORM_B: ClassVar[float] = 0.01

    @staticmethod
    def get_validate(instance: object, attr: str, value_type, ipt_instance, value):
        """
            获取指定类型值
        :param instance:
        :param attr:
        :param value_type: 值类型
        :param ipt_instance:
        :param value:
        :return:
        """
        try:
            setattr(instance, attr, value_type(value))
        except Exception as e:
            ipt_instance.error = True
            ipt_instance.text = ipt_instance.text[:-1]

    @property
    def uks(self) -> list[UnifiedKey]:
        """
            控件激活按键
        :return:
        """
        uks = []
        for key, obj in self.__dict__.items():
            if key.startswith('uk') and obj is not None and obj != UnifiedKeys.UK_UNKNOWN:
                uks.append(obj)
        return uks

    def __init__(
            self,
            touch_id: int, spr: ScalePointR, proxy_group: 'ProxyGroup',
            cb__bind_key: Callable[[UnifiedKey, Self], bool],
            cb__delete: Callable[[Self], ...],
            cb__move: Callable[[Self], None],
            uk: Optional[UnifiedKey] = None,
            **kwargs
    ):
        # 初始化
        kwargs.setdefault('size_hint', (None, None))
        kwargs.setdefault('size', (dp(60), dp(60)))

        # 模拟随机位置按键
        self.var__simulate = kwargs.pop('var__simulate', True)

        # 自动释放鼠标
        self.var__release_mouse = kwargs.pop('var__release_mouse', False)
        self._touch_holder: Optional[ButtonAim] = None

        super().__init__(**kwargs)

        self.touch_id = touch_id
        self._spr: ScalePointR = spr
        self._spr_r: ScalePointR = spr
        self.proxy_group = proxy_group

        self.cb__bind_key = cb__bind_key
        self.cb__delete = cb__delete
        self.cb__move = cb__move

        self.uk: UnifiedKey = UnifiedKeys.UK_UNKNOWN if uk is None else uk

        # 定义指示器
        self.badge = MDBadge()
        if self.uk is not UnifiedKeys.UK_UNKNOWN:
            self.badge.text = str(self.uk.value if self.uk.value is not None else self.uk.name)

        self.icon = MDIcon(self.badge, icon=self.ICON, icon_color=self.ICON_COLOR)
        self.add_widget(self.icon, canvas='before')
        self.bind(center=lambda instance, center: setattr(self.icon, 'center', center))

        self.is_selected: bool = False
        self.is_pressed: bool = False

        # 定义功能菜单
        self.menu = self.create__dropdown_menu()

    def spr(self, simulate: bool = True) -> ScalePointR:
        """
            模拟随机
        :return:
        """
        if self.var__simulate:
            if simulate:
                self._spr_r = self._spr + ScalePointR(
                    random.uniform(self.SIM_X_UNIFORM_A, self.SIM_X_UNIFORM_B),
                    random.uniform(self.SIM_Y_UNIFORM_A, self.SIM_Y_UNIFORM_B),
                    self._spr.r
                )
            return self._spr_r
        else:
            return self._spr

    def create__dropdown_menu(self) -> MDDropdownMenu:
        """
            创建功能菜单
        :return:
        """
        mdm = MDDropdownMenu(caller=self)

        items = [
            dict(text=_('Setup'), leading_icon='cog', on_release=lambda *args: mdm.dismiss() or self.create__setup_dialog()),
            dict(text=_('Delete'), leading_icon='delete', on_release=lambda *args: mdm.dismiss() or self.cb__delete(self)),
            dict(text=_('Lock'), leading_icon='lock', on_release=lambda *args: mdm.dismiss() or self.lock_switch()),
        ]

        mdm.items = items

        return mdm

    def update_pos(self, parent_widget: MDWidget, direction: EnumDirection):
        """
            更新位置
        :param parent_widget:
        :param direction:
        :return:
        """
        self._spr = self._spr.with_direction(direction)
        self.center = (
            self._spr.x * parent_widget.width + parent_widget.x,
            (1 - self._spr.y) * parent_widget.height + parent_widget.y
        )

    @classmethod
    def load(
            cls,
            touch_id: int, spr: ScalePointR, proxy_group: 'ProxyGroup',
            cb__bind_key: Callable[[UnifiedKey, Self], bool],
            cb__delete: Callable[[Self], ...],
            cb__move: Callable[[Self], ...],
            uk: Optional[UnifiedKey] = None,
            **kwargs
    ) -> Self: return cls(
        touch_id=touch_id, spr=spr, proxy_group=proxy_group,
        cb__bind_key=cb__bind_key, cb__delete=cb__delete, cb__move=cb__move,
        uk=uk, **kwargs
    )

    def dump(self) -> dict:
        """
            转储
        :return:
        """
        return {_key: _value for _key, _value in self.__dict__.items() if _key.startswith('var__')}

    def inject_setting_details(self, container: MDDialogContentContainer):
        """
            注入设置详情
        :param container:
        :return:
        """

    def create__setup_dialog(self):
        """
            创建设置窗口
        :return:
        """
        setting_dialog = SettingDialog(self.NAME)
        content = MDGridLayout(cols=4, adaptive_height=True, spacing=dp(30))
        setting_dialog.container.add_widget(content)

        # 配置按键列
        content.add_widget(MDLabel(text=_('Key'), size_hint=(None, 1), width=dp(120)))
        content.add_widget(SetUKButton(self.uk, self.bind_key))

        # 占位
        content.add_widget(MDWidget())
        content.add_widget(MDWidget())

        # 模拟操作
        content.add_widget(MDLabel(text=_('Simulate'), size_hint=(None, 1), width=dp(120)))
        content.add_widget(MDCheckbox(
            active=self.var__simulate,
            on_active=lambda instance, is_simulate: setattr(self, 'var__simulate', is_simulate),
        ))

        # 自动释放鼠标
        content.add_widget(MDLabel(text=_('Free Mouse'), size_hint=(None, 1), width=dp(120)))
        content.add_widget(MDCheckbox(
            active=self.var__release_mouse,
            on_active=lambda instance, is_release: setattr(self, 'var__release_mouse', is_release),
        ))

        self.inject_setting_details(setting_dialog.container)

        setting_dialog.open()

    def cb__release_mouse(self):
        """
            释放鼠标
        :return:
        """
        if self.proxy_group.touch_holder and isinstance(self.proxy_group.touch_holder, (
            ButtonAim, ButtonAimLinux
        )):
            self._touch_holder = self.proxy_group.touch_holder
            self._touch_holder.deactivate()
            self.proxy_group.touch_holder = None

    def cb__return_mouse(self):
        """
            归还鼠标控制
        """
        if self._touch_holder and self.proxy_group.touch_holder is None:
            self.proxy_group.touch_holder = self._touch_holder
            self._touch_holder.activate()

        self._touch_holder = None

    def bind_key(self, uk: Optional[UnifiedKey]) -> bool:
        """
            绑定按键
        :param uk:
        :return:
        """
        if uk is None:
            MYSnackBarError(_('Bind Error!'), color=CombineColors.red, duration=1)
            return False

        if not self.cb__bind_key(uk, self):
            return False

        else:
            self.uk = uk
            self.badge.text = str(self.uk.value) if self.uk.value is not None else str(self.uk.name)
            return True

    def lock_switch(self):
        """
            切换锁定状态
        :return:
        """
        self.disabled = not self.disabled

    @staticmethod
    def check_status(func):
        """
            检查当前是否锁定
        :param func:
        :return:
        """
        @wraps(func)
        def wrapper(self, uk: UnifiedKey, touch):
            # 右键放行锁定切换功能
            if touch.button == 'right':
                return func(self, uk, touch)
            else:
                if self.disabled:
                    return None
                else:
                    return func(self, uk, touch)

        return wrapper

    @check_status
    def on_touch_down(self, uk: UnifiedKey, touch):
        """
            触摸响应
        :param uk:
        :param touch:
        :return:
        """
        if self.collide_point(*touch.pos):
            # 右键打开配置菜单
            if uk == UnifiedKeys.UK_MOUSE_R:
                self.menu.open()

            # 双击进入配置界面
            elif touch.is_double_tap:
                self.create__setup_dialog()

            # 进入移动状态
            else:
                self.is_selected = True
            return True
        else:
            self.is_selected = False
            return None

    @check_status
    def on_touch_move(self, uk: UnifiedKey, touch):
        """
            当前选中则移动
        :param uk:
        :param touch:
        :return:
        """
        if self.is_selected:
            self.center = self.to_parent(touch.x, touch.y)
            self.cb__move(self)

    @check_status
    def on_touch_up(self, uk: UnifiedKey,  touch):
        """
            释放
        :param uk:
        :param touch:
        :return:
        """
        self.is_selected = False

    def touch_down(self, uk: UnifiedKey, touch: MouseMotionEvent, ca: ControlAdapter):
        self.proxy_group.control_layer.my_mouse_controller.on_touch_down(touch)

    def touch_move(self, uk: UnifiedKey, touch: MouseMotionEvent, ca: ControlAdapter):
        self.proxy_group.control_layer.my_mouse_controller.on_touch_move(touch)

    def touch_up(self, uk: UnifiedKey, touch: MouseMotionEvent, ca: ControlAdapter):
        self.proxy_group.control_layer.my_mouse_controller.on_touch_up(touch)

    def key_down(self, uk: UnifiedKey, modifiers, ca: ControlAdapter): ...

    def key_up(self, uk: UnifiedKey, modifiers, ca: ControlAdapter): ...


class ButtonHold(Proxy):
    """
        持续按键，按键按下则屏幕按下，按键释放则屏幕释放
    """
    NAME = _('Hold')
    ICON_COLOR = Colors.Green
    ICON = 'gesture-tap-button'
    TYPE_KEY = 'button_hold'

    def key_down(self, uk: UnifiedKey, modifiers, ca: ControlAdapter):
        """
            按下
        :param uk:
        :param modifiers:
        :param ca:
        :return:
        """
        if self.is_pressed: return
        ca.f_touch_spr(EnumAction.DOWN, self.spr(), self.touch_id)
        self.is_pressed = True

        # 释放鼠标
        if self.var__release_mouse: self.cb__release_mouse()

    def key_up(self, uk: UnifiedKey, modifiers, ca: ControlAdapter):
        """
            释放
        :param uk:
        :param modifiers:
        :param ca:
        :return:
        """
        if not self.is_pressed: return
        ca.f_touch_spr(EnumAction.UP, self.spr(False), self.touch_id)
        self.is_pressed = False

        # 归还鼠标
        if self.var__release_mouse: self.cb__return_mouse()


class ButtonHoldSwitch(ButtonHold):
    """
        按下时释放鼠标，再次按下恢复
    """
    NAME = _('HoldSwitch')
    ICON_COLOR = Colors.GreenLight
    ICON = 'gesture-tap-button'
    TYPE_KEY = 'button_hold_switch'

    def __init__(self, **kwargs):

        # 自动吸附鼠标位置
        self.var__attach_mouse = kwargs.pop('var__attach_mouse', False)

        super().__init__(**kwargs)

        self.is_activated: bool = False

    def inject_setting_details(self, container: MDDialogContentContainer):
        """
            设置
        :param container:
        :return:
        """
        content = MDGridLayout(cols=2, adaptive_height=True, spacing=dp(10))
        content.add_widget(MDLabel(text=_('attach mouse'), size_hint=(None, 1), width=dp(120)))
        content.add_widget(MDCheckbox(
            active=self.var__attach_mouse,
            on_active=lambda instance, value: setattr(self, 'var__attach_mouse', value),
        ))

        container.add_widget(content)

    def key_down(self, uk: UnifiedKey, modifiers, ca: ControlAdapter):
        """
            按下
        :param uk:
        :param modifiers:
        :param ca:
        :return:
        """
        if self.is_pressed: return
        ca.f_touch_spr(EnumAction.DOWN, self.spr(), self.touch_id)
        self.is_pressed = True

    def key_up(self, uk: UnifiedKey, modifiers, ca: ControlAdapter):
        """
            释放
        :param uk:
        :param modifiers:
        :param ca:
        :return:
        """
        if not self.is_pressed: return
        ca.f_touch_spr(EnumAction.UP, self.spr(False), self.touch_id)
        self.is_pressed = False

        # 若未激活，则激活状态，同时释放鼠标瞄准状态，用于点选
        self.is_activated = not self.is_activated

        if self.is_activated:
            self.cb__release_mouse()

            # 吸附鼠标
            if self._touch_holder and self.var__attach_mouse:
                cl = self.proxy_group.control_layer
                x = Window.left * Metrics.density + (Window.width - cl.width) + cl.width * self._spr.x
                y = Window.top * Metrics.density + (Window.height - cl.height) + cl.height * self._spr.y
                time.sleep(1 / 120)
                self._touch_holder.mouse_controller.position = (x, y)
                time.sleep(1 / 120)

        else: self.cb__return_mouse()


class ButtonInstantly(Proxy):
    """
        立即按键，按键按下时立即触发一次，不等待释放
    """
    NAME = _('Instantly')
    ICON_COLOR = Colors.Orange
    ICON = 'lightning-bolt'
    TYPE_KEY = 'button_instantly'

    def __init__(self, **kwargs):
        self.var__hold_ms = kwargs.pop('var__hold_ms', 50)
        super().__init__(**kwargs)

    def inject_setting_details(self, container: MDDialogContentContainer):
        """
            设置持续时间
        :param container:
        :return:
        """
        content = MDGridLayout(cols=2, adaptive_height=True, spacing=dp(10))
        content.add_widget(MDLabel(text=_('hold ms'), size_hint=(None, 1), width=dp(120)))

        tf_hold_ms = MDTextField(MDTextFieldHintText(text=_('ms')), text=str(self.var__hold_ms), mode='filled')
        tf_hold_ms.bind(text=partial(self.get_validate, self, 'var__hold_ms', int))
        content.add_widget(tf_hold_ms)

        container.add_widget(content)

    def key_down(self, uk: UnifiedKey, modifiers, ca: ControlAdapter):
        """
            激活
        :param uk:
        :param modifiers:
        :param ca:
        :return:
        """
        if self.is_pressed: return

        ca.f_touch_spr(EnumAction.DOWN, self.spr(), self.touch_id)

        def _release(*_args):
            ca.f_touch_spr(EnumAction.UP, self.spr(False), self.touch_id)

        self.is_pressed = True
        Clock.schedule_once(_release, self.var__hold_ms / 1000)

    def key_up(self, uk: UnifiedKey, modifiers, ca: ControlAdapter):
        """
            按键释放
        """
        self.is_pressed = False


class ButtonRepeat(Proxy):
    """
        重复按键，按下后以一定间隔重复按键
    """
    NAME = _('Repeat')
    ICON_COLOR = Colors.Red
    ICON = 'timer-marker'
    TYPE_KEY = 'button_repeat'

    def __init__(self, **kwargs):
        self.var__hold_ms = kwargs.pop('var__hold_ms', 50)
        self.var__repeat_ms = kwargs.pop('var__repeat_ms', 500)

        super().__init__(**kwargs)

        self.run_interval: Optional[ClockEvent] = None

    def inject_setting_details(self, container: MDDialogContentContainer):
        """
            增加设置项
        :param container:
        :return:
        """
        content = MDGridLayout(cols=2, adaptive_height=True, spacing=dp(10))

        tf_hold_ms = MDTextField(MDTextFieldHintText(text=_('ms')), text=str(self.var__hold_ms), mode='filled')
        tf_hold_ms.bind(text=partial(self.get_validate, self, 'var__hold_ms', int))

        content.add_widget(MDLabel(text=_('hold ms'), size_hint=(None, 1), width=dp(120)))
        content.add_widget(tf_hold_ms)

        tf_repeat_ms = MDTextField(
            MDTextFieldHintText(text=_('repeat_ms')),
            text=str(self.var__repeat_ms),
            mode='filled'
        )
        tf_repeat_ms.bind(text=partial(self.get_validate, self, 'var__repeat_ms', int))

        content.add_widget(MDLabel(text=_('interval'), size_hint=(None, 1), width=dp(120)))
        content.add_widget(tf_repeat_ms)

        container.add_widget(content)

    def key_down(self, uk: UnifiedKey, modifiers, ca: ControlAdapter):
        """
            按键按下后，以repeat_ms为间隔重复按下
        :param uk:
        :param modifiers:
        :param ca:
        :return:
        """
        if self.is_pressed: return
        else: self.is_pressed = True

        def _release(*_args):
            ca.f_touch_spr(EnumAction.UP, self.spr(False), self.touch_id)

        def _down(*_args):
            ca.f_touch_spr(EnumAction.DOWN, self.spr(), self.touch_id)
            Clock.schedule_once(_release, self.var__hold_ms / 1000)

        _down()
        self.run_interval = Clock.schedule_interval(_down, (self.var__repeat_ms + self.var__hold_ms + 5) / 1000)

    def key_up(self, uk: UnifiedKey, modifiers, ca: ControlAdapter):
        """
            释放定时器
        :param uk:
        :param modifiers:
        :param ca:
        :return:
        """
        self.run_interval and self.run_interval.cancel()
        self.is_pressed = False


class ButtonSwitch(Proxy):
    """
        开关按钮
    """
    NAME = _('Switch')
    ICON_COLOR = Colors.Blue
    ICON = 'toggle-switch'
    TYPE_KEY = 'button_switch'

    def key_up(self, uk: UnifiedKey, modifiers, ca: ControlAdapter):
        """
            开关按钮，按下后切换开关状态
        :param uk:
        :param modifiers:
        :param ca:
        :return:
        """
        ca.f_touch_spr(
            EnumAction.UP if self.is_pressed else EnumAction.DOWN,
            self.spr(not self.is_pressed),
            self.touch_id
        )
        self.is_pressed = not self.is_pressed


class ButtonAim(Proxy):
    """
        瞄准按钮
    """
    NAME = _('Aim')
    ICON_COLOR = Colors.Yellow
    ICON = 'target-account'
    TYPE_KEY = 'button_aim'

    MOUSE_BUTTON_MAP = {
        Button.left: UnifiedKeys.UK_MOUSE_L,
        Button.right: UnifiedKeys.UK_MOUSE_R,
        Button.middle: UnifiedKeys.UK_MOUSE_WHEEL
    }

    def __init__(self, **kwargs):

        self.var__scale_x = kwargs.pop('var__scale_x', 0.2)
        self.var__scale_y = kwargs.pop('var__scale_y', 0.2)
        self.var__uhid = kwargs.pop('var__uhid', False)

        super().__init__(**kwargs)

        self.ca: ControlAdapter = self.proxy_group.control_layer.ca

        self.mouse_controller = MouseController()

    def inject_setting_details(self, container: MDDialogContentContainer):
        """
            增加设置项
        :param container:
        :return:
        """
        content = MDGridLayout(cols=4, adaptive_height=True, spacing=dp(10))

        tf_scale_x = MDTextField(text=str(self.var__scale_x), mode='filled')
        tf_scale_x.bind(text=partial(self.get_validate, self, 'var__scale_x', float))

        content.add_widget(MDLabel(text=_('X轴灵敏度'), size_hint=(None, 1), width=dp(100)))
        content.add_widget(tf_scale_x)

        tf_scale_y = MDTextField(text=str(self.var__scale_y), mode='filled')
        tf_scale_y.bind(text=partial(self.get_validate, self, 'var__scale_y', float))

        content.add_widget(MDLabel(text=_('Y轴灵敏度'), size_hint=(None, 1), width=dp(100)))
        content.add_widget(tf_scale_y)

        container.add_widget(content)

    def activate(self):
        """
            激活控制状态
        :return:
        """
        self.is_pressed = True

        Window.show_cursor = False

        self.window_width = Window.width
        self.window_height = Window.height

        self.base_pos = (
            int(Window.left * Metrics.density + self.window_width / 2),
            int(Window.top * Metrics.density + self.window_height / 2)
        )

        self.last_move_time = time.time()

        self.aim_spr = self.spr()

        self.mouse_controller.position = self.base_pos

        self.ca.f_touch_spr(EnumAction.DOWN, self.aim_spr, self.touch_id)

        self.mouse_listener = MouseListener(on_click=self.on_click, on_move=self.on_move, suppress=True)
        self.mouse_listener.start()

        self.proxy_group.touch_holder = self

    def deactivate(self):
        """
            退出状态
        :return:
        """
        self.mouse_listener.stop()

        Window.show_cursor = True

        self.ca.f_touch_spr(EnumAction.UP, self.aim_spr, self.touch_id)
        self.is_pressed = False

        if self.proxy_group.touch_holder is self:
            self.proxy_group.touch_holder = None

    def key_up(self, uk: UnifiedKey, modifiers, ca: ControlAdapter):
        """
            切换状态
        :param uk:
        :param modifiers:
        :param ca:
        :return:
        """
        self.deactivate() if self.is_pressed else self.activate()

    def on_click(self, x: int, y: int, button, pressed):
        """
            点击事件，触发鼠标事件
        :param x:
        :param y:
        :param button:
        :param pressed:
        :return:
        """
        uk = self.MOUSE_BUTTON_MAP.get(button, None)
        if uk and uk in self.proxy_group.proxies_map:
            if pressed:
                Clock.schedule_once(
                    partial(self.proxy_group.on_key_down, uk, Window.modifiers, self.ca)
                )
            else:
                Clock.schedule_once(
                    partial(self.proxy_group.on_key_up, uk, Window.modifiers, self.ca)
                )

    def on_move(self, x: int, y: int, injected: bool):
        """
            移动事件
        :param x:
        :param y:
        :param injected:
        :return:
        """
        if injected: return

        x, y = int(x), int(y)

        mouse_pos = self.mouse_controller.position

        move_dx = x - mouse_pos[0]
        move_dy = y - mouse_pos[1]

        # 无移动
        if move_dx == 0 and move_dy == 0: return

        max_dx = 64
        move_dx = max(-max_dx, min(max_dx, move_dx))

        max_dy = 32
        move_dy = max(-max_dy, min(max_dy, move_dy))

        _move_spr = ScalePointR(
            move_dx * self.var__scale_x / self.window_width,
            move_dy * self.var__scale_y / self.window_height,
            self.aim_spr.r
        )

        self.aim_spr = self.aim_spr + _move_spr

        self.ca.f_touch_spr(EnumAction.MOVE, self.aim_spr, self.touch_id, ignore_repeat_check=True)

        if abs(self.aim_spr.x - self.spr(False).x) > 0.1 or abs(self.aim_spr.y - self.spr(False).y) > 0.1:
            self.reset()

        elif time.time() - self.last_move_time > 1:
            self.reset()

    def reset(self):
        """
            重置准星触摸位置
        :return:
        """
        self.ca.f_touch_spr(EnumAction.UP, self.aim_spr, self.touch_id)
        time.sleep(1 / 120)
        self.aim_spr = self.spr()
        self.ca.f_touch_spr(EnumAction.DOWN, self.aim_spr, self.touch_id)
        self.last_move_time = time.time()


class ButtonAimLinux(Proxy):
    """
        Linux系统下瞄准按钮
    """
    NAME = _('Aim')
    ICON_COLOR = Colors.Yellow
    ICON = 'target-account'
    TYPE_KEY = 'button_aim'

    MOUSE_BUTTON_MAP = {
        Button.left: UnifiedKeys.UK_MOUSE_L,
        Button.right: UnifiedKeys.UK_MOUSE_R,
        Button.middle: UnifiedKeys.UK_MOUSE_WHEEL
    }

    def __init__(self, **kwargs):

        self.var__scale_x = kwargs.pop('var__scale_x', 0.2)
        self.var__scale_y = kwargs.pop('var__scale_y', 0.2)
        self.var__uhid = kwargs.pop('var__uhid', False)

        super().__init__(**kwargs)

        self.ca: ControlAdapter = self.proxy_group.control_layer.ca

        self.mouse_controller = MouseController()

        self.task = None

    def inject_setting_details(self, container: MDDialogContentContainer):
        """
            增加设置项
        :param container:
        :return:
        """
        content = MDGridLayout(cols=4, adaptive_height=True, spacing=dp(10))

        tf_scale_x = MDTextField(text=str(self.var__scale_x), mode='filled')
        tf_scale_x.bind(text=partial(self.get_validate, self, 'var__scale_x', float))

        content.add_widget(MDLabel(text=_('X轴灵敏度'), size_hint=(None, 1), width=dp(100)))
        content.add_widget(tf_scale_x)

        tf_scale_y = MDTextField(text=str(self.var__scale_y), mode='filled')
        tf_scale_y.bind(text=partial(self.get_validate, self, 'var__scale_y', float))

        content.add_widget(MDLabel(text=_('Y轴灵敏度'), size_hint=(None, 1), width=dp(100)))
        content.add_widget(tf_scale_y)

        container.add_widget(content)

    def key_up(self, uk: UnifiedKey, modifiers, ca: ControlAdapter):
        """
            切换状态
        :param uk:
        :param modifiers:
        :param ca:
        :return:
        """
        self.deactivate() if self.is_pressed else self.activate()
        self.is_pressed = not self.is_pressed

    def activate(self):
        """
            激活控制状态
        """

        Window.grab_mouse()
        Window.show_cursor = False

        # Macosx 窗口位置计算不同
        self.window_width = Window.width / (Metrics.density if platform == 'macosx' else 1)
        self.window_height = Window.height / (Metrics.density if platform == 'macosx' else 1)

        # Macosx 窗口位置计算不同
        self.base_pos = (
            int(Window.left * (1 if platform == 'macosx' else Metrics.density) + self.window_width / 2),
            int(Window.top * (1 if platform == 'macosx' else Metrics.density) + self.window_height / 2)
        )

        self.last_pos: tuple[int, int] = self.base_pos
        self.mouse_controller.position = self.base_pos

        self.aim_spr = self.spr()
        self.ca.f_touch_spr(EnumAction.DOWN, self.aim_spr, self.touch_id)

        time.sleep(2 / 60)

        # 周期性检查鼠标状态
        self.task = Clock.schedule_interval(self._move, 1 / 120)

        self.proxy_group.touch_holder = self

    def deactivate(self):
        """
            失活
        """
        self.task.cancel()
        Window.ungrab_mouse()
        Window.show_cursor = True

        self.ca.f_touch_spr(EnumAction.UP, self.aim_spr, self.touch_id)

        if self.proxy_group.touch_holder is self:
            self.proxy_group.touch_holder = None

    def _move(self, dt):
        """
            周期性处理鼠标事件
        """

        mouse_pos = self.mouse_controller.position

        # 无移动
        if mouse_pos == self.last_pos: return

        dx, dy = mouse_pos[0] - self.last_pos[0], mouse_pos[1] - self.last_pos[1]

        # 限定移动范围
        max_dx = 64
        move_dx = max(-max_dx, min(max_dx, dx))

        max_dy = 32
        move_dy = max(-max_dy, min(max_dy, dy))

        # 计算移动量并传递信号
        self.aim_spr = ScalePointR(
            move_dx / self.window_width * self.var__scale_x,
            move_dy / self.window_height * self.var__scale_y,
            self.aim_spr.r
        ) + self.aim_spr

        self.ca.f_touch_spr(EnumAction.MOVE, self.aim_spr, self.touch_id, ignore_repeat_check=True)

        # 归位鼠标或触摸
        self.last_pos = mouse_pos

        dxa, dya = self.last_pos[0] - self.base_pos[0], self.last_pos[1] - self.base_pos[1]

        # 鼠标归位
        if abs(dxa) > self.window_width / 3 or abs(dya) > self.window_height / 3:
            self.mouse_controller.position = self.base_pos
            self.last_pos = self.base_pos

        # 触摸归位
        if abs(self.aim_spr.x - self.spr(False).x) > 0.15 or abs(self.aim_spr.y - self.spr(False).y) > 0.1:
            self.reset()

    def reset(self):
        """
            重置触摸位置
        """
        self.ca.f_touch_spr(EnumAction.UP, self.aim_spr, self.touch_id)
        time.sleep(1 / 60)
        self.aim_spr = self.spr()
        self.ca.f_touch_spr(EnumAction.DOWN, self.aim_spr, self.touch_id)


class ButtonJoystick(Proxy):
    """
        摇杆按钮
    """
    NAME = _('Joystick')
    ICON_COLOR = Colors.Grey
    ICON = 'gamepad'
    TYPE_KEY = 'button_joystick'

    def __init__(self, **kwargs):

        self.var__code_up = kwargs.pop('var__code_up', -1)
        self.var__code_down = kwargs.pop('var__code_down', -1)
        self.var__code_left = kwargs.pop('var__code_left', -1)
        self.var__code_right = kwargs.pop('var__code_right', -1)

        self.var__cr = kwargs.pop('var__cr', .2)
        self.var__speed = kwargs.pop('var__speed', .1)

        super().__init__(**kwargs)

        self.uk_u = UnifiedKeys.get_by_code(self.var__code_up)
        self.uk_d = UnifiedKeys.get_by_code(self.var__code_down)
        self.uk_l = UnifiedKeys.get_by_code(self.var__code_left)
        self.uk_r = UnifiedKeys.get_by_code(self.var__code_right)

        self.ca: ControlAdapter = self.proxy_group.control_layer.ca

        with self.canvas.before:
            Color(.2, 1, 0, 0.8)
            self.d_round = Line(width=dp(2))

        self.expand = MDSlider(
            MDSliderHandle(),
            value=self.var__cr, min=0, max=0.4, width=dp(180), size_hint_x=None
        )
        self.add_widget(self.expand)

        self.expand.bind(value=self.update_round)

        self.update_badge()

        self.task: Optional[ClockEvent] = None

        self.hw: float = self.proxy_group.control_layer.height / self.proxy_group.control_layer.width

        self.dx, self.dy = self._spr.x, self._spr.y
        self.angle_bias: float = 0.0
        self.angle_bias_xy: float = 0.0
        self.r_fix: float = 1.0

    def update_pos(self, parent_widget: MDWidget, direction: EnumDirection):
        """
            更新位置，需要同步更新外部圆及调整器
        :param parent_widget:
        :param direction:
        :return:
        """
        super().update_pos(parent_widget, direction)
        self.icon.center = self.center
        self.d_round.circle = (*self.center, self.var__cr * parent_widget.height)
        self.expand.center = (self.center_x, self.center_y - dp(60))

    def update_round(self, instance, value):
        """
            更新范围指示器
        :param instance:
        :param value:
        :return:
        """
        self.var__cr = value
        self.d_round.circle = (*self.center, self.var__cr * self.proxy_group.control_layer.height)

    def update_badge(self):
        """
            更新显示文本
        :return:
        """
        text = ''
        set_i = 0
        for name in ['up', 'down', 'left', 'right']:
            _uk = UnifiedKeys.get_by_code(getattr(self, f"var__code_{name}"))
            if _uk != UnifiedKeys.UK_UNKNOWN:
                if set_i == 2:
                    text += '\n'
                    set_i = -1
                else:
                    set_i += 1
                text += f' {name.upper()}:{_uk.value if _uk.value else _uk.code} '

        self.badge.text = text

    @Proxy.check_status
    def on_touch_down(self, uk: UnifiedKey, touch):
        """
            透传至内部控件
        :param uk:
        :param touch:
        :return:
        """
        if self.expand.collide_point(*touch.pos):
            self.expand.on_touch_down(touch)
            return True
        else:
            return super().on_touch_down(uk, touch)

    @Proxy.check_status
    def on_touch_move(self, uk: UnifiedKey, touch):
        """
            透传至内部控件
        :param uk:
        :param touch:
        :return:
        """
        if self.expand.collide_point(*touch.pos):
            self.expand.on_touch_move(touch)
            return True
        else:
            res = super().on_touch_move(uk, touch)
            self.update_pos(
                self.proxy_group.control_layer,
                self.proxy_group.control_layer.cb__current_direction()
            )
            return res

    @Proxy.check_status
    def on_touch_up(self, uk: UnifiedKey, touch):
        """
            透传至内部控件
        :param uk:
        :param touch:
        :return:
        """
        if self.expand.collide_point(*touch.pos):
            self.expand.on_touch_up(touch)
            return True
        else:
            return super().on_touch_up(uk, touch)

    def create__setup_dialog(self):
        """
            重写配置面板
        :return:
        """
        sd = SettingDialog(self.NAME)
        content = MDGridLayout(cols=4, adaptive_height=True, spacing=dp(15))
        sd.container.add_widget(content)

        # 模拟操作
        content.add_widget(MDLabel(text='Simulate', size_hint=(None, 1), width=dp(80)))
        content.add_widget(MDCheckbox(
            active=self.var__simulate,
            on_active=lambda instance, is_simulate: setattr(self, 'var__simulate', is_simulate),
        ))

        # 滑动速度
        tf__speed = MDTextField(text=str(self.var__speed), mode='filled')
        tf__speed.bind(text=partial(self.get_validate, self, 'var__speed', float))

        content.add_widget(MDLabel(text='speed', size_hint=(None, 1), width=dp(100)))
        content.add_widget(tf__speed)

        def register_key(key_name: str, uk: UnifiedKey) -> bool:
            """
                注册按键
            :param key_name:
            :param uk:
            :return:
            """
            if uk is None:
                MYSnackBarError('Bind Error!')
                return False

            if uk in self.proxy_group.proxies_map:
                MYSnackBarError('Repeated!')
                return False

            else:
                now_uk = UnifiedKeys.get_by_code(getattr(self, key_name))
                if now_uk in self.proxy_group.proxies_map:
                    self.proxy_group.proxies_map.pop(now_uk)
                setattr(self, key_name, uk.code)
                setattr(self, f"uk_{key_name[:1]}", uk)
                self.proxy_group.proxies_map[uk] = self
                self.update_badge()
                return True

        for _ in ['up', 'down', 'left', 'right']:
            content.add_widget(MDLabel(text=_.upper(), size_hint=(None, 1), width=dp(60)))
            content.add_widget(SetUKButton(
                UnifiedKeys.get_by_code(getattr(self, f"var__code_{_}")),

                # 自行处理注册逻辑
                partial(register_key, f"var__code_{_}"))
            )

        sd.open()

    @property
    def uks(self) -> list[UnifiedKey]:
        return [self.uk_u, self.uk_d, self.uk_l, self.uk_r]

    @property
    def pressed_keys(self) -> list[UnifiedKey]:
        """
            按下按键列表
        :return:
        """
        return [
            _ for _ in self.uks if _ in self.proxy_group.control_layer.pressed_keys
        ]

    def key_down(self, uk: UnifiedKey, modifiers, ca: ControlAdapter):
        """
            激活
        :param uk:
        :param modifiers:
        :param ca:
        :return:
        """
        if self.task: return
        else:
            cl = self.proxy_group.control_layer
            self.hw = cl.height / cl.width

            if self.var__simulate:
                self.angle_bias = math.radians(random.uniform(-8, 8))
                self.angle_bias_xy = math.radians(random.uniform(-1, 1))
                _spr = self.spr()
                self.r_fix = random.uniform(0.99, 1.1)
            else:
                self.angle_bias_xy = 0
                self.angle_bias = 0
                _spr = self._spr
                self.r_fix = 1

            self.dx, self.dy = _spr.x, _spr.y

            ca.f_touch_spr(EnumAction.DOWN, _spr, self.touch_id)

            self.task = Clock.schedule_interval(self.move, 1 / random.randint(60, 70))

    def key_up(self, uk: UnifiedKey, modifiers, ca: ControlAdapter):
        """
            失活检查
        :param uk:
        :param modifiers:
        :param ca:
        :return:
        """
        # 无论是否继续，更新模拟偏移角度
        if self.var__simulate:
            self.angle_bias = math.radians(random.uniform(-8, 8))
            self.angle_bias_xy = math.radians(random.uniform(-1, 1))

        if self.pressed_keys: return
        else:
            self.task.cancel()
            self.task = None
            ca.f_touch_spr(EnumAction.UP, ScalePointR(
                self.dx, self.dy, self._spr.r
            ), self.touch_id)

    def move(self, dt):
        """
            摇杆移动
        :param dt:
        :return:
        """

        pressed_keys = self.pressed_keys

        dx, dy = 0, 0

        if self.uk_u in pressed_keys:
            dy -= 1

        if self.uk_d in pressed_keys:
            dy += 1

        if self.uk_l in pressed_keys:
            dx -= 1

        if self.uk_r in pressed_keys:
            dx += 1

        # 无移动
        if dx == 0 and dy == 0: return

        angle = math.atan2(dy / self.hw, dx)

        # 单一方向增加小角度
        if abs(dx) + abs(dy) == 1:
            angle += self.angle_bias_xy

        # 组合方向增加大角度
        elif abs(dx) + abs(dy) > 1:
            angle += self.angle_bias

        _center_spr = self.spr(False)

        target_dx = self.var__cr * self.hw * math.cos(angle) * self.r_fix + _center_spr.x
        target_dy = self.var__cr * math.sin(angle) * self.r_fix + _center_spr.y

        move_dx = target_dx - self.dx
        move_dy = target_dy - self.dy

        if abs(move_dx) < 0.005 and abs(move_dy) < 0.005: return

        self.dx += move_dx * self.var__speed
        self.dy += move_dy * self.var__speed

        self.ca.f_touch_spr(
            EnumAction.MOVE,
            ScalePointR(self.dx, self.dy, self._spr.r),
            self.touch_id, ignore_repeat_check=True
        )


class ButtonWatch(Proxy):
    """
        观察按钮
    """
    NAME = _('Watch')
    ICON_COLOR = Colors.Yellow
    ICON = 'eye-circle'
    TYPE_KEY = 'button_watch'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.move_spr = self.spr()

        self.ca = self.proxy_group.control_layer.ca
        self.mouse_controller = MouseController()

        self._touch_holder = None

    def key_up(self, uk: UnifiedKey, modifiers, ca: ControlAdapter):
        """
            切换观察状态
        :param uk:
        :param modifiers:
        :param ca:
        :return:
        """
        self.deactivate() if self.is_pressed else self.activate()
        self.is_pressed = not self.is_pressed

    def activate(self):
        """
            激活观察状态
        :return:
        """
        # 若开启瞄准模式，则停止瞄准，进行观察
        if self.proxy_group.touch_holder:
            if isinstance(self.proxy_group.touch_holder, (ButtonAim, ButtonAimLinux,)):
                self.proxy_group.touch_holder.deactivate()
                time.sleep(2 / 60)
            elif isinstance(self.proxy_group.touch_holder, ButtonWatch):
                return

            self._touch_holder = self.proxy_group.touch_holder
            self.proxy_group.touch_holder = self

        Window.show_cursor = False

        self.window_width = Window.width
        self.window_height = Window.height

        self.move_spr = self.spr()
        self.ca.f_touch_spr(EnumAction.DOWN, self.move_spr, self.touch_id)

        # 等待按下生效
        time.sleep(2 / 60)

        # 启动监控
        self.mouse_listener = MouseListener(on_move=self.on_move, suppress=True)
        self.mouse_listener.start()

    def deactivate(self):
        """
            停止监控
        :return:
        """
        # 释放
        self.ca.f_touch_spr(EnumAction.UP, self.move_spr, self.touch_id)
        self.mouse_listener.stop()
        Window.show_cursor = True

        # 恢复瞄准状态
        if self._touch_holder:
            self.proxy_group.touch_holder = self._touch_holder
            self.proxy_group.touch_holder.activate()
            self._touch_holder = None

    def on_move(self, x: int, y: int, injected: bool):
        """
            移动观察
        :param x:
        :param y:
        :param injected:
        :return:
        """
        if injected: return

        x, y = int(x), int(y)

        mouse_pos = self.mouse_controller.position

        move_dx = x - mouse_pos[0]
        move_dy = y - mouse_pos[1]

        # 无移动
        if move_dx == 0 and move_dy == 0: return

        self.move_spr = self.move_spr + ScalePointR(
            move_dx / self.window_width, move_dy / self.window_height, self._spr.r
        ) * 0.6

        self.ca.f_touch_spr(EnumAction.MOVE, self.move_spr, self.touch_id)


class JoystickMapper:
    def __init__(self, joystick_center, joystick_max_radius):
        """
        :param joystick_center: 摇杆中心的像素坐标 (uj, vj)
        :param joystick_max_radius: 摇杆拉满时的像素距离 (通常是 100-150 像素)
        """
        self.uj, self.vj = joystick_center
        self.rj = joystick_max_radius

    def logic_to_touch_point(self, x_logic, y_logic, R_logic=100.0):
        """
        将还原后的逻辑坐标转换为模拟触摸的绝对像素坐标
        """
        # 1. 计算逻辑空间中的向量长度和角度
        magnitude = math.sqrt(x_logic ** 2 + y_logic ** 2)
        # 使用 atan2(y, x)，注意 y_logic 向上为正
        angle_rad = math.atan2(y_logic, x_logic)

        # 2. 归一化强度 (0.0 到 1.0)
        # 确保不会超出摇杆物理边界
        normalized_mag = min(magnitude / R_logic, 1.5)

        # 3. 映射回摇杆的像素坐标系
        # 屏幕像素坐标系中：U = CenterU + r * cos(theta)
        #                V = CenterV - r * sin(theta) (因为屏幕 V 向下是加)
        touch_u = self.uj + (normalized_mag * self.rj * math.cos(angle_rad))
        touch_v = self.vj - (normalized_mag * self.rj * math.sin(angle_rad))

        return touch_u, touch_v


class ButtonSkill(Proxy):
    """
        技能类按钮
    """
    NAME = _('Skill')
    ICON_COLOR = Colors.BlueLight
    ICON = 'vector-circle'
    TYPE_KEY = 'button_skill'

    def __init__(self, **kwargs):

        self.var__cal_type = kwargs.pop('var__cal_type', '1')

        # 技能椭圆中心
        self.var__skill_x = kwargs.pop('var__skill_x', .5)
        self.var__skill_y = kwargs.pop('var__skill_y', .5)

        # 真实中心 Y
        self.var__real_y = kwargs.pop('var__real_y', .5)

        # 椭圆长宽
        self.var__skill_a = kwargs.pop('var__skill_a', .2)
        self.var__skill_b = kwargs.pop('var__skill_b', .1)

        # 摇杆纵向半径比
        self.var__js_hr = kwargs.pop('var__js_hr', .05)

        super().__init__(**kwargs)

        self.ca: ControlAdapter = self.proxy_group.control_layer.ca

        with self.canvas.before:
            # 摇杆环
            Color(.2, 1, 0, 0.8)
            self.d_round_js = Line(width=dp(1))

        self.expand = MDSlider(
            MDSliderHandle(),
            value=self.var__js_hr, min=0, max=0.4, width=dp(180), size_hint_x=None
        )
        self.add_widget(self.expand)

        self.expand.bind(value=self.update_js_round)

        self.task = None
        self.mouse_spr = None
        self.last_mouse_pos: tuple[float, float] = .0, .0

    def update_pos(self, parent_widget: MDWidget, direction: EnumDirection):
        """
            更新位置信息
        """
        super().update_pos(parent_widget, direction)
        self.d_round_js.circle = (*self.center, self.var__js_hr * parent_widget.height)
        self.expand.center = (self.center_x, self.center_y - dp(60))

    def update_js_round(self, instance, value):
        """
            更新技能环半径
        """
        self.var__js_hr = value
        self.d_round_js.circle = (
            *self.center, self.var__js_hr * self.proxy_group.control_layer.height
        )

    @Proxy.check_status
    def on_touch_down(self, uk: UnifiedKey, touch):
        """
            透传至内部控件
        :param uk:
        :param touch:
        :return:
        """
        if self.expand.collide_point(*touch.pos):
            self.expand.on_touch_down(touch)
            return True
        else:
            return super().on_touch_down(uk, touch)

    @Proxy.check_status
    def on_touch_move(self, uk: UnifiedKey, touch):
        """
            透传至内部控件
        :param uk:
        :param touch:
        :return:
        """
        if self.expand.collide_point(*touch.pos):
            self.expand.on_touch_move(touch)
            return True
        else:
            res = super().on_touch_move(uk, touch)
            self.update_pos(
                self.proxy_group.control_layer,
                self.proxy_group.control_layer.cb__current_direction()
            )
            return res

    @Proxy.check_status
    def on_touch_up(self, uk: UnifiedKey, touch):
        """
            透传至内部控件
        :param uk:
        :param touch:
        :return:
        """
        if self.expand.collide_point(*touch.pos):
            self.expand.on_touch_up(touch)
            return True
        else:
            return super().on_touch_up(uk, touch)

    def inject_setting_details(self, container: MDDialogContentContainer):
        """
            设置界面
        """
        content = MDGridLayout(cols=4, adaptive_height=True, spacing=dp(10))

        # 技能椭圆 A
        tf_skill_a = MDTextField(text=str(self.var__skill_a), mode='filled')
        tf_skill_a.bind(text=partial(self.get_validate, self, 'var__skill_a', float))
        content.add_widget(MDLabel(text=_('Skill EA/W'), size_hint=(None, 1), width=dp(100)))
        content.add_widget(tf_skill_a)

        # 技能椭圆 B
        tf_skill_b = MDTextField(text=str(self.var__skill_b), mode='filled')
        tf_skill_b.bind(text=partial(self.get_validate, self, 'var__skill_b', float))
        content.add_widget(MDLabel(text=_('Skill EB/H'), size_hint=(None, 1), width=dp(100)))
        content.add_widget(tf_skill_b)

        # 技能椭圆圆心 Y
        tf_skill_y = MDTextField(text=str(self.var__skill_y), mode='filled')
        tf_skill_y.bind(text=partial(self.get_validate, self, 'var__skill_y', float))
        content.add_widget(MDLabel(text=_('Skill EY'), size_hint=(None, 1), width=dp(100)))
        content.add_widget(tf_skill_y)

        # 实际角色技能中心 Y
        tf_real_y = MDTextField(text=str(self.var__real_y), mode='filled')
        tf_real_y.bind(text=partial(self.get_validate, self, 'var__real_y', float))
        content.add_widget(MDLabel(text=_('Real Y'), size_hint=(None, 1), width=dp(100)))
        content.add_widget(tf_real_y)

        def open_menu(caller):
            menu_items = [
                {
                    "text": f"{i}",
                    "on_release": lambda x=str(i):
                        setattr(self, 'var__cal_type', x) or
                        setattr(drop_down_txt, 'text', f"TYPE_{x}") or
                        menu.dismiss()
                } for i in range(1, 3)
            ]
            menu = MDDropdownMenu(caller=caller, items=menu_items)
            menu.open()

        # 技能映射算法
        content.add_widget(MDLabel(text=_('CalType'), size_hint=(None, 1), width=dp(100)))

        drop_down_txt = MDDropDownItemText()
        content.add_widget(
            MDDropDownItem(
                drop_down_txt, on_release=open_menu
            )
        )

        container.add_widget(content)

        Clock.schedule_once(
            lambda dt: setattr(drop_down_txt, 'text', f"TYPE_{self.var__cal_type}"), 0.2
        )

    def key_down(self, uk: UnifiedKey, modifiers, ca: ControlAdapter):
        """
            激活技能
        """
        if self.is_pressed: return
        self.is_pressed = True

        if self.var__simulate:
            self.mouse_spr = self.spr()
        else:
            self.mouse_spr = self._spr

        ca.f_touch_spr(EnumAction.DOWN, self.mouse_spr, self.touch_id)

        cl = self.proxy_group.control_layer.screen

        # 真实技能中心
        self.real_center = np.array((self.var__skill_x * cl.width, self.var__real_y * cl.height))

        # 技能范围椭圆
        self.el_center = np.array((self.var__skill_x * cl.width, self.var__skill_y * cl.height))
        self.el_a, self.el_b = self.var__skill_a * cl.width, self.var__skill_b * cl.height
        self.inv_sq_axes = 1.0 / np.array((self.el_a ** 2, self.el_b ** 2))

        # 摇杆中心及半径
        self.js_center = np.array((self.mouse_spr.x * cl.width, self.mouse_spr.y * cl.height))
        self.cr = self.var__js_hr * cl.height

        self.physics_width = cl.width
        self.physics_height = cl.height

        # 等待技能激活
        time.sleep(1 / 60)

        # 启动技能鼠标跟踪
        self.task = Clock.schedule_interval(self.update, 1 / 60)

    def key_up(self, uk: UnifiedKey, modifiers, ca: ControlAdapter):
        """
            释放技能
        """
        self.is_pressed = False
        self.task.cancel()

        ca.f_touch_spr(EnumAction.UP, self.mouse_spr, self.touch_id)

    def mouse2joystick_1(self, mouse_x, mouse_y):
        """
            鼠标坐标转换为技能
            方式1：以角色脚下为计算点
        """
        mouse_pos = np.array((mouse_x, mouse_y))

        # 直线方向向量
        v = mouse_pos - self.real_center

        # 相对于椭圆中心偏移
        w = self.real_center - self.el_center

        a = np.sum((v ** 2) * self.inv_sq_axes)
        b = 2 * np.sum((v * w) * self.inv_sq_axes)
        k = np.sum((w ** 2) * self.inv_sq_axes) - 1

        # 判断是否成立
        delta = b ** 2 - 4 * a * k
        if delta < 0:
            return

        # 计算映射比例
        t_boundary = (-b + np.sqrt(delta)) / (2 * a)
        ratio = 1.0 / t_boundary if t_boundary != 0 else 0

        # 计算角度
        angle_rad = np.arctan2(v[1], v[0])

        # 映射到目标圆
        # 映射坐标 = 目标中心 + 方向向量 * (比例 * 目标半径)
        direction_vec = np.array([np.cos(angle_rad), np.sin(angle_rad)])
        (js_x, js_y) = self.js_center + direction_vec * (ratio * self.cr)

        self.mouse_spr = ScalePointR(
            js_x / self.physics_width, js_y / self.physics_height,
            self.mouse_spr.r
        )

    def mouse2joystick_2(self, mouse_x, mouse_y):
        """
            鼠标坐标转换为技能
            方式2：透视还原方式
        """
        mouse_pos = np.array((mouse_x, mouse_y))

        # 相对坐标
        m_local = mouse_pos - self.el_center
        rc_local = self.real_center - self.el_center

        # 透视系数
        delta = rc_local[1]

        # 修正
        _f = self.el_b ** 2 + delta ** 2
        k = delta / _f if _f != 0 else 0

        # 逆透视变换
        denom = 1 - k * m_local[1]
        if np.abs(denom) < 1e-9: denom = 1e-9

        # 反向映射
        js_x = (m_local[0] / denom / self.el_a) * self.cr + self.js_center[0]
        js_y = ((m_local[1] - delta) / denom / self.el_b) * self.cr + self.js_center[1]

        self.mouse_spr = ScalePointR(
            js_x / self.physics_width, js_y / self.physics_height, self.mouse_spr.r
        )

    def update(self, dt):
        """
            鼠标跟踪
        """
        _mouse_pos = Window.mouse_pos

        if self.last_mouse_pos == _mouse_pos: return
        else: self.last_mouse_pos = _mouse_pos

        cl = self.proxy_group.control_layer.screen
        if not cl.collide_point(*self.last_mouse_pos): return

        # 鼠标坐标转换为像素坐标
        x, y = cl.to_local(*self.last_mouse_pos)

        mouse_spr = ScalePointR(
            x / cl.width, 1 - y / cl.height, self._spr.r
        )
        mouse_x, mouse_y = mouse_spr.x * cl.width, mouse_spr.y * cl.height

        self.__getattribute__(f"mouse2joystick_{self.var__cal_type}")(mouse_x, mouse_y)

        self.ca.f_touch_spr(
            EnumAction.MOVE, self.mouse_spr, self.touch_id
        )


class ButtonMouseMove(ButtonSkill):
    """
        鼠标控制摇杆移动
    """
    NAME = _('MouseMove')
    ICON_COLOR = Colors.GreenLight
    ICON = 'square-rounded-badge'
    TYPE_KEY = 'button_mouse_move'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.is_holding: bool = False

    def key_down(self, uk: UnifiedKey, modifiers, ca: ControlAdapter):
        """
            保持按键状态
        :param uk:
        :param modifiers:
        :param ca:
        :return:
        """
        if self.is_holding: return

        super().key_down(uk, modifiers, ca)
        self.proxy_group.touch_holder = self

    def key_up(self, uk: UnifiedKey, modifiers, ca: ControlAdapter):
        """
            保持按键状态
        :param uk:
        :param modifiers:
        :param ca:
        :return:
        """
        if not self.is_holding:
            self.is_holding = True
            return

        else:
            super().key_up(uk, modifiers, ca)
            self.is_holding = False
            self.proxy_group.touch_holder = None


ProxyDict: dict[str, type[Proxy]] = {
    cls.TYPE_KEY: cls for cls in (
        ButtonHold, ButtonHoldSwitch,
        ButtonInstantly, ButtonRepeat, ButtonSwitch,
        ButtonWatch,
        ButtonJoystick,
        ButtonSkill, ButtonMouseMove
    )
}


if platform in ('linux', 'macosx'):
    ProxyDict[ButtonAimLinux.TYPE_KEY] = ButtonAimLinux
else:
    ProxyDict[ButtonAim.TYPE_KEY] = ButtonAim


class EnumMode(StrEnum):
    EDIT = 'EDIT'
    CONTROL = 'CONTROL'


class ProxyGroup:

    def __init__(self, control_layer, cfg: JSProxyGroup) -> None:
        self.control_layer = control_layer
        self.cfg = cfg

        self.touch_ids: set[int] = set()

        self.proxies: set[Proxy] = set()

        self.proxies_map: dict[UnifiedKey, Proxy] = {}

        self.touch_holder = None

    def generate_touch_id(self) -> int:
        """
            生成唯一 Touch ID
        :return:
        """
        for touch_id in range(0x413 + 500, 0x413 + 1000):
            if touch_id not in self.touch_ids:
                self.touch_ids.add(touch_id)
                return touch_id
        raise OverflowError('Touch ID Overflow!')

    def activate(self): ...

    def deactivate(self): ...

    def load(self, current_direction: EnumDirection):
        """
            加载代理
        :return:
        """
        self.proxies = set()
        self.cfg.reload()

        for proxy_kwargs in self.cfg.proxies:
            try:
                proxy_cls = ProxyDict.get(proxy_kwargs.pop('type'))
                proxy_instance = proxy_cls.load(
                    touch_id=self.generate_touch_id(),
                    spr=ScalePointR(
                        proxy_kwargs.pop('x'), proxy_kwargs.pop('y'), EnumDirection(proxy_kwargs.pop('r'))
                    ).with_direction(current_direction),
                    proxy_group=self,
                    cb__bind_key=self.cb__bind_key,
                    cb__delete=self.cb__delete,
                    cb__move=self.cb__move,
                    uk=UnifiedKeys.get_by_code(proxy_kwargs.pop('uk', None)),
                    **proxy_kwargs
                )
                self.proxies.add(proxy_instance)

                for key_name, value in proxy_instance.__dict__.items():
                    if key_name.startswith('uk'):
                        self.proxies_map[value] = proxy_instance

            except Exception as e:
               print(e)

    def dump(self):
        """
            存储
        :return:
        """
        proxies = []
        for proxy in self.proxies:
            if not proxy.uks:
                continue

            kwargs = proxy.dump()
            kwargs['type'] = proxy.TYPE_KEY
            kwargs['x'] = proxy._spr.x
            kwargs['y'] = proxy._spr.y
            kwargs['r'] = proxy._spr.r
            kwargs['uk'] = proxy.uk.code if proxy.uk else None
            proxies.append(kwargs)

        self.cfg.proxies = proxies
        self.cfg.dump()

    def cb__bind_key(self, uk: UnifiedKey, proxy: Proxy) -> bool:
        """
            绑定按键
        :param uk:
        :param proxy:
        :return:
        """
        if uk in self.proxies_map:
            MYSnackBarWarning(f"{uk.name} Exists!")
            return False

        self.proxies_map[uk] = proxy
        self.proxies.add(proxy)
        self.proxies_map.pop(proxy.uk, None)

        return True

    def cb__delete(self, proxy: Proxy):
        """
            删除代理
        :param proxy:
        :return:
        """
        if proxy in self.proxies:
            self.proxies.remove(proxy)
            for uks in proxy.uks:
                self.proxies_map.pop(uks, None)

        if proxy in self.control_layer.children:
            self.control_layer.remove_widget(proxy)

    def cb__move(self, proxy: Proxy):
        """
            移动回调函数
        :param proxy:
        :return:
        """
        x, y = proxy.center

        proxy._spr = ScalePointR(
            (x - self.control_layer.x) / self.control_layer.width,
            1 - (y - self.control_layer.y) / self.control_layer.height,
            self.control_layer.cb__current_direction()
        )

    def on_touch_down(self, mode: EnumMode, uk: UnifiedKey, touch: MouseMotionEvent, ca: ControlAdapter):
        """
            按下信号
        :param ca:
        :param mode:
        :param uk:
        :param touch:
        :return:
        """
        # 编辑模式
        if mode == EnumMode.EDIT:
            for proxy in self.proxies:
                if proxy.on_touch_down(uk, touch): return True

        # 控制模式
        elif mode == EnumMode.CONTROL:
            if self.touch_holder:
                proxy = self.proxies_map.get(uk, None)
                if proxy: return proxy.key_down(uk, Window.modifiers, ca)
            else:
                self.control_layer.my_mouse_controller.on_touch_down(touch)

        return None

    def on_touch_move(self, mode: EnumMode, uk: UnifiedKey, touch: MouseMotionEvent, ca: ControlAdapter):
        """
            移动
        :param ca:
        :param mode:
        :param uk:
        :param touch:
        :return:
        """
        # 编辑模式
        if mode == EnumMode.EDIT:
            for proxy in self.proxies:
                if proxy.on_touch_move(uk, touch):
                    return True

        # 控制模式
        elif mode == EnumMode.CONTROL:
            if self.touch_holder is None:
                self.control_layer.my_mouse_controller.on_touch_move(touch)

        return None

    def on_touch_up(self, mode: EnumMode, uk: UnifiedKey, touch: MouseMotionEvent, ca: ControlAdapter):
        """
            释放
        :param ca:
        :param mode:
        :param uk:
        :param touch:
        :return:
        """
        # 编辑模式
        if mode == EnumMode.EDIT:
            for proxy in self.proxies:
                if proxy.on_touch_up(uk, touch):
                    return True

        # 控制模式
        elif mode == EnumMode.CONTROL:
            if self.touch_holder:
                proxy = self.proxies_map.get(uk, None)
                if proxy: return proxy.key_up(uk, Window.modifiers, ca)
            else: self.control_layer.my_mouse_controller.on_touch_up(touch)

        return None

    def on_key_down(self, uk: UnifiedKey, modifiers, ca: ControlAdapter, *args):
        """
            按键按下
        :param ca:
        :param uk:
        :param modifiers:
        :return:
        """
        uk in self.proxies_map and self.proxies_map[uk].key_down(uk, modifiers, ca)

    def on_key_up(self, uk: UnifiedKey, modifiers, ca: ControlAdapter, *args):
        """
            按键抬起
        :param ca:
        :param uk:
        :param modifiers:
        :return:
        """
        uk in self.proxies_map and self.proxies_map[uk].key_up(uk, modifiers, ca)

    def add_proxy(self, proxy_cls, spr: ScalePointR) -> Proxy:
        """
            新建代理
        :param proxy_cls:
        :param spr:
        :return:
        """
        proxy_instance = proxy_cls.load(
            self.generate_touch_id(), spr, self,
            self.cb__bind_key, self.cb__delete, self.cb__move
        )
        self.proxies.add(proxy_instance)
        Clock.schedule_once(
            lambda dt: proxy_instance.update_pos(self.control_layer, spr.r)
        )
        return proxy_instance
