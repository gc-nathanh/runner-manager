"""
This type stub file was generated by pyright.
"""

from typing import Any, Callable, Dict, Optional, Set, Tuple, Union

"""
This file adapted from FastAPI's encoders.

Licensed under the MIT License (MIT).

Copyright (c) 2018 Sebastián Ramírez

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""
SetIntStr = Set[Union[int, str]]
DictIntStrAny = Dict[Union[int, str], Any]
def generate_encoders_by_class_tuples(type_encoder_map: Dict[Any, Callable[[Any], Any]]) -> Dict[Callable[[Any], Any], Tuple[Any, ...]]:
    ...

encoders_by_class_tuples = ...
def jsonable_encoder(obj: Any, include: Optional[Union[SetIntStr, DictIntStrAny]] = ..., exclude: Optional[Union[SetIntStr, DictIntStrAny]] = ..., by_alias: bool = ..., exclude_unset: bool = ..., exclude_defaults: bool = ..., exclude_none: bool = ..., custom_encoder: Dict[Any, Callable[[Any], Any]] = ..., sqlalchemy_safe: bool = ...) -> Any:
    ...

