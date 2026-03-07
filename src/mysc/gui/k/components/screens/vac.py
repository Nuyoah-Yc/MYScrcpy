# -*- coding: utf-8 -*-
"""
    VideoAudioControl
    ~~~~~~~~~~~~~~~~~~
    
    Log:
        2026-01-28 0.1.0 Me2sY 创建
"""

__author__ = 'Me2sY'
__version__ = '0.1.0'

__all__ = [
    'ScreenVAC'
]

from dataclasses import dataclass
from functools import wraps
import pathlib
import time
from typing import Optional

from kivy.core.window import Window
from kivy.clock import Clock
from kivy.graphics import Color, Rectangle
from kivy.graphics.texture import Texture
from kivy.metrics import Metrics

from kivymd.uix.label import MDIcon
from kivymd.uix.menu import MDDropdownMenu
from kivymd.uix.widget import MDWidget

from mysc.core.device import MYDevice
from mysc.core.session import Session
from mysc.gui.k.components.base.my_audio import MYAudio
from mysc.gui.k.components.base.my_screen import MYScreen
from mysc.gui.k.components.base.my_navigation import MYNavigation
from mysc.gui.k.components.base.my_skill_adjuster import MYSkillAdjuster
from mysc.gui.k.components.base.my_snack_bar import MYSnackBarWarning
from mysc.gui.k.defs import Colors, CombineColors, init_language
from mysc.gui.utils.audio_player import AudioPlayer
from mysc.gui.k.components.base.my_control_layer import ControlLayer
from mysc.utils.keys import ADBKeyCode
from mysc.utils.storage import JSONStorage
from mysc.utils.vector import Coordinate, EnumDirection, Point

_ = init_language()


@dataclass
class JSVac(JSONStorage):
    """
        设备 VAC 存储
    """
    Prefix = 'VAC_'

    v_pos_x: int = 400
    v_pos_y: int = 200
    v_size_width: int = 500
    v_size_height: int = 800

    h_pos_x: int = 400
    h_pos_y: int = 200
    h_size_width: int = 800
    h_size_height: int = 500

    v__is_paused: bool = False

    is_muted: bool = False
    output_device_name: str = ''
    muted_when_switch: bool = True

    opacity_set: float = 0.5
    opacity_on: float = 0.05


class VideoLayer(MDWidget):
    """
        视频层
    """
    @staticmethod
    def current_check(func):
        """
            判断是否为当前显示页面
        :param func:
        :return:
        """
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            if not self.screen.is_current:
                return

            func(self, *args, **kwargs)

        return wrapper

    def __init__(self, screen: 'ScreenVAC', **kwargs):

        super().__init__(**kwargs)

        self.screen = screen
        self.va = self.screen.sess.va
        self.cfg = self.screen.cfg
        self.bind(size=self.bind__size)

        # 暂时关闭暂停功能
        self.cfg.v__is_paused = False

        self._is_paused: bool = self.cfg.v__is_paused

        if self.va is None:
            # 无视频连接
            self.coord_frame = Coordinate(*self.screen.my_device.adb_device.window_size())
            with self.canvas.before:
                Color(*Colors.TouchPad)
                self.video_rect = Rectangle()

            self.add_widget(MDIcon(icon='video-off'))

            MYSnackBarWarning(_('Video Disabled'))

        else:
            # 等待就绪
            while not self.va.is_ready:
                time.sleep(0.001)
                if not self.va.connection.is_connected:
                    raise RuntimeError(_('Video connection failed!'))

            self.va.is_paused = self.cfg.v__is_paused

            self.frame_n: int = -1

            self.coord_frame = self.va.coordinate

            # 使用 RGB 模式， RGBA Linux下 to_ndarray 内存错误
            self.texture_v = Texture.create(size=self.coord_frame.vertical_wh.t, colorfmt='rgb')
            self.texture_h = Texture.create(size=self.coord_frame.horizontal_wh.t, colorfmt='rgb')

            self.texture_v.flip_vertical()
            self.texture_h.flip_vertical()

            # 定义视频显示区
            with self.canvas.before:
                # 定义Color 否则透明无显示
                Color(1, 1, 1, 1)
                self.video_rect = Rectangle()

            # 创建更新触发器
            self.trigger = Clock.create_trigger(self.update_frame)
            self.va.frame_update_callback = self.trigger

        self.is_changing_sp: bool = False

    def switch_pause(self, status: Optional[bool] = None):
        """
            切换暂停状态
        :param status:
        :return:
        """
        if status is None:
            self.cfg.v__is_paused = not self.cfg.v__is_paused
            if self.va:
                self.va.is_paused = self.cfg.v__is_paused
                self.cfg.dump()
        else:
            if status == self.cfg.v__is_paused: return
            else: self.switch_pause()

    def bind__size(self, instance, size):
        """
            更新显示框 Size
        :param instance:
        :param size:
        :return:
        """
        self.video_rect.size = size

    def update_frame(self, dt):
        """
            更新视频 Frame
        :return:
        """
        if self.cfg.v__is_paused: return

        try:
            if self.frame_n == self.va.frame_n: return

            self.frame_n = self.va.frame_n

            last_frame = self.va.last_frame

            frame_coord = Coordinate(last_frame.width, last_frame.height)

            if frame_coord != self.coord_frame:

                # 屏幕发生变化
                if frame_coord.rotate() != self.coord_frame:
                    self.screen_changed()

                self.coord_frame = frame_coord
                self.rotation_callback(frame_coord)

            if frame_coord.current_direction == EnumDirection.VERTICAL:
                self.texture_v.blit_buffer(last_frame.to_ndarray(format='rgb24').tobytes(), colorfmt='rgb')
                self.video_rect.texture = self.texture_v
            else:
                self.texture_h.blit_buffer(last_frame.to_ndarray(format='rgb24').tobytes(), colorfmt='rgb')
                self.video_rect.texture = self.texture_h

        except Exception as e:
            ...

    def screen_changed(self):
        """
            屏幕变化（折叠屏展开等）
        :return:
        """
        self.screen.set_video()
        MYSnackBarWarning(_('Screen Changed!'))

    @current_check
    def rotation_callback(self, frame_coord: Coordinate):
        """
            旋转时回调
        :return:
        """
        self.update_window_size_and_pos()

    def update_window_size_and_pos(self):
        """
            更新窗口Size和Pos
        :return:
        """
        self.is_changing_sp = True
        self.update_window_size()
        self.update_window_pos()
        self.is_changing_sp = False

    def update_window_size(self):
        """
            更新 Windows Size
        :return:
        """
        if self.coord_frame.current_direction == EnumDirection.HORIZONTAL:
            Window.size = self.cfg.h_size_width / Metrics.density, self.cfg.h_size_height / Metrics.density
        else:
            Window.size = self.cfg.v_size_width / Metrics.density, self.cfg.v_size_height / Metrics.density

    def update_window_pos(self):
        """
            更新 Windows Pos
        :return:
        """
        if self.coord_frame.current_direction == EnumDirection.HORIZONTAL:
            Window.left = self.cfg.h_pos_x
            Window.top = self.cfg.h_pos_y
        else:
            Window.left = self.cfg.v_pos_x
            Window.top = self.cfg.v_pos_y

    def set_opacity(self, is_opacity: bool):
        """
            设置透明
        :return:
        """
        if is_opacity:
            self.canvas.before.clear()
            self.switch_pause()
        else:
            with self.canvas.before:
                Color(1, 1, 1, 1)
                self.video_rect = Rectangle()
            self.switch_pause()
            self.screen_changed()


class AudioController:
    def __init__(self, screen: 'ScreenVAC'):
        """
            声音连接控制器
        :param screen:
        """
        self.screen = screen
        self.cfg: JSVac = screen.cfg

        self.is_activated: bool = False
        self.last_mute_state: bool = self.cfg.is_muted

        self.aa = self.screen.sess.aa

        if self.aa:
            self.audio_player = AudioPlayer()
            self.audio_player.start(
                device_index=self.audio_player.get_device_index_by_name(self.cfg.output_device_name),
                is_muted=self.cfg.is_muted
            )
            self.aa.frame_update_callback = self.audio_player.play
            self.dialog = MYAudio(self.audio_player, False, self.cb__changed)
            self.is_activated = True

    def cb__changed(self):
        """
            状态变化，更新配置文件
        :return:
        """
        self.cfg.is_muted = self.audio_player.is_muted
        self.cfg.output_device_name = self.audio_player.current_output_device_info['name']
        self.nav_btn.icon = 'speaker-off' if self.audio_player.is_muted else 'speaker'
        self.cfg.dump()

    def activate(self):
        """
            激活
        :return:
        """
        if not self.is_activated: return

        if self.cfg.muted_when_switch:
            self.audio_player.set_mute(self.last_mute_state)

        self.nav_btn = self.screen.nav.add_main_button(
            'speaker-off' if self.audio_player.is_muted else 'speaker',
            lambda caller: self.dialog.open(),
            theme_bg_color='Custom', md_bg_color=Colors.SoftLinen
        )

    def deactivate(self):
        """
            失活
        :return:
        """
        if not self.is_activated: return

        # 保存当前静音状态，设置静音
        if self.cfg.muted_when_switch:
            self.last_mute_state = self.audio_player.is_muted
            self.audio_player.set_mute(True)


class ScreenVAC(MYScreen):

    @property
    def direction(self) -> EnumDirection:
        return self.vl.coord_frame.current_direction

    def get_direction(self) -> EnumDirection:
        return self.vl.coord_frame.current_direction

    def __init__(self, my_device: MYDevice, mode, nav: MYNavigation, main, **kwargs):

        super().__init__(nav, main, **kwargs)

        self.my_device = my_device
        self.mode = mode

        self.sess = Session.from_dict(self.my_device, self.mode.storage_kwargs)

        # 配置文件路径
        self.cfg_cls = JSVac.get_cls(StoragePath=pathlib.Path(f"{self.my_device.serial_no}"))
        self.cfg: JSVac = self.cfg_cls.load(self.mode.save_key)

        # 加载配置参数
        if self.cfg is None:
            # 最大窗口大小

            self.cfg = self.cfg_cls(save_key=self.mode.save_key)

            coord = Coordinate(
                *self.my_device.adb_device.window_size()
            ).get_max_coordinate(1200, 800)

            self.cfg.h_size_width, self.cfg.h_size_height = (coord.horizontal_wh + Coordinate(40, 20)).t
            self.cfg.v_size_width, self.cfg.v_size_height = (coord.vertical_wh + Coordinate(40, 20)).t
            self.cfg.h_pos_x, self.cfg.h_pos_y = Window.left, Window.top
            self.cfg.v_pos_x, self.cfg.v_pos_y = Window.left, Window.top

            self.cfg.dump()

        self.vl: Optional[VideoLayer] = None
        self.set_video()

        self.cc: ControlLayer = ControlLayer(self)
        self.add_widget(self.cc)

        self.ac: AudioController = AudioController(self)

        self.skill_adjuster = MYSkillAdjuster(self)

    def set_video(self):
        """
            设置视频显示控制器
            当视频显示屏幕变化（折叠屏）后重置显示
        :return:
        """
        if self.vl:
            self.remove_widget(self.vl)

        self.vl: VideoLayer = VideoLayer(self)
        self.add_widget(self.vl, canvas='before')

        # 若为Crop模式，进行坐标转换
        if self.sess.va and self.sess.ca:
            crop = self.sess.va._kwargs.crop_
            if crop:
                wh: Coordinate = crop[0]
                xy: Point = crop[1]

                # 确定偏移方向
                if wh.current_direction == EnumDirection.VERTICAL:
                    self.sess.ca.offset_x, self.sess.ca.offset_y = xy.t
                else:
                    self.sess.ca.offset_y, self.sess.ca.offset_x = xy.t
                self.sess.ca.set_wm_coord(wh)

    def on_enter(self, *args):
        """
            进入界面
        :param args:
        :return:
        """
        # 调整窗口位置及大小
        self.main.screen_connections.current_vac = self

        self.vl.update_window_size_and_pos()
        Window.set_title(self.my_device.serial_no + ' - ' + self.mode.save_key)

        # Nav增加控制按钮
        self.nav.clear_buttons()
        self.nav.add_main_button('close-circle', self.cb__disconnect)
        self.nav.add_main_button('move-resize', self.cb__resize_menu)

        # 激活控制
        self.ac.activate()
        self.cc.activate()

        # 注册按钮
        self.register_nav_buttons()

    def cb__resize_menu(self, caller):
        """
            Resize Menu
        :param caller:
        :return:
        """
        def resize(direction: EnumDirection):
            menu.dismiss()

            w, h = Window.size

            # 确定屏幕坐标系
            if self.sess.va:
                coord = self.sess.va.coordinate
            else:
                coord = Coordinate(*self.my_device.adb_device.window_size())

            nw, nh = self.size

            if direction == EnumDirection.VERTICAL:
                Window.size = (w / Metrics.density, ((coord.w2h(nw) - nh) + h) / Metrics.density)
            else:
                Window.size = (((coord.h2w(nh) - nw) + w) / Metrics.density, h / Metrics.density)

        # 创建菜单
        menu = MDDropdownMenu(
            caller=caller, items=[
                {
                    'text': _('Horizontal'), 'leading_icon': 'arrow-expand-horizontal',
                    'on_release': lambda *_args, direction=EnumDirection.HORIZONTAL: resize(direction)
                },
                {
                    'text': _('vertical'), 'leading_icon': 'arrow-expand-vertical',
                    'on_release': lambda *_args, direction=EnumDirection.VERTICAL: resize(direction)
                },
            ]
        )

        menu.open()

    def on_pre_leave(self, *args):
        """
            离开界面，保存配置
        :param args:
        :return:
        """
        self.main.screen_connections.current_vac = None
        self.cfg.dump()

        self.cc.deactivate()
        self.ac.deactivate()

        # 取消透明状态
        if Window.opacity != 1:
            Window.opacity = 1
            try:
                self.vl.set_opacity(False)
            except:
                ...

    def cb__mouse_switch(self, caller):
        """
            Mouse 模式切换
        :param caller:
        :return:
        """
        self.cc.mouse_handler.switch_mode()

    def cb__disconnect(self, caller, auto_switch: bool=True):
        """
            断开连接
        :param caller:
        :param auto_switch: 自动切换至 Device 界面
        :return:
        """
        self.main.screen_connections.remove_vac(self)
        self.sess.disconnect()
        if auto_switch: self.manager.switch_to(self.main.screen_devices)

    def on_window_resize(self, *args):
        """
            窗口移动
        :param args:
        :return:
        """
        if not self.is_current or self.vl.is_changing_sp:
            return

        i, w, h = args

        if self.vl.coord_frame.current_direction == EnumDirection.HORIZONTAL:
            self.cfg.h_size_width = w
            self.cfg.h_size_height = h
        else:
            self.cfg.v_size_width = w
            self.cfg.v_size_height = h

        self.cfg.dump()

    def on_window_left(self, *args):
        """
            窗口 x 变化
        :param args:
        :return:
        """
        if not self.is_current or self.vl.is_changing_sp:
            return

        i, left = args

        if self.vl.coord_frame.current_direction == EnumDirection.HORIZONTAL:
            self.cfg.h_pos_x = left
        else:
            self.cfg.v_pos_x = left

        self.cfg.dump()

    def on_window_top(self, *args):
        """
            窗口 y 变化
        :param args:
        :return:
        """
        if not self.is_current or self.vl.is_changing_sp:
            return

        i, top = args

        if self.vl.coord_frame.current_direction == EnumDirection.HORIZONTAL:
            self.cfg.h_pos_y = top
        else:
            self.cfg.v_pos_y = top

        self.cfg.dump()

    def set_opacity(self):
        """
            透明设置
        :return:
        """
        if Window.opacity == 1:
            Window.opacity = self.cfg.opacity_set

        elif round(Window.opacity, 1) == self.cfg.opacity_set:
            Window.opacity = self.cfg.opacity_on
            self.vl.set_opacity(True)

        else:
            Window.opacity = 1
            self.vl.set_opacity(False)

    def register_nav_buttons(self):
        """
            注册导航按钮
        :return:
        """
        def cb__adb(adb_code: ADBKeyCode):
            self.my_device.adb_device.keyevent(adb_code)

        self.nav.add_scroll_button(
            icon='home', callback=lambda caller, adb_code=ADBKeyCode.HOME: cb__adb(adb_code),
            color=CombineColors.grey_dust
        )
        self.nav.add_scroll_button(
            icon='arrow-left', callback=lambda caller, adb_code=ADBKeyCode.BACK: cb__adb(adb_code),
            color=CombineColors.grey_dust
        )
        self.nav.add_scroll_button(
            icon='apps', callback=lambda caller, adb_code=ADBKeyCode.APP_SWITCH: cb__adb(adb_code),
            color=CombineColors.grey_dust
        )

        # skill adjuster
        self.nav.add_scroll_button(
            icon='vector-circle', callback=lambda caller: self.skill_adjuster.draw()
        )

        # opacity
        self.nav.add_scroll_button(
            icon='square-opacity', callback=lambda caller: self.set_opacity(),
            color=CombineColors.orange
        )

        self.nav.add_scroll_button(
            icon='power', callback=lambda caller, adb_code=ADBKeyCode.POWER: cb__adb(adb_code),
            color=CombineColors.red
        )

        self.nav.add_scroll_button(
            icon='bell', callback=lambda caller, adb_code=ADBKeyCode.NOTIFICATION: cb__adb(adb_code),
            color=CombineColors.grey
        )

        self.nav.add_scroll_button(
            icon='volume-mute', callback=lambda caller, adb_code=ADBKeyCode.KB_VOLUME_MUTE: cb__adb(adb_code),
            color=CombineColors.grey
        )
        self.nav.add_scroll_button(
            icon='volume-plus', callback=lambda caller, adb_code=ADBKeyCode.KB_VOLUME_UP: cb__adb(adb_code),
            color=CombineColors.grey
        )
        self.nav.add_scroll_button(
            icon='volume-minus', callback=lambda caller, adb_code=ADBKeyCode.KB_VOLUME_DOWN: cb__adb(adb_code),
            color=CombineColors.grey
        )
        self.nav.add_scroll_button(
            icon='microphone-off', callback=lambda caller, adb_code=ADBKeyCode.MIC_MUTE: cb__adb(adb_code),
            color=CombineColors.grey
        )

        self.nav.add_scroll_button(
            icon='play-pause', callback=lambda caller, adb_code=ADBKeyCode.KB_MEDIA_PLAY_PAUSE: cb__adb(adb_code),
            color=CombineColors.grey
        )
        self.nav.add_scroll_button(
            icon='skip-next', callback=lambda caller, adb_code=ADBKeyCode.KB_MEDIA_NEXT_TRACK: cb__adb(adb_code),
            color=CombineColors.grey
        )
        self.nav.add_scroll_button(
            icon='skip-previous', callback=lambda caller, adb_code=ADBKeyCode.KB_MEDIA_PREV_TRACK: cb__adb(adb_code),
            color=CombineColors.grey
        )

        self.nav.add_scroll_button(
            icon='camera', callback=lambda caller, adb_code=ADBKeyCode.CAMERA: cb__adb(adb_code),
            color=CombineColors.grey
        )
        self.nav.add_scroll_button(
            icon='magnify-plus', callback=lambda caller, adb_code=ADBKeyCode.ZOOM_IN: cb__adb(adb_code),
            color=CombineColors.grey
        )
        self.nav.add_scroll_button(
            icon='magnify-minus', callback=lambda caller, adb_code=ADBKeyCode.ZOOM_OUT: cb__adb(adb_code),
            color=CombineColors.grey
        )

        self.nav.add_scroll_button(
            icon='brightness-7', callback=lambda caller, adb_code=ADBKeyCode.BRIGHTNESS_UP: cb__adb(adb_code),
            color=CombineColors.grey
        )
        self.nav.add_scroll_button(
            icon='brightness-5', callback=lambda caller, adb_code=ADBKeyCode.BRIGHTNESS_DOWN: cb__adb(adb_code),
            color=CombineColors.grey
        )

        self.nav.add_scroll_button(
            icon='assistant', callback=lambda caller, adb_code=ADBKeyCode.VOICE_ASSIST: cb__adb(adb_code),
            color=CombineColors.grey
        )
        self.nav.add_scroll_button(
            icon='web', callback=lambda caller, adb_code=ADBKeyCode.EXPLORER: cb__adb(adb_code),
            color=CombineColors.grey
        )
        self.nav.add_scroll_button(
            icon='calculator', callback=lambda caller, adb_code=ADBKeyCode.CALCULATOR: cb__adb(adb_code),
            color=CombineColors.grey
        )
        self.nav.add_scroll_button(
            icon='calendar', callback=lambda caller, adb_code=ADBKeyCode.CALENDAR: cb__adb(adb_code),
            color=CombineColors.grey
        )
        self.nav.add_scroll_button(
            icon='phone', callback=lambda caller, adb_code=ADBKeyCode.CALL: cb__adb(adb_code),
            color=CombineColors.grey
        )
        self.nav.add_scroll_button(
            icon='contacts', callback=lambda caller, adb_code=ADBKeyCode.CONTACTS: cb__adb(adb_code),
            color=CombineColors.grey
        )
