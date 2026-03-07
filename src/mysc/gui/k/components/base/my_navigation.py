# -*- coding: utf-8 -*-
"""
    侧边导航栏
    ~~~~~~~~~~~~~~~~~~
    
    Log:
        2026-01-26 0.1.0 Me2sY 创建
"""

__author__ = 'Me2sY'
__version__ = '0.1.0'

__all__ = [
    'EnumButtonType',
    'MYNavigation',
]


from enum import Enum, auto
from typing import Callable, Optional

from kivy.metrics import sp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDFabButton, MDIconButton
from kivymd.uix.divider import MDDivider
from kivymd.uix.gridlayout import MDGridLayout
from kivymd.uix.scrollview import MDScrollView

from mysc.gui.k.defs import CombineColors


class EnumButtonType(Enum):
    Main = auto()
    Scroll = auto()
    Fixed = auto()


class MYNavigation(MDGridLayout):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.cols = 1

        self.spacing = sp(4)
        self.padding = sp(4)

        _size_btn = MDFabButton(icon='resize', style='small')
        self.size_hint_x = None
        self.width = _size_btn.width + sp(10)

        # 定位器
        self.div_main = MDDivider(size_hint_x=None, width=0)
        self.add_widget(self.div_main)

        self.layout_scroll = MDBoxLayout(
            adaptive_height=True, orientation='vertical', spacing=sp(2)
        )
        self._layout_scroll = MDScrollView(
            self.layout_scroll, do_scroll_x=False, bar_width=1
        )
        self.add_widget(self._layout_scroll)

        # 定位器
        self.div_fix = MDDivider()
        self.add_widget(self.div_fix)

        self.main_buttons: list[MDFabButton] = []
        self.scroll_buttons: list[MDIconButton] = []
        self.fixed_buttons: list[MDFabButton] = []

    def clear_buttons(self):
        """
            清空Main及Scroll内容
        """
        self.clear_widgets(
            [
                child for child in self.children[self.children.index(self.div_fix):] if child not in [
                self.div_main, self.div_fix, self._layout_scroll
            ]])
        self.layout_scroll.clear_widgets()

        self.main_buttons = []
        self.scroll_buttons = []

    def add_main_button(self, icon: str, callback: Callable, **kwargs) -> MDFabButton:
        """
            增加主要按钮
        :param icon:
        :param callback:
        :param kwargs:
        :return:
        """
        color: Optional[CombineColors] = kwargs.pop('color', None)
        if color is not None:
            kwargs['theme_bg_color'] = 'Custom'
            kwargs['theme_icon_color'] = 'Custom'
            kwargs['md_bg_color'] = color.value[0]
            kwargs['icon_color'] = color.value[1]

        btn = MDFabButton(icon=icon, style='small', valign='center', on_release=callback, **kwargs)
        self.add_widget(btn, index=self.children.index(self.div_main) + 1)
        self.main_buttons.append(btn)
        return btn

    def add_scroll_button(self, icon: str, callback: Callable, **kwargs) -> MDIconButton:
        """
            添加滚动按钮
        :param icon:
        :param callback:
        :return:
        """
        color: Optional[CombineColors] = kwargs.pop('color', None)
        if color is not None:
            kwargs['theme_bg_color'] = 'Custom'
            kwargs['theme_icon_color'] = 'Custom'
            kwargs['md_bg_color'] = color.value[0]
            kwargs['icon_color'] = color.value[1]

        btn = MDIconButton(icon=icon, style='tonal', valign='center', on_release=callback, **kwargs)
        self.layout_scroll.add_widget(btn)
        self.scroll_buttons.append(btn)
        return btn

    def add_fixed_button(self, icon: str, callback: Callable, **kwargs) -> MDFabButton:
        """
            添加底部固定按钮
        :param icon:
        :param callback:
        :return:
        """
        btn = MDFabButton(icon=icon, style='small', valign='center', on_release=callback, **kwargs)
        self.add_widget(btn, index=self.children.index(self.div_fix))
        self.fixed_buttons.append(btn)
        return btn

    def add_button(
            self, icon: str, callback: Callable, button_type: EnumButtonType, **kwargs
    ) -> MDFabButton | MDIconButton:
        """
            增加按钮
        :param icon:
        :param callback:
        :param button_type:
        :param kwargs:
        :return:
        """
        match button_type:
            case EnumButtonType.Main:
                return self.add_main_button(icon, callback, **kwargs)
            case EnumButtonType.Scroll:
                return self.add_scroll_button(icon, callback, **kwargs)
            case EnumButtonType.Fixed:
                return self.add_fixed_button(icon, callback, **kwargs)
