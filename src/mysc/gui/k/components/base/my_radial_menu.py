# -*- coding: utf-8 -*-
"""
    my_radial_menu
    ~~~~~~~~~~~~~~~~~~
    
    Log:
        2026-02-01 0.1.0 Me2sY 创建
"""

__author__ = 'Me2sY'
__version__ = '0.1.0'

__all__ = ['MYRadialMenu']

import math
from typing import Optional, Callable

from kivymd.uix.floatlayout import MDFloatLayout
from kivymd.uix.label import MDLabel
from kivy.graphics import Color, Ellipse, Line
from kivy.properties import ListProperty, NumericProperty, BooleanProperty
from kivy.metrics import dp

from mysc.gui.k.defs import Colors
from mysc.utils.vector import ScalePointR


class MYRadialMenu(MDFloatLayout):

    items = ListProperty([])

    menu_radius = NumericProperty(dp(100))
    inner_radius_ratio = NumericProperty(0.2)

    active = BooleanProperty(False)
    selected_index = NumericProperty(-1)

    def __init__(self, cb__select: Callable[[int, str], None], items: Optional[list[str]] = None, **kwargs):
        """
            径向菜单
        :param kwargs:
        """
        super().__init__(**kwargs)
        self.size_hint = (None, None)
        self.size = (self.menu_radius * 2, self.menu_radius * 2)
        self.labels = []  # 存储标签引用

        if items:
            self.items = items

        self.cb__select = cb__select

        self.spr: Optional[ScalePointR] = None

    def open_menu(self, pos, spr: ScalePointR):
        """
            打开菜单
        :param pos:
        :param spr:
        :return:
        """
        self.active = True
        self.center = pos
        self.draw_menu()
        self.create_labels()
        self.spr = spr

    def close_menu(self):
        """
            关闭菜单， 返回选中项
        :return:
        """
        if self.active and self.selected_index != -1:
            self.cb__select(self.selected_index, self.items[self.selected_index])

        self.active = False
        self.selected_index = -1
        self.clear_labels()
        self.canvas.before.clear()

    def clear_labels(self):
        """
            清空文字控件
        :return:
        """
        for label in self.labels:
            self.remove_widget(label)
        self.labels = []

    def create_labels(self):
        """
            创建文字提示
        :return:
        """
        self.clear_labels()
        if not self.items: return

        step = 360 / len(self.items)

        # 0.5 是边缘，所以除以 4 得到中间偏移比
        text_dist_ratio = (1 + self.inner_radius_ratio) / 4

        for i, text in enumerate(self.items):
            # 计算文字的中心角度 (12点钟为0度，顺时针偏移)
            angle_deg = i * step + (step / 2)
            angle_rad = math.radians(angle_deg)

            # 计算偏移比例 (基于中心点 0.5, 0.5)
            # sin/cos 对应 Kivy 的顺时针 0度在上坐标系
            offset_x = text_dist_ratio * math.sin(angle_rad)
            offset_y = text_dist_ratio * math.cos(angle_rad)

            lbl = MDLabel(
                text=text, theme_text_color="Custom", text_color='white', font_style='Label',
                halign="center", valign="middle",
                size_hint=(None, None), size=(dp(80), dp(40)),
                pos_hint={
                    'center_x': 0.5 + offset_x,
                    'center_y': 0.5 + offset_y
                }
            )
            self.add_widget(lbl)
            self.labels.append(lbl)

    def get_angle_from_pos(self, pos):
        """
            计算角度
        :param pos:
        :return:
        """
        dx = pos[0] - self.center_x
        dy = pos[1] - self.center_y
        angle = math.degrees(math.atan2(dx, dy))
        if angle < 0: angle += 360
        return angle

    def on_mouse_move(self, pos):
        """
            鼠标移动
        :param pos:
        :return:
        """
        if not self.active: return

        dist = math.sqrt((pos[0] - self.center_x) ** 2 + (pos[1] - self.center_y) ** 2)

        if self.menu_radius * self.inner_radius_ratio < dist:
            angle = self.get_angle_from_pos(pos)
            step = 360 / len(self.items)
            self.selected_index = int(angle / step)
        else:
            self.selected_index = -1

        self.update_visuals()

    def update_visuals(self):
        """
            更新选中状态
        :return:
        """
        for i, lbl in enumerate(self.labels):
            lbl.text_color = 'white' if i != self.selected_index else Colors.Orange
            lbl.font_style = 'Label' if i != self.selected_index else 'Body'

        self.draw_menu()

    def draw_menu(self):
        """
            绘制菜单
        :return:
        """
        self.canvas.before.clear()
        if not self.active or not self.items: return

        step = 360 / len(self.items)

        with self.canvas.before:
            # 绘制选中扇形
            for i in range(len(self.items)):
                if i == self.selected_index:
                    Color(0.12, 0.58, 0.95, 0.9)  # 选中蓝色
                else:
                    Color(0.15, 0.15, 0.15, 0.9)  # 未选中深灰

                Ellipse(pos=self.pos, size=self.size, angle_start=i * step, angle_end=(i + 1) * step)

            # 绘制分割线
            Color(1, 1, 1, 0.8)
            for i in range(len(self.items)):
                angle_rad = math.radians(i * step)
                Line(points=[self.center_x, self.center_y,
                             self.center_x + self.menu_radius * math.sin(angle_rad),
                             self.center_y + self.menu_radius * math.cos(angle_rad)],
                     width=dp(1))
