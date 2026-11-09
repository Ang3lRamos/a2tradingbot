from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import TypeVar

T = TypeVar("T")


def paginate(
    fetch_page: Callable[[int], list[T]],
    ts_of: Callable[[T], int],
    since_ms: int,
    until_ms: int,
    step_ms: int,
) -> Iterator[list[T]]:
    """Recorre un endpoint paginado por tiempo y entrega páginas con `since_ms <= ts < until_ms`.

    Cada página se puede guardar apenas llega: si el proceso se corta, la siguiente corrida
    retoma desde lo último guardado.
    """
    cursor = since_ms
    while cursor < until_ms:
        page = [item for item in fetch_page(cursor) if cursor <= ts_of(item) < until_ms]
        if not page:
            return
        yield page
        cursor = ts_of(page[-1]) + step_ms


def to_datetime(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=UTC)


def to_ms(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)
