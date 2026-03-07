# -*- coding: utf-8 -*-
"""
    __init__.py
    ~~~~~~~~~~~~~~~~~~
    
    Log:
        2026-01-20 0.1.0 Me2sY 创建
"""

__author__ = 'Me2sY'
__version__ = '0.1.0'

__all__ = [
    'KeyMapper'
]

from kivy.core.window import Keyboard

from mysc.utils.keys import UnifiedKeys, KeyMapper


# 注册 kivy 按键 至 KeyMapper
# Kivy使用 pygame 键位键值

key_mapper = {}

for key, code in Keyboard.keycodes.items():
    _key = {
        'rshift': 'SHIFT_R',
        'lctrl': 'CONTROL_L',
        'rctrl': 'CONTROL_R',
        'alt-gr': 'ALT_R',
        'pageup': 'PAGE_UP',
        'pagedown': 'PAGE_DOWN',
        'numpaddecimal': 'NP_PERIOD',
        'numpaddivide': 'NP_DIVIDE',
        'numpadmul': 'NP_MULTIPLY',
        'numpadsubstract': 'NP_MINUS',
        'numpadadd': 'NP_PLUS',
        'numpadenter': 'NP_ENTER',
        'spacebar': 'SPACE',
        '[': 'BRACKET_L',
        ']': 'KB_BRACKET_R',
        ';': 'KB_COLON',
        '=': 'KB_EQUALS',
        '-': 'KB_MINUS',
        '/': 'KB_SLASH',
        '`': 'KB_BACKQUOTE',
        '\\': 'KB_BACKSLASH',
        "'": 'KB_QUOTE',
        ',': 'KB_COMMA',
        '.': 'KB_PERIOD'
    }.get(key, key)

    if _key.startswith('numpad'):
        _key = 'NP_' + _key[-1]

    uks = UnifiedKeys.filter_name(_key)
    if uks:
        key_mapper[code] = uks

KeyMapper.register('ky', key_mapper)
