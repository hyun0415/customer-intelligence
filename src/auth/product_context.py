from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True)
class ProductContext:
    parent_asin: str
    title: str


_product_context: ContextVar[ProductContext | None] = ContextVar(
    "product_context",
    default=None,
)


def get_product_context() -> ProductContext | None:
    return _product_context.get()


@contextmanager
def product_context(value: ProductContext | None) -> Iterator[None]:
    token = _product_context.set(value)
    try:
        yield
    finally:
        _product_context.reset(token)
