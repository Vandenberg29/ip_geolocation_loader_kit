"""Load and index IP-to-country CSV data for fast range lookup.

The loader reads a CSV file of (start_ip, end_ip, country_code) rows and
builds a structure optimised for point-queries: 'which country does this IP
fall into?'. The query uses binary search over the sorted start addresses,
so a lookup is O(log n) after a one-time O(n log n) sort at load time.

Only IPv4 is supported. Supporting both families would mean either two
parallel indexes or a 128-bit comparison path; both add complexity for no
benefit when the source data we target is IPv4-only. If a row's addresses
cannot be parsed as IPv4 the loader raises GeolocationParseError rather
than silently dropping data — a dropped row changes lookup results and a
silent failure is worse than a loud one at load time.
"""

import csv
import ipaddress
import io
from bisect import bisect_right
from typing import IO, Iterable, List, Optional, Sequence, Tuple, Union


class GeolocationParseError(ValueError):
    """Raised when a CSV row cannot be parsed as a valid IPv4 range."""


class GeolocationLookupError(ValueError):
    """Raised when lookup input is not a valid IPv4 address."""


# A normalised entry: (start_int, end_int, country_code).
_Range = Tuple[int, int, str]


class CountryLookup:
    """Index of non-overlapping IPv4 ranges, built from parsed entries.

    Kept separate from the loader so the index can be constructed from any
    iterable of entries (e.g. for testing or for a different CSV dialect)
    without going through the file-reading path.
    """

    def __init__(self, ranges: Iterable[_Range]) -> None:
        materialised: List[_Range] = list(ranges)
        # Lexicographic sort on (start, end, country) gives us the order
        # binary search needs. Sorting by start alone is sufficient for
        # correctness; including end in the key keeps equal starts
        # deterministically ordered for reproducible behaviour.
        materialised.sort(key=lambda r: (r[0], r[1], r[2]))
        self._starts: List[int] = [r[0] for r in materialised]
        self._ends: List[int] = [r[1] for r in materialised]
        self._countries: List[str] = [r[2] for r in materialised]

    def lookup(self, ip: str) -> Optional[str]:
        """Return the country code for *ip*, or None if no range contains it.

        Raises GeolocationLookupError if *ip* is not a valid IPv4 address.
        """
        try:
            addr = ipaddress.IPv4Address(ip)
        except (ipaddress.AddressValueError, ValueError) as exc:
            raise GeolocationLookupError(f"not a valid IPv4 address: {ip!r}") from exc
        target = int(addr)
        # bisect_right finds the insertion point to the right of any equal
        # start, so index-1 is the last range whose start <= target. That
        # is the only candidate that can contain the address.
        idx = bisect_right(self._starts, target) - 1
        if idx < 0:
            return None
        if target <= self._ends[idx]:
            return self._countries[idx]
        return None


def _parse_ipv4(text: str, row_num: int, column: str) -> int:
    try:
        return int(ipaddress.IPv4Address(text))
    except (ipaddress.AddressValueError, ValueError) as exc:
        raise GeolocationParseError(
            f"row {row_num}: invalid IPv4 in column {column!r}: {text!r}"
        ) from exc


def _parse_row(row: Sequence[str], row_num: int) -> _Range:
    if len(row) < 3:
        raise GeolocationParseError(
            f"row {row_num}: expected 3 columns, got {len(row)}"
        )
    start = _parse_ipv4(row[0], row_num, "start_ip")
    end = _parse_ipv4(row[1], row_num, "end_ip")
    if end < start:
        raise GeolocationParseError(
            f"row {row_num}: end_ip {row[1]!r} is less than start_ip {row[0]!r}"
        )
    country = row[2].strip().upper()
    if not country:
        raise GeolocationParseError(f"row {row_num}: empty country code")
    return (start, end, country)


class IpGeolocationLoader:
    """Load an IP-to-country CSV file and answer point-queries.

    The CSV is expected to have at least three columns per row: start_ip,
    end_ip, country_code. A header row is fine but is not assumed — if the
    first row cannot be parsed as addresses the loader raises rather than
    guessing whether a header is present.
    """

    def __init__(self, source: Union[str, IO[str]]) -> None:
        """Build the index from *source*.

        *source* may be a filesystem path or an already-open text stream.
        Accepting a stream lets callers read from bundled resources, in-memory
        data, or any non-file object without a temporary file.
        """
        self._index: CountryLookup = self._build_index(source)

    def _build_index(self, source: Union[str, IO[str]]) -> CountryLookup:
        if isinstance(source, str):
            # newline='' is the csv module's documented requirement when
            # reading, so embedded newlines in quoted fields are handled
            # correctly.
            with open(source, "r", newline="", encoding="utf-8") as handle:
                return self._build_index(handle)

        reader = csv.reader(source)
        ranges: List[_Range] = []
        for row_num, row in enumerate(reader, start=1):
            if not row:
                continue
            ranges.append(_parse_row(row, row_num))
        return CountryLookup(ranges)

    @classmethod
    def from_csv_text(cls, text: str) -> "IpGeolocationLoader":
        """Build a loader from an in-memory CSV string.

        Convenient for tests and for data bundled inside the package.
        """
        return cls(io.StringIO(text))

    def lookup(self, ip: str) -> Optional[str]:
        """Return the country code for *ip*, or None if no range contains it."""
        return self._index.lookup(ip)
