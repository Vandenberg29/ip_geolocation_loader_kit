# ip_geolocation_loader_kit

Load and index IP-to-country CSV data for fast range lookup using binary search on sorted start addresses.

## Usage

```python
from ip_geolocation_loader_kit import IpGeolocationLoader, GeolocationLookupError

loader = IpGeolocationLoader.from_csv_text("8.8.8.0,8.8.8.255,US\n")
country = loader.lookup("8.8.8.8")  # returns "US", or None if no range matches
```

For a file path, pass it to the constructor:

```python
loader = IpGeolocationLoader("ranges.csv")
```

`lookup` raises `GeolocationLookupError` if the input is not a valid IPv4 address, and returns `None` when no range contains the address.

## Why this exists

The problem is narrow: you have a CSV of `(start_ip, end_ip, country_code)` rows and you need to answer 'which country does this IPv4 address fall into?' for many addresses. A linear scan per query is too slow at scale; a full in-memory database is overkill. This library sorts the ranges once at load time and answers each query with a single `bisect` call — `O(log n)` per lookup, `O(n log n)` to build.

The trade-off: the index lives in process memory and is rebuilt by re-reading the file. There is no persistence layer, no incremental update, and no IPv6 support — the comparison path is plain 32-bit integers. If you need live updates or IPv6, this is not the right tool.

## Edge cases you will hit

- A lookup address that falls in a gap between two ranges returns `None`; gaps are real in most published geolocation tables and are not treated as errors.
- Rows whose `end_ip` is numerically less than `start_ip` raise `GeolocationParseError` at load time rather than producing a silently broken index.
- Country codes are uppercased and stripped; an empty code after stripping is a parse error.
- Only IPv4 is accepted. An IPv6 address passed to `lookup` raises `GeolocationLookupError`, and an IPv6 address in the CSV raises `GeolocationParseError`.

## Exported names

- `IpGeolocationLoader` — the loader class. Constructor takes a file path or a text stream; `from_csv_text(text)` builds from a string.
- `CountryLookup` — the index type, usable on its own with an iterable of `(start_int, end_int, country)` tuples.
- `GeolocationParseError` — raised during loading for malformed CSV rows.
- `GeolocationLookupError` — raised by `lookup` for addresses that are not valid IPv4.

## Performance

The window keeps a bounded buffer, so `push` is constant time and memory does not
grow with the length of the stream. `peak` and `trough` are linear in the window
size, which is the trade that keeps `push` cheap.

