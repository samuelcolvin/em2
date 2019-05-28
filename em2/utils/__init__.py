from functools import wraps
from typing import Any, Callable, Generator, List, TypeVar

T = TypeVar('T')


def listify(gen: Callable[..., Generator[T, None, None]]) -> Callable[..., List[T]]:
    """
    decorator to coerce a generator to a list
    """

    @wraps(gen)
    def list_func(*args, **kwargs) -> List[Any]:
        return list(gen(*args, **kwargs))

    return list_func
