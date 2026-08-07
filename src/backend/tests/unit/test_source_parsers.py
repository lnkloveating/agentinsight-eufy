from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.schemas.source_processing import SourceLocatorKind
from app.sources.parsers import (
    CsvSourceParser,
    HtmlSourceParser,
    JsonSourceParser,
    PdfSourceParser,
    SourceParserError,
    TextSourceParser,
)


def _pdf_with_text(text: str) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_reference = writer._add_object(font)
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {NameObject("/F1"): font_reference}
            )
        }
    )
    content = DecodedStreamObject()
    content.set_data(f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(content)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_text_parser_preserves_exact_excerpt_and_rejects_tampering(
    tmp_path: Path,
) -> None:
    path = tmp_path / "research.md"
    path.write_text("Package arrived.\n\nRain is forecast.\n", encoding="utf-8")
    parser = TextSourceParser(max_excerpt_chars=200)

    result = parser.parse(path)

    assert result.parser_id == "deterministic-text"
    assert len(result.fragments) == 1
    fragment = result.fragments[0]
    assert fragment.original_excerpt == "Package arrived.\n\nRain is forecast."
    assert fragment.locator.kind is SourceLocatorKind.TEXT
    parser.verify(path, result.fragments)

    path.write_text("Package removed.\n\nRain is forecast.\n", encoding="utf-8")
    with pytest.raises(SourceParserError, match="could not be verified"):
        parser.verify(path, result.fragments)


def test_csv_parser_tracks_multiline_logical_rows(tmp_path: Path) -> None:
    path = tmp_path / "reviews.csv"
    path.write_text('id,review\n1,"left outside\nin rain"\n', encoding="utf-8")
    parser = CsvSourceParser()

    result = parser.parse(path)

    assert len(result.fragments) == 2
    assert result.fragments[1].locator.kind is SourceLocatorKind.ROW
    assert result.fragments[1].locator.row_number == 2
    assert result.fragments[1].locator.line_start == 2
    assert result.fragments[1].locator.line_end == 3
    assert result.fragments[1].original_excerpt == '1,"left outside\nin rain"'
    parser.verify(path, result.fragments)


def test_json_parser_requires_valid_json_and_keeps_character_locator(
    tmp_path: Path,
) -> None:
    path = tmp_path / "research.json"
    path.write_text('{"event": "package_delivered"}', encoding="utf-8")
    parser = JsonSourceParser(max_excerpt_chars=200)

    result = parser.parse(path)

    assert len(result.fragments) == 1
    assert result.fragments[0].locator.kind is SourceLocatorKind.JSON
    assert result.fragments[0].locator.json_pointer == "/"
    parser.verify(path, result.fragments)

    path.write_text('{"event":', encoding="utf-8")
    with pytest.raises(SourceParserError, match="JSON content is invalid"):
        parser.parse(path)


def test_pdf_parser_extracts_and_revalidates_page_text(tmp_path: Path) -> None:
    path = tmp_path / "research.pdf"
    path.write_bytes(_pdf_with_text("Package risk evidence"))
    parser = PdfSourceParser(max_excerpt_chars=200)

    result = parser.parse(path)

    assert len(result.fragments) == 1
    assert result.fragments[0].locator.kind is SourceLocatorKind.PAGE
    assert result.fragments[0].locator.page_number == 1
    assert "Package risk evidence" in result.fragments[0].original_excerpt
    parser.verify(path, result.fragments)


def test_html_parser_keeps_exact_visible_text_and_web_path(tmp_path: Path) -> None:
    path = tmp_path / "page.html"
    path.write_text(
        "<html><head><style>hidden</style></head><body>"
        "<main><h1>Package intelligence</h1>"
        "<script>also hidden</script><p>Rain risk is high.</p></main>"
        "</body></html>",
        encoding="utf-8",
    )
    parser = HtmlSourceParser(max_excerpt_chars=200)

    result = parser.parse(path)

    assert [item.original_excerpt for item in result.fragments] == [
        "Package intelligence",
        "Rain risk is high.",
    ]
    assert result.fragments[0].locator.kind is SourceLocatorKind.WEB
    assert result.fragments[0].locator.web_path == "/html/body/main/h1"
    parser.verify(path, result.fragments)

    path.write_text(path.read_text(encoding="utf-8").replace("high", "low"), encoding="utf-8")
    with pytest.raises(SourceParserError, match="could not be verified"):
        parser.verify(path, result.fragments)
