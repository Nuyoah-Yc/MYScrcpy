# -*- coding: utf-8 -*-
"""
    my_snack_bar
    ~~~~~~~~~~~~~~~~~~
    
    Log:
        2026-01-26 0.1.0 Me2sY 创建
"""

__author__ = 'Me2sY'
__version__ = '0.1.0'

__all__ = [
    'MYSnackBar',
    'MYSnackBarSuccess', 'MYSnackBarError', 'MYSnackBarWarning', 'MYSnackBarInfo',
]

from typing import ClassVar, Optional
import unicodedata

from kivy.metrics import dp
from kivymd.uix.snackbar import MDSnackbar, MDSnackbarText

from mysc.gui.k.defs import CombineColors, init_language

_ = init_language()


class MYSnackBar(MDSnackbar):

    DEFAULT_TEXT: ClassVar[str] = ''
    DEFAULT_COMBINE_COLOR: ClassVar[CombineColors] = CombineColors.white

    def __init__(self, text: Optional[str] = None, auto_open:bool=True, **kwargs):

        color = kwargs.pop('color', self.DEFAULT_COMBINE_COLOR)

        kwargs.setdefault('y', dp(80))
        kwargs.setdefault('pos_hint', {'center_x': .5})

        kwargs.setdefault('duration', 1)
        kwargs.setdefault('background_color', color.value[0])

        text = self.DEFAULT_TEXT if text is None else text

        width = 0

        for char in text:
            # 计算中文宽度
            status = unicodedata.east_asian_width(char)
            if status in ('W', 'F', 'A'):
                width += 2
            else:
                width += 1

        kwargs.setdefault('size_hint_x', None)
        kwargs.setdefault('width', min(width * dp(18), dp(400)))

        super().__init__(**kwargs)

        self.add_widget(
            MDSnackbarText(
                text=self.DEFAULT_TEXT if text is None else text,
                font_style='Body', theme_text_color='Custom',
                text_color=color.value[1],
                pos_hint={'center_x': .5, 'center_y': .5},
            )
        )
        if auto_open:
            self.open()


class MYSnackBarSuccess(MYSnackBar):
    DEFAULT_TEXT = _('Success')
    DEFAULT_COMBINE_COLOR = CombineColors.green


class MYSnackBarError(MYSnackBar):
    DEFAULT_TEXT = _('Error')
    DEFAULT_COMBINE_COLOR = CombineColors.red


class MYSnackBarWarning(MYSnackBar):
    DEFAULT_TEXT = _('Warning')
    DEFAULT_COMBINE_COLOR = CombineColors.yellow


class MYSnackBarInfo(MYSnackBar):
    DEFAULT_TEXT = _('Info')
    DEFAULT_COMBINE_COLOR = CombineColors.grey
