'''Decorators for modifying other decorators'''

from typing import Concatenate, Callable, ParamSpec, TypeAlias, TypeVar
from functools import partial

from ..typetools import C, O, P, R, Args, KWArgs
Decorator : TypeAlias = Callable[[Callable[P, R]], Callable[P, R]]


# META DECORATORS
def extend_to_methods(dec : Decorator) -> Decorator:
    '''Meta-decorator; modifies an existing decorator definition to be transferrable to methods with no additional code
    The modified decorator can be used interchangably to decorate both ordinary functions AND methods of classes'''
    class AdaptedDecorator:
        __doc__ = dec.__doc__ # copy docstring for annotation

        def __init__(self, funct : Callable[P, R]) -> None:
            '''Record function'''
            self.funct = funct

        def __call__(self, *args : Args, **kwargs : KWArgs) -> dec.__annotations__.get('return'): # TODO : fix this to reflect the decorator's return signature
            '''Apply decorator to function, then call decorated function'''
            return dec(self.funct)(*args, **kwargs)

        def __get__(self, instance : O, owner : C) -> Callable[[Concatenate[O, P]], R]:
            '''Generate partial application with calling instance as first argument (fills in for "self")'''
            method = self.funct.__get__(instance, owner) # look up method belonging to owner class
            return dec(method) # return the decorated method

    return AdaptedDecorator