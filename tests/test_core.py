import io
import os
import tempfile
import unittest

from ip_geolocation_loader_kit import (
    IpGeolocationLoader,
    GeolocationLookupError,
    GeolocationParseError,
    CountryLookup,
)


class FromCsvTextTests(unittest.TestCase):
    def test_basic_lookup(self):
        loader = IpGeolocationLoader.from_csv_text(
            "8.8.8.0,8.8.8.255,US\n1.0.0.0,1.0.0.255,AU\n"
        )
        self.assertEqual(loader.lookup("8.8.8.8"), "US")
        self.assertEqual(loader.lookup("1.0.0.10"), "AU")

    def test_lookup_returns_none_outside_any_range(self):
        loader = IpGeolocationLoader.from_csv_text("8.8.8.0,8.8.8.255,US\n")
        self.assertIsNone(loader.lookup("9.9.9.9"))

    def test_lookup_in_gap_between_ranges(self):
        loader = IpGeolocationLoader.from_csv_text(
            "10.0.0.0,10.0.0.10,US\n10.0.0.20,10.0.0.30,GB\n"
        )
        self.assertIsNone(loader.lookup("10.0.0.15"))

    def test_lookup_at_range_boundaries(self):
        loader = IpGeolocationLoader.from_csv_text("192.0.2.0,192.0.2.255,DE\n")
        self.assertEqual(loader.lookup("192.0.2.0"), "DE")
        self.assertEqual(loader.lookup("192.0.2.255"), "DE")
        self.assertIsNone(loader.lookup("192.0.1.255"))
        self.assertIsNone(loader.lookup("192.0.3.0"))

    def test_country_code_uppercased(self):
        loader = IpGeolocationLoader.from_csv_text("203.0.113.1,203.0.113.2,fr\n")
        self.assertEqual(loader.lookup("203.0.113.1"), "FR")

    def test_invalid_lookup_address_raises(self):
        loader = IpGeolocationLoader.from_csv_text("8.8.8.0,8.8.8.255,US\n")
        with self.assertRaises(GeolocationLookupError):
            loader.lookup("not-an-ip")

    def test_ipv6_address_raises(self):
        loader = IpGeolocationLoader.from_csv_text("8.8.8.0,8.8.8.255,US\n")
        with self.assertRaises(GeolocationLookupError):
            loader.lookup("2001:db8::1")

    def test_parse_error_on_bad_ip(self):
        with self.assertRaises(GeolocationParseError):
            IpGeolocationLoader.from_csv_text("not-an-ip,8.8.8.255,US\n")

    def test_parse_error_on_too_few_columns(self):
        with self.assertRaises(GeolocationParseError):
            IpGeolocationLoader.from_csv_text("8.8.8.0,8.8.8.255\n")

    def test_parse_error_on_empty_country(self):
        with self.assertRaises(GeolocationParseError):
            IpGeolocationLoader.from_csv_text("8.8.8.0,8.8.8.255,  \n")

    def test_parse_error_on_end_before_start(self):
        with self.assertRaises(GeolocationParseError):
            IpGeolocationLoader.from_csv_text("8.8.8.10,8.8.8.0,US\n")

    def test_unsorted_input_still_lookups_correctly(self):
        loader = IpGeolocationLoader.from_csv_text(
            "50.0.0.0,50.0.0.10,ZA\n10.0.0.0,10.0.0.10,US\n30.0.0.0,30.0.0.10,JP\n"
        )
        self.assertEqual(loader.lookup("10.0.0.5"), "US")
        self.assertEqual(loader.lookup("30.0.0.5"), "JP")
        self.assertEqual(loader.lookup("50.0.0.5"), "ZA")

    def test_from_file_path(self):
        with tempfile.NamedTemporaryFile(
            "w", suffix=".csv", delete=False, newline="", encoding="utf-8"
        ) as fh:
            fh.write("172.16.0.0,172.16.0.255,US\n")
            path = fh.name
        try:
            loader = IpGeolocationLoader(path)
            self.assertEqual(loader.lookup("172.16.0.1"), "US")
        finally:
            os.unlink(path)

    def test_from_stream(self):
        stream = io.StringIO("100.64.0.0,100.64.0.10,RU\n")
        loader = IpGeolocationLoader(stream)
        self.assertEqual(loader.lookup("100.64.0.5"), "RU")


class CountryLookupDirectTests(unittest.TestCase):
    def test_lookup_in_empty_index_returns_none(self):
        index = CountryLookup([])
        self.assertIsNone(index.lookup("8.8.8.8"))

    def test_lookup_below_all_ranges_returns_none(self):
        index = CountryLookup([(1_000_000, 2_000_000, "US")])
        self.assertIsNone(index.lookup("0.0.0.1"))

    def test_first_range_is_hit(self):
        # A regression guard for bisect returning index 0.
        index = CountryLookup([(1, 10, "US"), (20, 30, "GB")])
        self.assertEqual(index.lookup("0.0.0.5"), "US")


if __name__ == "__main__":
    unittest.main()
