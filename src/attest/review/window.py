"""`--since`: the slice of a ledger a weekly report is about (D-171).

`attest stats` reads a repository's whole ledger, which is the right default and
the wrong thing to put in front of someone on a Monday. A stable-period report
is *"what did this thing do last week"*, and that is a filter on one field.

Two spellings, because both are what people write:

* a **date** or timestamp -- `2026-09-01`, `2026-09-01T09:00:00+0800`;
* a **duration back from now** -- `7d`, `24h`, `90m`, `2w`.

Rows are kept when their `ts` is at or after the boundary. A row whose `ts`
cannot be read is **kept**, not dropped: this is a report, and the safe
direction for an unreadable timestamp in a report is to show it rather than to
quietly shrink the denominator. (`daily_spend` takes the opposite default for
the opposite reason -- there the unreadable row is *charged*, because that is
the safe direction for a spending cap.)

Pure: the boundary is a parameter, so a test can pin `now` and no assertion
depends on the day it runs.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

WINDOW_SCHEMA_VERSION = "attest.stats-window.v1"

_DURATION = re.compile(r"^(?P<value>\d+)(?P<unit>[mhdw])$")
_UNITS = {"m": "minutes", "h": "hours", "d": "days", "w": "weeks"}
_STAMPS = ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d")


def parse_since(spec: str, *, now: datetime | None = None) -> datetime:
    """The boundary ``spec`` names, as an aware datetime.

    Raises ValueError with the accepted spellings rather than guessing, because
    a report over the wrong window is worse than a report that did not run.
    """
    text = (spec or "").strip()
    moment = now or datetime.now(UTC)
    duration = _DURATION.match(text)
    if duration is not None:
        amount = int(duration.group("value"))
        return moment - timedelta(**{_UNITS[duration.group("unit")]: amount})
    for shape in _STAMPS:
        try:
            parsed = datetime.strptime(text, shape)
        except ValueError:
            continue
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=moment.tzinfo or UTC)
    raise ValueError(
        f"cannot read --since {spec!r}: use a date (2026-09-01), a timestamp "
        "(2026-09-01T09:00:00+0800), or a duration back from now (7d, 24h, 90m, 2w)"
    )


def row_time(value: object) -> datetime | None:
    if type(value) is not str or not value:
        return None
    for shape in _STAMPS:
        try:
            parsed = datetime.strptime(value, shape)
        except ValueError:
            continue
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    return None


def since(
    entries: Sequence[Mapping[str, Any]], boundary: datetime
) -> tuple[list[dict[str, Any]], int]:
    """(rows at or after ``boundary``, rows whose timestamp could not be read)."""
    kept: list[dict[str, Any]] = []
    unreadable = 0
    for row in entries:
        stamp = row_time(row.get("ts"))
        if stamp is None:
            unreadable += 1
            kept.append(dict(row))
            continue
        if stamp >= boundary:
            kept.append(dict(row))
    return kept, unreadable
