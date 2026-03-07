# -*- coding: utf-8 -*-
"""
    main
    ~~~~~~~~~~~~~~~~~~
    
    Log:
        2026-01-26 0.1.0 Me2sY 创建
"""

__author__ = 'Me2sY'
__version__ = '0.1.0'

__all__ = []

from dataclasses import dataclass
from enum import StrEnum
import logging
from typing import Optional

from kivy.clock import Clock
from kivy.core.text import LabelBase
from kivy.core.window import Window
from kivy.metrics import Metrics, dp
from kivy.config import Config
from kivy.utils import platform

from kivymd.app import MDApp
from kivymd.uix.divider import MDDivider
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.screenmanager import MDScreenManager

from mysc.gui.k.components.base.my_navigation import MYNavigation
from mysc.gui.k.components.screens.devices import ScreenListDevices
from mysc.gui.k.components.screens.connections import ScreenConnections
from mysc.utils.params import Param
from mysc.utils.storage import JSONStorage

Config.set('kivy', 'exit_on_escape', 0)
Config.set('input', 'mouse', 'mouse,multitouch_on_demand')

LabelBase.register(name='Roboto', fn_regular=Param.PATH_LIBS.joinpath('notosans.ttf').__str__())

# MacOS adbutils window_size 缺陷
if platform == 'macosx':
    logging.getLogger("adbutils").setLevel(logging.INFO)


class EnumStyle(StrEnum):
    Light = 'Light'
    Dark = 'Dark'


@dataclass
class MainConfig(JSONStorage):
    """
        App 设置
    """
    Prefix = 'APPCFG_'

    # Pos and Size
    pos_x: int = 1300
    pos_y: int = 400
    width: float = 500
    height: float = 800

    main_style: EnumStyle = EnumStyle.Light

    @property
    def size(self) -> tuple:
        return self.width, self.height


class Main(MDBoxLayout):
    """
        主界面
    """
    def __init__(self, app_cfg: MainConfig, **kwargs):

        super().__init__(**kwargs)

        self.orientation = 'horizontal'
        self.padding = dp(4)
        self.spacing = dp(1)

        self.app_cfg = app_cfg

        # 定义左侧导航栏
        self.nav = MYNavigation(md_bg_color=self.md_bg_color)
        self.add_widget(self.nav)
        self.init_nav()

        self.add_widget(MDDivider(orientation='vertical'))

        # 定义右侧主界面
        self.layout = MDBoxLayout(orientation='vertical')
        self.add_widget(self.layout)

        self.menu_items = {}

        # Screens ====================================================================
        # MDScreenManager
        self.sm: MDScreenManager = MDScreenManager(md_bg_color=self.md_bg_color)
        self.layout.add_widget(self.sm)

        # Screen Device
        self.screen_devices: ScreenListDevices = ScreenListDevices(nav=self.nav, main=self)

        # Connections
        self.screen_connections: ScreenConnections = ScreenConnections(nav=self.nav, main=self)

        self.sm.add_widget(self.screen_devices)
        self.sm.current = self.screen_devices.name

        self.sm.add_widget(self.screen_connections)

        self.is_changing_sp: bool = False
        self.set_window_pos_and_size()

        Clock.schedule_once(self.init_window_bind, 1)

    def init_window_bind(self, *args):
        """
            初始化事件绑定
        :param args:
        :return:
        """
        Window.bind(on_resize=self.on_window_resize, top=self.on_window_top, left=self.on_window_left)

    def on_main(self, title: Optional[str] = None):
        """
            切换至主界面
        :param title:
        :return:
        """
        self.set_window_pos_and_size()
        if title: Window.set_title(title)

    def set_window_pos_and_size(self):
        """
            设置 Windows Position & Size
        :return:
        """
        self.is_changing_sp = True

        if Window.size != self.app_cfg.size: Window.size = self.app_cfg.size
        if Window.left != self.app_cfg.pos_x: Window.left = self.app_cfg.pos_x
        if Window.top != self.app_cfg.pos_y: Window.top = self.app_cfg.pos_y

        self.is_changing_sp = False

    def on_window_resize(self, *args):
        """
            Window Resize
        :param args:
        :return:
        """
        if self.is_changing_sp: return

        i, w, h = args
        if self.sm.current_screen is self.screen_connections.current_vac:
            self.screen_connections.on_window_resize(*args)
        else:
            self.app_cfg.width = w / Metrics.density
            self.app_cfg.height = h / Metrics.density

    def on_window_left(self, *args):
        """
            Window Left
        :param args:
        :return:
        """
        if self.is_changing_sp: return

        if self.sm.current_screen is self.screen_connections.current_vac:
            self.screen_connections.on_window_left(*args)
        else:
            obj, self.app_cfg.pos_x = args

    def on_window_top(self, *args):
        """
            Window Top
        :param args:
        :return:
        """
        if self.is_changing_sp: return

        if self.sm.current_screen is self.screen_connections.current_vac:
            self.screen_connections.on_window_top(*args)
        else:
            obj, self.app_cfg.pos_y = args

    def init_nav(self):
        """
            初始化导航栏
        :return:
        """
        self.nav.add_fixed_button('animation', self.cb__btn_connections)
        self.nav.add_fixed_button('devices', self.cb__btn_devices)

    def cb__btn_devices(self, caller):
        """
            设备管理界面
        :param caller:
        :return:
        """
        self.screen_devices.active()

    def cb__btn_connections(self, caller):
        """
            连接管理界面
        :param caller:
        :return:
        """
        self.screen_connections.active()


class MYScrcpyApp(MDApp):

    def on_stop(self):
        self.app_cfg.dump()

    def build(self):
        """
            创建应用
        :return:
        """
        self.app_cfg = MainConfig.load('main')
        if self.app_cfg is None:
            self.app_cfg = MainConfig('main')

        self.theme_cls.theme_style = self.app_cfg.main_style
        self.icon = Param.PATH_STATICS.joinpath('mysc.ico').__str__()

        return Main(app_cfg=self.app_cfg, md_bg_color=self.theme_cls.backgroundColor)


if __name__ == '__main__':
    MYScrcpyApp().run()
