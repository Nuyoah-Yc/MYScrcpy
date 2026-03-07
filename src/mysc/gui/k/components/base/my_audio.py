# -*- coding: utf-8 -*-
"""
    my_audio
    ~~~~~~~~~~~~~~~~~~
    
    Log:
        2026-02-03 0.1.0 Me2sY 创建
"""

__author__ = 'Me2sY'
__version__ = '0.1.0'

__all__ = [
    'MYAudio'
]

from typing import Any, Optional, Callable

from kivy.metrics import dp

from kivymd.uix.dialog import MDDialog, MDDialogHeadlineText, MDDialogContentContainer
from kivymd.uix.divider import MDDivider
from kivymd.uix.dropdownitem import MDDropDownItem, MDDropDownItemText
from kivymd.uix.gridlayout import MDGridLayout
from kivymd.uix.label import MDLabel
from kivymd.uix.menu import MDDropdownMenu
from kivymd.uix.selectioncontrol import MDSwitch

from mysc.gui.k.defs import init_language
from mysc.gui.utils.audio_player import AudioPlayer

_ = init_language()


class MYAudio(MDDialog):

    def __init__(
            self, audio_player: AudioPlayer, auto_open: bool = True,
            cb__changed: Optional[Callable] = None,
            **kwargs
    ):
        super().__init__(**kwargs)

        self.audio_player = audio_player

        self.cb__changed = cb__changed

        # 标题栏
        self.add_widget(MDDialogHeadlineText(text=_('Audio')))

        # 容器
        self.container = MDDialogContentContainer()
        self.add_widget(self.container)

        # 显示当前设备
        device_name = self.audio_player.current_output_device_info

        if device_name is None:
            device_name = _('Select Output Device')
        else:
            device_name = device_name['name']

        self.selected_item = MDDropDownItemText()

        self.widget_source = MDDropDownItem(
            self.selected_item,
            on_release=self.cb__select_device,
            pos_hint={'center_x': 0.5, 'center_y': 0.5},
            size_hint=(1, None), height=dp(80)
        )

        self.selected_item.text = device_name

        # 静音栏
        self.mute_switch = MDSwitch(
            icon_active='volume-mute', icon_active_color='red', icon_inactive='volume-source'
        )

        self.mute_switch.active = self.audio_player.is_muted
        self.mute_switch.bind(on_active=self.cb__mute)

        self.container.add_widget(
            MDGridLayout(
                MDLabel(
                    text=_('Mute'), font_style='Title',
                    size_hint_x=None, width=dp(80)
                ),
                self.mute_switch,
                MDDivider(orientation='vertical'),
                self.widget_source,
                cols=4, spacing=dp(10),
            )
        )

        if auto_open:
            self.open()

    def cb__select_device(self, caller):
        """
            选择设备
        :param caller:
        :return:
        """
        def select_device(device_info: dict[str, Any]):
            menu.dismiss()
            self.audio_player.select_device(device_info['index'])
            self.selected_item.text = device_info['name']
            self.cb__changed()

        menu_items = [
            {
                'text': device['name'],
                'on_release': lambda *args, _device=device: select_device(_device)
            } for device in self.audio_player.get_output_devices()
        ]
        menu = MDDropdownMenu(caller=caller, items=menu_items)
        menu.open()

    def cb__mute(self, caller, is_active: bool):
        """
            静音回调
        :param caller:
        :param is_active:
        :return:
        """
        self.audio_player.set_mute(is_active)
        self.cb__changed()
