# -*- coding: utf-8 -*-
"""
    connect_args
    ~~~~~~~~~~~~~~~~~~
    
    Log:
        2026-01-17 0.1.0 Me2sY 创建
"""

__author__ = 'Me2sY'
__version__ = '0.1.0'

__all__ = [
    'ConnectKwargs',
    'Adapter',
]

import abc
from dataclasses import dataclass, asdict, fields
from typing import Optional, Type, Any, get_origin, Union, get_args, Self

from mysc.core.connection import Connection


@dataclass
class ConnectKwargs:

    def to_kwargs(self) -> dict:
        """
            生成 scrcpy 连接参数
        :return:
        """
        return {
            str(k).lower().replace('-', '_'): v
            for k, v in vars(self).items()
            if not k.startswith('_') and v is not None
        }

    @classmethod
    def load(cls, **kwargs) -> Self:
        """
            从字典中加载
        :param kwargs:
        :return:
        """
        _field_names = [f.name for f in fields(cls)]
        return cls(**{
            key: kwargs[key]
         for key in kwargs if key in _field_names })

    def dump(self) -> dict:
        """
            转储方法
        :return:
        """
        return asdict(self)

    def to_items(self) -> list[tuple[str, Type, Optional[Any]]]:
        """
            转换为 配置项
        """
        items = []
        for field in fields(self):
            _t = get_origin(field.type)
            if _t is None:
                items.append((field.name, field.type, getattr(self, field.name)))
            elif _t is Union:
                items.append((field.name, get_args(field.type)[0], getattr(self, field.name)))
            else:
                continue
        return items


class Adapter(metaclass=abc.ABCMeta):
    """
        连接适配器
    """

    def __init__(self, connect_kwargs):
        self.is_running: bool = False
        self.connection: Optional[Connection] = None
        self._kwargs = connect_kwargs
        self.connect_kwargs = self._kwargs.to_kwargs()

    @abc.abstractmethod
    def connect(self, *args, **kwargs):
        raise NotImplementedError()

    @abc.abstractmethod
    def disconnect(self):
        raise NotImplementedError()
