"""Tests for lok_sabha_dataset.loader."""

from lok_sabha_dataset.loader import convert_date, pdf_filename_from_url


class TestConvertDate:
    def test_standard(self):
        assert convert_date("04.02.2025") == "2025-02-04"

    def test_leading_zeros(self):
        assert convert_date("01.01.2020") == "2020-01-01"

    def test_passthrough(self):
        assert convert_date("2025-02-04") == "2025-02-04"

    def test_none(self):
        assert convert_date(None) is None

    def test_empty(self):
        assert convert_date("") is None

    def test_whitespace(self):
        assert convert_date("  04.02.2025  ") == "2025-02-04"


class TestPdfFilenameFromUrl:
    def test_standard_url(self):
        url = "https://sansad.in/getFile/loksabhaquestions/annex/187/AS280_6OmUWJ.pdf?source=pqals"
        assert pdf_filename_from_url(url) == "AS280_6OmUWJ.pdf"

    def test_no_query_string(self):
        url = "https://sansad.in/getFile/AS100.pdf"
        assert pdf_filename_from_url(url) == "AS100.pdf"

    def test_none(self):
        assert pdf_filename_from_url(None) is None

    def test_empty(self):
        assert pdf_filename_from_url("") is None
