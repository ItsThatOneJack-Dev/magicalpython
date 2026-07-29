__magicalpython_internal__ = True # Hide from tracebacks.

import sys
from typing import Generic, TypeVar, Callable, Any, Union, Iterator, cast
from .error import Error

T = TypeVar("T")
E = TypeVar("E")
U = TypeVar("U")

class Ok(Generic[T]):
    def __init__(self, value: T) -> None:
        self.value = value

    def is_ok(self) -> bool:
        return True

    def is_err(self) -> bool:
        return False

    def unwrap(self) -> Any:
        val = cast(Any, self.value)
        hook = getattr(val, "__unwrap__", None)
        if callable(hook):
            return hook()
        return self.value

    def unwrap_or(self, default: Any) -> Any:
        return self.unwrap()

    def unwrap_or_else(self, op: Callable[[Any], Any]) -> Any:
        return self.unwrap()

    def unwrap_err(self) -> Any:
        raise ValueError(f"Called unwrap_err on an Ok value: {self.value}")

    def expect(self, msg: str) -> Any:
        return self.unwrap()

    def expect_err(self, msg: str) -> Any:
        raise ValueError(f"{msg}: {self.value}")

    def map(self, op: Callable[[T], U]) -> "Ok[U]":
        return Ok(op(self.value))

    def map_err(self, op: Callable[[Any], Any]) -> "Ok[T]":
        return self

    def and_then(self, op: Callable[[T], "Result"]) -> "Result":
        return op(self.value)

    def or_else(self, op: Callable[[Any], "Result"]) -> "Ok[T]":
        return self

    # C++-brained operator abuse below

    def __bool__(self) -> bool:
        return True

    def __iter__(self) -> Iterator[T]:
        # Rust IntoIterator energy: yields exactly once
        yield self.value

    def __rshift__(self, op: Callable[[T], "Result"]) -> "Result":
        # result >> f >> g  chaining, and_then but uglier
        return self.and_then(op)

    def __pos__(self) -> Any:
        # +result as a unary "deref" unwrap. deeply unnecessary.
        return self.unwrap()

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Ok) and self.value == other.value

    def __repr__(self) -> str:
        return f"Ok({repr(self.value)})"


class Err(Generic[E]):
    def __init__(self, value: E) -> None:
        self.value = value

    def is_ok(self) -> bool:
        return False

    def is_err(self) -> bool:
        return True

    def unwrap(self) -> Any:
        hook = getattr(self.value, "__unwrap__", None)
        if callable(hook):
            return hook()
        if isinstance(self.value, BaseException):
            raise self.value
        raise ValueError(f"Called unwrap on an Err value: {self.value}")

    def unwrap_or(self, default: U) -> U:
        return default

    def unwrap_or_else(self, op: Callable[[E], U]) -> U:
        return op(self.value)

    def unwrap_err(self) -> E:
        return self.value

    def expect(self, msg: str) -> Any:
        raise ValueError(f"{msg}: {self.value}")

    def expect_err(self, msg: str) -> E:
        return self.value

    def map(self, op: Callable[[Any], Any]) -> "Err[E]":
        return self

    def map_err(self, op: Callable[[E], U]) -> "Err[U]":
        return Err(op(self.value))

    def and_then(self, op: Callable[[Any], "Result"]) -> "Err[E]":
        return self

    def or_else(self, op: Callable[[E], "Result"]) -> "Result":
        return op(self.value)

    def __bool__(self) -> bool:
        return False

    def __iter__(self) -> Iterator[Any]:
        # yields zero times, so `for x in err_result:` just silently does nothing
        return
        yield

    def __rshift__(self, op: Callable[[Any], "Result"]) -> "Err[E]":
        return self

    def __pos__(self) -> Any:
        return self.unwrap()  # will raise, as intended

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Err) and self.value == other.value

    def __repr__(self) -> str:
        return f"Err({repr(self.value)})"

Result = Union[Ok[T], Err[E]]

_enhanced_type_cache = {}

def _get_enhanced_type(original_type):
    if original_type in _enhanced_type_cache:
        return _enhanced_type_cache[original_type]
    if issubclass(original_type, Error):
        _enhanced_type_cache[original_type] = original_type
        return original_type
    enhanced = type(original_type.__name__, (Error, original_type), {})
    _enhanced_type_cache[original_type] = enhanced
    return enhanced

def enhance_exception(exc: BaseException) -> BaseException:
    if isinstance(exc, Error):
        return exc
    enhanced_type = _get_enhanced_type(type(exc))
    new_exc = enhanced_type.__new__(enhanced_type)
    new_exc.args = exc.args
    new_exc.__dict__.update(exc.__dict__)
    new_exc.message = str(exc)
    new_exc.errortype = type(exc).__name__
    new_exc.__cause__ = exc.__cause__
    new_exc.__context__ = exc.__context__
    new_exc.__traceback__ = exc.__traceback__
    return new_exc

_NEVER_CATCH = (SystemExit, KeyboardInterrupt, GeneratorExit)

class _Propagate(Exception):
    """Internal control-flow exception. If you catch this yourself, that's on you."""
    def __init__(self, err: "Err"):
        self.err = err

def q(result: "Result[T, E]") -> T:
    if isinstance(result, Ok):
        return result.unwrap()
    raise _Propagate(result)  # now narrowed to Err[E]

def try_block(fn: Callable[..., Any]) -> Callable[..., "Result"]:
    """
    Decorator that turns a function using q() into one that returns
    a Result instead of raising. This is, in effect, reimplementing
    Rust's function-level ? propagation using exceptions as goto.
    """
    def wrapper(*args, **kwargs) -> "Result":
        try:
            value = fn(*args, **kwargs)
            return value if isinstance(value, (Ok, Err)) else Ok(value)
        except _Propagate as p:
            return p.err
    return wrapper

def _auto_try(fn):
    def wrapper(*args, **kwargs):
        try:
            value = fn(*args, **kwargs)
            return value if isinstance(value, (Ok, Err)) else Ok(value)
        except _Propagate as p:
            return p.err
        except _NEVER_CATCH:
            raise
        except BaseException as e:
            return Err(enhance_exception(e))
    return wrapper