# MYScrcpy V3.3.0

### [README in English](README_EN.md)

### python语言实现的一个 [**Scrcpy 3.3**](https://github.com/Genymobile/scrcpy/) 客户端

包含完整的视频、音频、控制解析，**开发友好，引入即用！**

**V3.3** GUI采用 [**Kivy**](https://kivy.org/) / [**KivyMD**](https://kivymd.readthedocs.io/en/latest/) 

现代化界面风格，支持Windows/Ubuntu(X11)/MacOSX，支持多设备连接，鼠标及键盘映射。

Windows
![windows.png](files/images/windows.png)

Ubuntu
![ubuntu.png](files/images/ubuntu.png)

Macosx
![macosx.png](files/images/macosx.png)

### GUI
- 根据设备及当前连接参数，自动记忆窗口大小，同时记忆窗口旋转前位置。在横竖屏切换时，无需频繁调整窗口位置
- 支持Windows/Ubuntu(X11)/MacOS X
- 支持有线、无线连接设备
- 支持设置无线端口
- 可根据设备配置相应连接模式，保存连接参数
  - 例如若使用手机摄像头模式，则video/audio配置，control关闭，并保存为Camera配置组合
  - 使用投屏，则全部配置，并保存为投屏配置组合

### 视频
- 支持h264/h265视频流解析
- 支持按比例调整窗口大小
  - 拉动窗口，进行自由伸缩
  - 根据高度/宽度，自动调整窗口至视频比例

### 音频
- 支持opus/flac/raw
- 支持选择播放设备

### 控制
- **NEW** V3.3 新增蒙版模式
- 优化鼠标控制器
  - 使用 鼠标中键 切换 UHID/触摸模式
  - 支持右键功能选择器
- 新增键盘切换器，使用 F8 切换 UHID/Ctrl模式
- 按键映射创建工具，支持键盘，鼠标等多种控制映射方式，Windows/Ubuntu(X11)/MacOS X 适用
- 支持UHID鼠标，可以实现Android界面中鼠标与PC混用
- 支持UHID-Keyboard，模拟外接键盘，直接输入中文（百度、搜狗输入法测试通过）
- 支持鼠标滚轮滑动，缩放等功能
- 支持创建第二虚拟点，配合左键模拟两指操作
- 侧边栏多种功能键


## 帮助与支持

在使用中有任何问题、想法及建议，欢迎通过以下方式与我联系：

#### QQ群：579618095
![579618095](files/images/qq_group.jpg)

#### 邮箱：Me2sY@outlook.com

#### Blog: [CSDN](https://blog.csdn.net/weixin_43463913)**

## 基本使用

### 1.1 pypi安装

**注意 V3.2.X以上 采用KivyMD 2.X版本 需手动安装**

[KivyMD getting-started](https://kivymd.readthedocs.io/en/latest/getting-started/)

```bash
pip install mysc

# V3.2版本以上 采用 KivyMD 2.X 版本，需手动安装
pip install https://github.com/kivymd/KivyMD/archive/master.zip
```

### 1.2 克隆本项目，本项目采用uv管理
```bash
uv sync
```

### 2. 项目结构：
**注意！V3.3版本架构改动较V3.2较大，仅保留Kivy GUI，同时优化Core相关类及方法**

1. **utils**
定义基本工具类及各类参数
2. **gui**
Kivy/KivyMD 界面实现，包括视频绘制，鼠标事件，UHID鼠标、键盘输入，映射编辑等。
3. **core**
Session、Connection、视频流、音频流、控制流、设备控制器等核心包
4. **libs**
字体、Scrcpy服务包
5. **locales**
国际化（待完成）
6. **statics**
静态文件

### 3. 程序引用使用，便于自行开发

获取视频流，音频及控制同理。
```python
from adbutils import adb

from mysc.core.video import VideoAdapter, VideoKwargs

device = adb.device_list()[0]

# 定义视频适配器
va = VideoAdapter(
    # 定义连接参数
    VideoKwargs(
        video_codec=VideoKwargs.EnumVideoCodec.H264,
        max_fps=30
    )
)

# 发起连接
va.connect(device)

while True:
    
    # Pillow Image
    pil_img = va.get_image()
    
    # RGB np.ndarray
    data = va.get_ndarray(frame_format='rgb24')
    
    # 自定义逻辑

# 关闭连接
va.disconnect()

```

### 4.使用GUI

:exclamation: _Ubuntu等Linux下 使用pyaudio 需要先安装portaudio_
```bash
sudo apt install build-essential python3-dev ffmpeg libav-tools portaudio19-dev
```

启动程序
```bash
python -m mysc.run
```

#### 界面简介

**选择设备界面**
![gui_devices.jpg](files/images/gui_devices.jpg)

**选择连接模式界面**
![gui_connect_mode.jpg](files/images/gui_connect_mode.jpg)

**编辑连接模式界面**
![gui_mode_edit.jpg](files/images/gui_mode_edit.jpg)

**切换连接界面**
![gui_connections.jpg](files/images/gui_connections.jpg)

**侧边功能**
![gui_nav.jpg](files/images/gui_nav.jpg)

**控制代理（映射）界面**
进入编辑模式后，右键界面处增加控制映射按钮。支持FPS模式，技能释放模式（使用技能参数指示器获取参数）鼠标移动模式等
![gui_proxy.jpg](files/images/gui_proxy.jpg)


## 鸣谢

感谢 [**Scrcpy**](https://github.com/Genymobile/scrcpy/) 项目及作者 [**rom1v**](https://github.com/rom1v)，在这一优秀项目基础上，才有了本项目。

感谢 Kivy/KivyMD 等优秀GUI框架

感谢使用到的各个包项目及作者们。有你们的付出，才有了如此好的软件开发环境。

同时感谢各位使用者们，谢谢你们的支持与帮助，也希望MYScrcpy成为你们得心应手的好工具，好帮手。


## 声明

本项目供日常学习（图形、声音、AI训练等）、Android测试、开发等使用。

**请一定注意：**

1.开启手机调试模式存在一定风险，可能会造成数据泄露等风险，使用前确保您了解并可以规避相关风险

**2.本项目不可用于违法犯罪等使用**

**本人及本项目不对以上产生的相关后果负任何责任，请斟酌使用。**

## 历史版本
[V3.2 - V1.7 README.md](files/old_version/README.md)
[V3.2 - V1.7 README_EN.md](files/old_version/README_EN.md)