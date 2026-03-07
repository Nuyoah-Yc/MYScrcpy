# -*- coding: utf-8 -*-
"""
    defs
    ~~~~~~~~~~~~~~~~~~
    
    Log:
        2026-01-20 0.1.0 Me2sY 创建
"""

__author__ = 'Me2sY'
__version__ = '0.1.0'

__all__ = [
    'init_language',
    'Colors', 'CombineColors'

]

import gettext
from enum import Enum
from typing import Optional

from mysc.utils.params import Param


def init_language(language: Optional[str] = 'zh_CN'):
    """
        初始化语言
    """
    try:
        translator = gettext.translation(
            domain=Param.PROJECT_NAME,
            localedir=Param.PATH_LOCALES,
            languages=[language],
            fallback=True
        )
    except FileNotFoundError:
        translator = gettext.NullTranslations()

    translator.install()
    return translator.gettext


_ = init_language()


class Colors:
    """
        色彩定义
    """
    Black = 'black'
    White = 'white'
    Red = '#ff6b81'

    Green = '#7bed9f'
    GreenLight = '#8BBD8B'
    Blue = '#1e90ff'
    BlueLight = '#57B8FF'
    Grey = '#e2e2e2'
    GreyDust = '#D6D2D2'
    Yellow = '#f1c40f'
    Orange = '#ffa502'
    PaleOak = '#DBCFB0'
    SoftLinen = '#E0E2DB'

    Background = [1, 1, 1, 1]
    TouchPad = [.749, .749, .749, 1]


class CombineColors(Enum):
    """
        Button 配色
    """
    black = (Colors.Black, Colors.White)
    white = (Colors.White, Colors.Black)
    red = (Colors.Red, Colors.White)
    green = (Colors.Green, Colors.Black)
    blue = (Colors.Blue, Colors.Black)
    grey = (Colors.Grey, Colors.Black)
    yellow = (Colors.Yellow, Colors.Black)
    orange = (Colors.Orange, Colors.Black)
    grey_dust = (Colors.GreyDust, Colors.Black)
