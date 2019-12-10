import inspect
from functools import wraps
from typing import Any, AsyncGenerator, Callable, Generator, List, TypeVar, Union

T = TypeVar('T')


def listify(gen: Callable[..., Union[Generator[T, None, None], AsyncGenerator[T, None]]]) -> Callable[..., List[T]]:
    """
    decorator to coerce a generator to a list
    """
    if inspect.isasyncgenfunction(gen):

        @wraps(gen)
        async def list_func(*args, **kwargs) -> List[Any]:
            return [v async for v in gen(*args, **kwargs)]

    elif inspect.isgeneratorfunction(gen):

        @wraps(gen)
        def list_func(*args, **kwargs) -> List[Any]:
            return list(gen(*args, **kwargs))

    else:
        raise TypeError(f'{gen} is not a generator or async-generator')
    return list_func
