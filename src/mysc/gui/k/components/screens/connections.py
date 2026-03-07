# -*- coding: utf-8 -*-
"""
    connections
    ~~~~~~~~~~~~~~~~~~
    
    Log:
        2026-01-28 0.1.0 Me2sY 创建
"""

__author__ = 'Me2sY'
__version__ = '0.1.0'

__all__ = [
    'ScreenConnections'
]

import io
import math
from typing import Optional

from kivy.clock import Clock
from kivy.core.image import Image as CoreImage
from kivy.metrics import dp

from kivymd.uix.appbar import MDTopAppBar, MDTopAppBarTitle
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDIconButton
from kivymd.uix.card import MDCard
from kivymd.uix.divider import MDDivider
from kivymd.uix.fitimage import FitImage
from kivymd.uix.gridlayout import MDGridLayout
from kivymd.uix.label import MDLabel

from kivymd.uix.scrollview import MDScrollView

from mysc.core.device import MYDevice
from mysc.gui.k.components.base.my_screen import MYScreen
from mysc.gui.k.components.base.my_snack_bar import MYSnackBarWarning, MYSnackBarInfo
from mysc.gui.k.components.base.my_navigation import MYNavigation
from mysc.gui.k.components.screens.connect_modes import JSMode
from mysc.gui.k.components.screens.vac import ScreenVAC
from mysc.gui.k.defs import init_language

_ = init_language()


class ConnectionItem(MDCard):

    WIDTH = dp(150)

    def __init__(self, vac: ScreenVAC, **kwargs):

        kwargs.setdefault('style', 'outlined')
        kwargs.setdefault('size_hint_x', None)
        kwargs.setdefault('width', self.WIDTH)
        kwargs.setdefault('orientation', 'vertical')
        kwargs.setdefault('adaptive_height', True)

        super().__init__(**kwargs)

        self.vac = vac

        self.image = FitImage(
            fit_mode='contain', radius=(dp(10), dp(10), 0, 0),
            size_hint=(None, None), size=(self.WIDTH - dp(2), self.WIDTH - dp(2))
        )
        self.add_widget(self.image)

        self.button_container = MDBoxLayout(adaptive_height=True, orientation='horizontal', padding=dp(5))
        self.add_widget(self.button_container)

        self.button_container.add_widget(
            MDLabel(
                text=self.vac.sess.device.serial_no + '\n' + vac.mode.save_key,
                font_style='Label', role='small'
            )
        )
        self.button_container.add_widget(MDIconButton(icon='close', on_release=self.cb__close))

        self.update_screencap()

    def update_screencap(self):
        """
            更新屏幕截图
        :return:
        """
        data = io.BytesIO()
        self.vac.sess.va.get_image().save(data, 'PNG')
        data.seek(0)
        self.image.texture = CoreImage(data, ext='png').texture

    def on_release(self, *args) -> None:
        """
            点击切换到画面
        :param args:
        :return:
        """
        self.vac.active()

    def cb__close(self, *args):
        """
            断开连接
        """
        self.vac.cb__disconnect(self, False)


class ListConnections(MDScrollView):
    def __init__(self, **kwargs):

        kwargs.setdefault('do_scroll_x', False)
        super().__init__(**kwargs)

        self.layout = MDGridLayout(cols=1, adaptive_height=True, spacing=dp(10), padding=dp(10))
        self.add_widget(self.layout)

        self.items: list[ConnectionItem] = []

        self.bind(width=self.width_changed)

    def width_changed(self, caller, new_width):
        """
            宽度变化时自动调整 cols
        :param caller:
        :param new_width:
        :return:
        """
        self.layout.cols = math.floor(new_width / (ConnectionItem.WIDTH + dp(10)))

    def add_item(self, item: ConnectionItem):
        """
            增加项目
        :param item:
        :return:
        """
        self.items.append(item)
        self.layout.add_widget(item)

    def clear_items(self):
        """
            清除项目
        :return:
        """
        self.layout.clear_widgets(self.items)
        self.items = []


class ScreenConnections(MYScreen):

    TITLE = _('Connections')

    def __init__(self, nav: MYNavigation, main, **kwargs):

        super().__init__(nav, main, **kwargs)

        self.vac_map: dict[str, ScreenVAC] = {}

        self.main_layout = MDBoxLayout(orientation='vertical', spacing=dp(10), padding=dp(10))
        self.add_widget(self.main_layout)

        """
            标题栏
        """
        self.main_layout.add_widget(
            MDTopAppBar(
                MDTopAppBarTitle(text=self.TITLE, halign='center', font_style='Title')
            )
        )
        self.main_layout.add_widget(MDDivider())

        self.connect_list = ListConnections()
        self.main_layout.add_widget(self.connect_list)

        self.current_vac: Optional[ScreenVAC] = None

    def create_vac(self, my_device: MYDevice, connect_mode: JSMode) -> Optional[ScreenVAC]:
        """
            创建连接
        :param my_device:
        :param connect_mode:
        :return:
        """
        MYSnackBarInfo(_('连接中'))
        Clock.schedule_once(
            lambda dt: self._create_vac(my_device, connect_mode),
            0.5
        )

    def _create_vac(self, my_device: MYDevice, connect_mode: JSMode) -> Optional[ScreenVAC]:
        """
            创建 VAC
        :param my_device:
        :param connect_mode:
        :return:
        """
        key = f"{my_device.serial_no}|{connect_mode.save_key}"

        if key in self.vac_map:
            sc_vac = self.vac_map[key]
        else:
            try:
                sc_vac = ScreenVAC(my_device, connect_mode, self.nav, self.main, md_bg_color=self.md_bg_color)
                self.vac_map[key] = sc_vac
            except RuntimeError as e:
                MYSnackBarWarning(str(e))
                return None

        if sc_vac not in self.manager.screens:
            self.manager.add_widget(sc_vac)

        sc_vac.active()

        return sc_vac

    def remove_vac(self, vac: ScreenVAC):
        """
            移除 VAC
        :return:
        """
        key = f"{vac.my_device.serial_no}|{vac.mode.save_key}"
        self.vac_map.pop(key, None)
        self.draw()
        if vac == self.current_vac:
            self.current_vac = None

    def draw(self, *args):
        """
            加载 VAC
        :param args:
        :return:
        """
        self.connect_list.clear_items()
        for vac in self.vac_map.values():
            self.connect_list.add_item(ConnectionItem(vac))

    def on_enter(self, *args):

        self.main.on_main(self.TITLE)

        self.nav.clear_buttons()
        self.nav.add_main_button('refresh', self.draw)

        self.draw()

    def on_window_resize(self, *args):
        """
            Window resize
        :param args:
        :return:
        """
        self.current_vac and self.current_vac.on_window_resize(*args)

    def on_window_left(self, *args):
        """
            Window left changed
        :param args:
        :return:
        """
        self.current_vac and self.current_vac.on_window_left(*args)

    def on_window_top(self, *args):
        """
            Window top changed
        :param args:
        :return:
        """
        self.current_vac and self.current_vac.on_window_top(*args)
