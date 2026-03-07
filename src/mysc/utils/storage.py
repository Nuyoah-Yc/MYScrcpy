# -*- coding: utf-8 -*-
"""
    storage
    ~~~~~~~~~~~~~~~~~~
    
    Log:
        2026-01-19 0.1.0 Me2sY 创建，用于持久化运行信息
"""

__author__ = 'Me2sY'
__version__ = '0.1.0'

__all__ = [
    'JSONStorage'
]

from dataclasses import dataclass, asdict, fields
import json
import pathlib
from typing import Self, Optional, ClassVar, Type

from mysc.utils.params import Param


@dataclass
class JSONStorage:

    ProjectPath: ClassVar[pathlib.Path] = Param.PATH_CONFIG
    StoragePath: ClassVar[Optional[pathlib.Path]] = pathlib.Path('.')

    Prefix: ClassVar[str] = ''

    save_key: str

    @property
    def file_name(self) -> str:
        """
            文件名
        :return:
        """
        return self.Prefix + self.save_key

    @classmethod
    def _file_base_path(cls) -> pathlib.Path:
        """
            文件路径
        :return:
        """
        _fp = cls.ProjectPath / cls.StoragePath
        _fp.mkdir(parents=True, exist_ok=True)
        return _fp

    @property
    def file_path(self) -> pathlib.Path:
        """
            存储路径
        :return:
        """
        return self._file_base_path().joinpath(f"{self.file_name}.json")

    def dump(self) -> Self:
        """
            保存
        :return:
        """
        json.dump(
            {k: v for k, v in asdict(self).items() if not k.startswith('_')},
            self.file_path.open('w'),
            indent=4
        )
        return self

    def delete(self) -> None:
        """
            删除配置文件
        :return:
        """
        self.file_path.unlink()

    def rename(self, new_name: str) -> Self:
        """
            重命名
        :param new_name:
        :return:
        """
        _file_path = self.file_path
        _file_path.rename(
            _file_path.parent / f"{self.Prefix}{new_name}.json"
        )
        self.save_key = new_name
        self.dump()
        return self

    @classmethod
    def path_glob(cls):
        """
            路径遍历
        :return:
        """
        return cls._file_base_path().glob(f"{cls.Prefix}*.json")

    @classmethod
    def load(cls, save_key: str) -> Optional[Self]:
        """
            加载
        :param save_key:
        :return:
        """
        _fp = cls._file_base_path().joinpath(f"{cls.Prefix}{save_key}.json")

        if not _fp.exists() or not _fp.is_file(): return None

        kwargs = json.load(_fp.open('r'))
        kwargs.setdefault('save_key', save_key)

        # 剔除无用字段
        _fields = set(f.name for f in fields(cls))
        return cls(**{k: v for k, v in kwargs.items() if k in _fields})

    def reload(self) -> Self:
        """
            重加载
        :return:
        """
        kwargs = json.load(self.file_path.open('r'))
        for k, v in kwargs.items():
            setattr(self, k, v)
        return self

    @classmethod
    def obj_glob(cls):
        """
            遍历对象
        :return:
        """
        for fp in cls.path_glob():
            try:
                yield cls(**json.load(fp.open('r')))
            except json.decoder.JSONDecodeError:
                continue

    @classmethod
    def get_cls(cls, **kwargs) -> Type[Self]:
        """
            获取类
        :param kwargs:
        :return:
        """
        class JS(cls): ...

        for key, value in kwargs.items():
            getattr(JS, key) and setattr(JS, key, value)
        return JS
