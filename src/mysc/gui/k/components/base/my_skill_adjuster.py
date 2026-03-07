# -*- coding: utf-8 -*-
"""
    my_skill_adjuster
    ~~~~~~~~~~~~~~~~~~
    技能范围计算器

    Log:
        2026-02-21 0.1.0 Me2sY 创建
"""

__author__ = 'Me2sY'
__version__ = '0.1.0'

__all__ = [
    'MYSkillAdjuster'
]

from kivy.graphics import Color, Line
from kivy.uix.label import Label
from kivymd.uix.button import MDIconButton
from kivymd.uix.slider import MDSlider, MDSliderHandle
from kivymd.uix.widget import MDWidget

from mysc.gui.k.defs import init_language

_ = init_language()


class MYSkillAdjuster(MDWidget):

    def __init__(self, vac, **kwargs):
        super().__init__(**kwargs)

        self.vac = vac

        self.ellipse_width = 0.2
        self.ellipse_height = 0.2

        self.y_fix: float = .0
        self.y_rel: float = -.1

        self.bind(pos=self.update_canvas, size=self.update_canvas)

        # Width / 2
        self.w_slider = MDSlider(
            MDSliderHandle(),
            min=0, max=1, value=self.ellipse_width,
            pos_hint={'center_x': 0.5, 'center_y': 0.1},
            size_hint=(0.9, None), height='20dp',
        )
        self.w_slider.bind(value=self.on_param_changed)

        # Height / 2
        self.h_slider = MDSlider(
            MDSliderHandle(),
            min=0, max=1, value=self.ellipse_height,
            pos_hint={'center_x': 0.5, 'center_y': 0.2},
            size_hint=(0.9, None), height='20dp'
        )
        self.h_slider.bind(value=self.on_param_changed)

        # skill y
        self.y_slider = MDSlider(
            MDSliderHandle(),
            min=-0.5, max=0.5, value=self.y_fix,
            pos_hint={'center_x': 0.7, 'center_y': 0.6},
            orientation='vertical',
            size_hint=(None, 0.7), width='20dp',
        )
        self.y_slider.bind(value=self.on_param_changed)

        # real y rel
        self.ry_slider = MDSlider(
            MDSliderHandle(),
            min=-0.2, max=0.2, value=self.y_rel,
            pos_hint={'center_x': 0.8, 'center_y': 0.6},
            orientation='vertical',
            size_hint=(None, 0.7), width='20dp'
        )
        self.ry_slider.bind(value=self.on_param_changed)

        # Info Label
        self.info = Label(text=_('Skill Args'), pos_hint={'center_x': 0.15, 'center_y': 0.5}, font_size='18sp')

        # Close Button
        self.btn__close = MDIconButton(
            icon='close', style='filled', on_release=self.cb__close,
            theme_bg_color='Custom', md_bg_color='red'
        )

    def draw(self):
        """
            初始化
        """
        if self in self.vac.children: return

        self.vac.add_widget(self)
        self.vac.add_widget(self.h_slider)
        self.vac.add_widget(self.w_slider)
        self.vac.add_widget(self.y_slider)
        self.vac.add_widget(self.ry_slider)
        self.vac.add_widget(self.info)
        self.vac.add_widget(self.btn__close)

        self.update_canvas()

    def cb__close(self, *args):
        """
            关闭指示器
        """
        if self not in self.vac.children: return

        self.vac.clear_widgets([
            self.w_slider, self.h_slider, self.y_slider, self.ry_slider, self.info, self.btn__close
        ])
        self.vac.remove_widget(self)

    def on_param_changed(self, *args):
        """
            更新属性
        """
        self.ellipse_width = self.w_slider.value
        self.ellipse_height = self.h_slider.value

        self.y_fix = self.y_slider.value

        self.y_rel = self.ry_slider.value

        self.update_canvas()

        try:

            info = (f"EA/W  : {self.ellipse_width:.5f}\n"
                    f"EB/H  : {self.ellipse_height:.5f}\n"
                    f"EY    : {(0.5 - self.y_fix):.5f}\n"
                    f"Real Y: {(0.5 - self.y_rel):.5f}"
                    )

            self.info.text = info

        except:
            self.info.text = 'Value Error!'

    def update_canvas(self, *args):
        """
            更新绘制图像
        """
        self.canvas.clear()

        cx, cy = self.center
        ecy = cy + self.y_fix * self.vac.height

        width = self.ellipse_width * self.vac.width * 2
        height = self.ellipse_height * self.vac.height * 2

        with self.canvas:
            # 技能环
            Color(0.3, 1, 1, 1)
            Line(ellipse=(cx - width / 2, ecy - height /2,
                          width, height), width=1)
            Line(circle=(cx, ecy, 4), width=3)

            # 绘制实际计算中心点
            Color(1, 0, 0, 0.9)
            Line(circle=(cx, cy + self.y_rel * self.vac.height, 4), width=3)
