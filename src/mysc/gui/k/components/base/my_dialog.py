# -*- coding: utf-8 -*-
"""
    my_dialog
    ~~~~~~~~~~~~~~~~~~
    
    Log:
        2026-01-26 0.1.0 Me2sY 创建
"""

__author__ = 'Me2sY'
__version__ = '0.1.0'

__all__ = [
    'MYDialogLoading', 'MYDialogInput'
]

from typing import Callable, Optional

from kivy.clock import Clock
from kivy.metrics import sp
from kivymd.uix.button import MDButton, MDButtonText
from kivymd.uix.dialog import (
    MDDialog, MDDialogHeadlineText, MDDialogSupportingText, MDDialogContentContainer,
    MDDialogButtonContainer
)
from kivymd.uix.divider import MDDivider
from kivymd.uix.progressindicator import MDCircularProgressIndicator
from kivymd.uix.textfield import MDTextField
from kivymd.uix.widget import MDWidget


class MYDialogLoading(MDDialog):
    """
        加载窗口
    """

    def __init__(self, title: str, auto_open:bool = True, **kwargs):
        super().__init__(**kwargs)

        self.auto_dismiss = False

        self.headline = MDDialogHeadlineText(text=title)
        self.add_widget(self.headline)

        self.help_text = MDDialogSupportingText(text=' ')
        self.add_widget(self.help_text)

        self.add_widget(
            MDDialogContentContainer(
                MDCircularProgressIndicator(
                    size_hint=(None, None), size=(sp(40), sp(40)),
                    pos_hint={'center_x': 0.5, 'center_y': 0.5}
                ),
                orientation='vertical',
            )
        )

        if auto_open:
            self.open()

    def update_help_text(self, text: str):
        Clock.schedule_once(lambda dt: setattr(self.help_text, 'text', text), 0)


class MYDialogInput(MDDialog):
    """
        输入界面
    """
    def __init__(
            self,
            title: str,
            cb_confirm: Callable[[str], None],
            widget_text_field: Optional[MDTextField] = None,
            *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.cb_confirm = cb_confirm

        self.add_widget(MDDialogHeadlineText(text=title))

        self.widget_txt = MDTextField(
            pos_hint={'center_x': 0.5, 'center_y': 0.5},
            multiline=False, mode='filled'
        ) if widget_text_field is None else widget_text_field

        self.add_widget(MDDialogContentContainer(
            MDDivider(),
            self.widget_txt,
            orientation='vertical'
        ))
        self.widget_btn_create = MDButton(
            MDButtonText(text='Ok'),
            on_release = self._confirm, style='text'
        )
        self.add_widget(MDDialogButtonContainer(
            MDWidget(),
            MDButton(
                MDButtonText(text='Cancel'),
                on_release=self.dismiss, style='text'
            ),
            self.widget_btn_create
        ))

    def _confirm(self, *args):
        """
            确认回调
        :param args:
        :return:
        """
        self.dismiss()
        if self.widget_txt.text != '': self.cb_confirm(self.widget_txt.text)
