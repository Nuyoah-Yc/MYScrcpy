# -*- coding: utf-8 -*-
"""
    params
    ~~~~~~~~~~~~~~~~~~
    
    Log:
        2026-01-17 2.0.0 Me2sY  重构

        2024-10-24 1.7.0 Me2sY  适配 Scrcpy 2.7.0

        2024-09-29 1.6.4 Me2sY  新增 Action 分类

        2024-09-18 1.6.0 Me2sY  重构 Extensions 体系

        2024-09-12 1.5.10 Me2sY 新增 Extensions

        2024-09-10 1.5.9 Me2sY  新增文件管理器相关路径

        2024-09-02 1.5.2 Me2sY  Pypi发布

        2024-08-24 1.3.7 Me2sY  从utils中抽离

"""

__author__ = 'Me2sY'
__version__ = '2.0.0'

__all__ = ['Param']

import pathlib
from typing import ClassVar

PROJECT_NAME = 'mysc'


def project_path() -> pathlib.Path:
    """
        获取项目根目录
    :return:
    """
    for _ in pathlib.Path(__file__).resolve().parents:
        if _.name == PROJECT_NAME:
            return _

    raise FileNotFoundError(PROJECT_NAME)


class Param:

    PROJECT_NAME: ClassVar[str] = PROJECT_NAME
    AUTHOR: ClassVar[str] = __author__
    VERSION: ClassVar[str] = __version__
    EMAIL: ClassVar[str] = 'me2sy@outlook.com'
    GITHUB: ClassVar[str] = 'https://github.com/Me2sY/mysc'

    PATH_BASE: ClassVar[pathlib.Path] = project_path()

    PATH_LIBS: ClassVar[pathlib.Path] = PATH_BASE.joinpath('libs')
    PATH_LIBS.mkdir(parents=True, exist_ok=True)

    PATH_STATICS: ClassVar[pathlib.Path] = PATH_BASE.joinpath('statics')
    PATH_STATICS.mkdir(parents=True, exist_ok=True)

    PATH_LOCALES: ClassVar[pathlib.Path] = PATH_BASE.joinpath('locales')
    PATH_LOCALES.mkdir(parents=True, exist_ok=True)

    PATH_LOCAL: ClassVar[pathlib.Path] = pathlib.Path.home().joinpath(f".{PROJECT_NAME}")
    PATH_LOCAL.mkdir(parents=True, exist_ok=True)

    PATH_TEMP: ClassVar[pathlib.Path] = PATH_LOCAL.joinpath("temp")
    PATH_TEMP.mkdir(parents=True, exist_ok=True)

    PATH_CONFIG: ClassVar[pathlib.Path] = PATH_LOCAL.joinpath("config")
    PATH_CONFIG.mkdir(parents=True, exist_ok=True)