#!/usr/bin/env python
# coding: utf-8

# Standard Library
import abc
import copy
import functools
import importlib
import inspect
import re
import types
import typing
from typing import *

import IPython
import toolz.curried as toolz


def unwrap_partial(object):
    return getattr(object, "func", object)


@functools.partial(setattr, typing._Union, "__instancecheck__")
def __union_instancecheck__(self, object):
    for arg in self.__args__:
        if isinstance(object, arg):
            return True
    return False


__slots__ = (
    "__forward_arg__",
    "__forward_code__",
    "__forward_evaluated__",
    "__forward_value__",
)


def __init__(self, arg, _coerce=None, _observe=None, **kwargs):
    super(type(self), self).__init__(arg)
    if isinstance(arg, str):
        try:
            code = compile(arg, "<string>", "eval")
        except SyntaxError:
            raise SyntaxError(
                "Forward reference must be an expression -- got %r" % (arg,)
            )
    else:
        code = None

    self.__forward_arg__ = arg
    self.__forward_kwargs__ = kwargs
    self.__forward_code__ = code
    self.__forward_evaluated__ = False
    self.__forward_value__ = None
    self.__forward_coerce__ = _coerce
    self.__forward_observe__ = _observe
    self.__forward_display__ = None


def __eq__(self, other):
    if not isinstance(other, typing._ForwardRef):
        return NotImplemented
    return (
        self.__forward_arg__ == other.__forward_arg__
        and self.__forward_value__ == other.__forward_value__
    )


def __hash__(self):
    return hash((self.__forward_arg__, self.__forward_value__))


def __instancecheck__(self, object):
    self._eval_type(get_ipython().user_ns, get_ipython().user_ns)
    if not isinstance(self.__forward_value__, type):
        return False
    return isinstance(object, self.__forward_value__)


def __subclasscheck__(self, object):
    self._eval_type(get_ipython().user_ns, get_ipython().user_ns)
    return (
        isinstance(object, type)
        and isinstance(self.__forward_value__, type)
        and issubclass(object, self.__forward_value__)
    )


def __repr__(self):
    return type(self).__name__ + "(%r)" % (self.__forward_arg__,)


def overload_forward_reference(type):
    type.__init__ = __init__
    type.__slots__ = __slots__
    type.__eq__ = __eq__
    type.__hash__ = __hash__
    type.__instancecheck__ = __instancecheck__
    type.__subclasscheck__ = __subclasscheck__
    type.__repr__ = __repr__
    return type


@overload_forward_reference
class Literal(typing._TypingBase, _root=True):
    # custom init
    def _eval_type(self, globals, locals, **kwargs):
        return self.__forward_arg__


def _module_and_name(str):
    module, name = str.rpartition(".")[::2]
    return module or "__main__", name


@overload_forward_reference
class Forward(typing._TypingBase, _root=True):
    def _eval_type(self, globals, locals, **kwargs):
        eval = self.__forward_evaluated__
        kwargs.update(self.__forward_kwargs__)
        try:
            try:
                if not isinstance(self.__forward_arg__, str):
                    self.__forward_evaluated__ = True
                    self.__forward_value__ = self.__forward_arg__
                object = typing._ForwardRef._eval_type(self, globals, locals)
            except TypeError as Exception:
                module, name = _module_and_name(self.__forward_arg__)
                return getattr(importlib.import_module(module), name, Exception)
        except BaseException as Exception:
            return Exception
        if kwargs:
            for key, item in kwargs.items():
                if isinstance(item, str):
                    item = Forward(item)
                try:
                    kwargs[key] = typing._eval_type(item, globals, locals)
                except BaseException as Exception:
                    return Exception
            object = functools.partial(object, **kwargs)

        if self.__forward_observe__ and self.__forward_coerce__:
            if not eval and isinstance(self.__forward_coerce__, str):
                module, name = _module_and_name(self.__forward_coerce__)
                self.__forward_display__ = object(
                    **{
                        self.__forward_observe__: getattr(
                            importlib.import_module(module), name, None
                        )
                    }
                )

                def change(change):
                    nonlocal globals, locals, self
                    if not isinstance(change, dict):
                        change = dict(new=change)
                    setattr(importlib.import_module(module), name, change["new"])

                if hasattr(self.__forward_display__, "param"):
                    self.__forward_display__.param.watch(
                        change, self.__forward_observe__
                    )
                elif hasattr(self.__forward_display__, "observe"):
                    self.__forward_display__.observe(change, self.__forward_observe__)

                if hasattr(self.__forward_display__, "description"):
                    self.__forward_display__.description = self.__forward_coerce__

                change(getattr(self.__forward_display__, "value"))
                IPython.display.display(self.__forward_display__)

        elif self.__forward_coerce__ and self.__forward_coerce__ is not True:
            module, name = _module_and_name(self.__forward_coerce__)
            value = globals.get(self.__forward_coerce__, None)

            if (not isinstance(object, type)) or (not isinstance(value, object)):
                setattr(importlib.import_module(module), name, object(value))

        return object


@overload_forward_reference
class Priority(typing._TypingBase, _root=True):
    def _eval_type(self, globals, locals, **kwargs):
        for arg in (
            self.__forward_arg__
            if toolz.isiterable(self.__forward_arg__)
            else (self.__forward_arg__,)
        ):
            if isinstance(arg, str):
                arg = Forward(arg)

            if isinstance(arg, Forward):
                arg.__forward_coerce__ = (
                    arg.__forward_coerce__ or self.__forward_coerce__
                )

            object = typing._eval_type(arg, globals, locals)
            if (object is not None) and (not isinstance(object, BaseException)):
                return object


@functools.partial(setattr, Priority, "__instancecheck__")
def __priority_instancecheck__(self, object):
    for arg in (
        self.__forward_arg__
        if toolz.isiterable(self.__forward_arg__)
        else (self.__forward_arg__,)
    ):
        if isinstance(arg, str):
            arg = Forward(str)
        if isinstance(object, arg):
            return True
    return False


def annodize(name="__main__", annotations=None):
    globals, locals = map(vars, map(importlib.import_module, [name] * 2))
    __annotations__ = globals.get("__annotations__", {})
    annotations = toolz.keymap(Forward, (annotations or {}))
    annotations = toolz.keymap(
        lambda x: typing._eval_type(x, globals, locals), annotations
    )
    for key, value in __annotations__.items():
        if getattr(value, "__forward_coerce__", False) is True:
            value.__forward_coerce__ = key
        if value in annotations:
            new = copy.copy(annotations[value])

            if getattr(new, "__forward_coerce__", False) is True:
                new.__forward_coerce__ = key
            __annotations__[key] = typing.Union[value, new]

        typing._eval_type(__annotations__[key], globals, locals)


def load_ipython_extension(shell):
    global _extension
    _extension = functools.partial(annodize, "__main__")
    shell.events.register("post_execute", _extension)


def unload_ipython_extension(shell):
    global _extension
    shell.events.unregister("post_execute", _extension)


if __name__ == "__main__":
    get_ipython().system(
        "jupyter nbconvert --to python --TemplateExporter.exclude_input_prompt=True annodize.ipynb"
    )
    get_ipython().system("black annodize.py")
    get_ipython().system("isort annodize.py")
