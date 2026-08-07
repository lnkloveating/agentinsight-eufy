import csv
import io
import json
from collections.abc import Sequence
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import NoReturn, Protocol

from pypdf import PdfReader

from app.schemas.source_processing import SourceLocator, SourceLocatorKind


class SourceParserError(Exception):
    def __init__(self, code: str, message: str, *, blocked: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.blocked = blocked


@dataclass(frozen=True)
class ParsedFragmentCandidate:
    locator: SourceLocator
    original_excerpt: str


@dataclass(frozen=True)
class DeterministicParseResult:
    parser_id: str
    parser_version: str
    fragments: tuple[ParsedFragmentCandidate, ...]


class DeterministicSourceParser(Protocol):
    @property
    def parser_id(self) -> str: ...

    @property
    def parser_version(self) -> str: ...

    @property
    def media_types(self) -> tuple[str, ...]: ...

    def parse(self, path: Path) -> DeterministicParseResult: ...

    def verify(self, path: Path, fragments: Sequence[ParsedFragmentCandidate]) -> None: ...


class SourceParserRegistry:
    def __init__(self, parsers: Sequence[DeterministicSourceParser]) -> None:
        by_media_type: dict[str, DeterministicSourceParser] = {}
        for parser in parsers:
            for media_type in parser.media_types:
                if media_type in by_media_type:
                    raise ValueError(f"duplicate source parser for {media_type}")
                by_media_type[media_type] = parser
        self._by_media_type = by_media_type

    def get(self, media_type: str) -> DeterministicSourceParser:
        parser = self._by_media_type.get(media_type)
        if parser is None:
            raise SourceParserError(
                "SOURCE_PARSER_NOT_CONFIGURED",
                f"No deterministic parser is registered for {media_type}.",
                blocked=True,
            )
        return parser


class TextSourceParser:
    parser_id = "deterministic-text"
    parser_version = "1.0"
    media_types = ("text/plain", "text/markdown")

    def __init__(self, max_excerpt_chars: int) -> None:
        self.max_excerpt_chars = max_excerpt_chars

    def parse(self, path: Path) -> DeterministicParseResult:
        text = _read_utf8(path)
        fragments = tuple(
            _chunk_text(text, SourceLocatorKind.TEXT, self.max_excerpt_chars)
        )
        return DeterministicParseResult(self.parser_id, self.parser_version, fragments)

    def verify(self, path: Path, fragments: Sequence[ParsedFragmentCandidate]) -> None:
        _verify_character_fragments(_read_utf8(path), fragments)


class CsvSourceParser:
    parser_id = "deterministic-csv"
    parser_version = "1.0"
    media_types = ("text/csv",)

    def parse(self, path: Path) -> DeterministicParseResult:
        text = _read_utf8(path)
        offsets = _line_offsets(text)
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        fragments: list[ParsedFragmentCandidate] = []
        previous_line = 0
        try:
            for row_number, _row in enumerate(reader, start=1):
                line_start = previous_line + 1
                line_end = reader.line_num
                start = offsets[previous_line]
                end = offsets[line_end]
                previous_line = line_end
                start, end = _trim_span(text, start, end)
                if start == end:
                    continue
                fragments.append(
                    ParsedFragmentCandidate(
                        locator=SourceLocator(
                            kind=SourceLocatorKind.ROW,
                            row_number=row_number,
                            line_start=line_start,
                            line_end=line_end,
                            char_start=start,
                            char_end=end,
                        ),
                        original_excerpt=text[start:end],
                    )
                )
        except csv.Error as exc:
            raise SourceParserError("SOURCE_CSV_INVALID", "CSV content is invalid.") from exc
        return DeterministicParseResult(
            self.parser_id, self.parser_version, tuple(fragments)
        )

    def verify(self, path: Path, fragments: Sequence[ParsedFragmentCandidate]) -> None:
        text = _read_utf8(path)
        # Re-parse to ensure malformed CSV cannot pass only by matching character offsets.
        try:
            tuple(csv.reader(io.StringIO(text, newline=""), strict=True))
        except csv.Error as exc:
            raise SourceParserError("SOURCE_CSV_INVALID", "CSV content is invalid.") from exc
        _verify_character_fragments(text, fragments)


class JsonSourceParser:
    parser_id = "deterministic-json"
    parser_version = "1.0"
    media_types = ("application/json",)

    def __init__(self, max_excerpt_chars: int) -> None:
        self.max_excerpt_chars = max_excerpt_chars

    def parse(self, path: Path) -> DeterministicParseResult:
        text = _read_utf8(path)
        _load_json(text)
        fragments = tuple(
            _chunk_text(
                text,
                SourceLocatorKind.JSON,
                self.max_excerpt_chars,
                json_pointer="/",
            )
        )
        return DeterministicParseResult(self.parser_id, self.parser_version, fragments)

    def verify(self, path: Path, fragments: Sequence[ParsedFragmentCandidate]) -> None:
        text = _read_utf8(path)
        _load_json(text)
        _verify_character_fragments(text, fragments)


class PdfSourceParser:
    parser_id = "pypdf-text"
    parser_version = "1.0"
    media_types = ("application/pdf",)

    def __init__(self, max_excerpt_chars: int) -> None:
        self.max_excerpt_chars = max_excerpt_chars

    def parse(self, path: Path) -> DeterministicParseResult:
        pages = _extract_pdf_pages(path)
        fragments: list[ParsedFragmentCandidate] = []
        for page_number, text in enumerate(pages, start=1):
            fragments.extend(
                _chunk_text(
                    text,
                    SourceLocatorKind.PAGE,
                    self.max_excerpt_chars,
                    page_number=page_number,
                )
            )
        return DeterministicParseResult(
            self.parser_id, self.parser_version, tuple(fragments)
        )

    def verify(self, path: Path, fragments: Sequence[ParsedFragmentCandidate]) -> None:
        pages = _extract_pdf_pages(path)
        for fragment in fragments:
            locator = fragment.locator
            if locator.kind is not SourceLocatorKind.PAGE or locator.page_number is None:
                _verification_failed()
            page_index = locator.page_number - 1
            if page_index < 0 or page_index >= len(pages):
                _verification_failed()
            _verify_character_fragment(pages[page_index], fragment)


class HtmlSourceParser:
    parser_id = "deterministic-html"
    parser_version = "1.0"
    media_types = ("text/html", "application/xhtml+xml")

    def __init__(self, max_excerpt_chars: int) -> None:
        self.max_excerpt_chars = max_excerpt_chars

    def parse(self, path: Path) -> DeterministicParseResult:
        html = _read_utf8(path)
        collector = _VisibleHtmlTextCollector(html, self.max_excerpt_chars)
        try:
            collector.feed(html)
            collector.close()
        except (AssertionError, ValueError) as exc:
            raise SourceParserError(
                "SOURCE_HTML_INVALID", "HTML content could not be parsed safely."
            ) from exc
        return DeterministicParseResult(
            self.parser_id, self.parser_version, tuple(collector.fragments)
        )

    def verify(self, path: Path, fragments: Sequence[ParsedFragmentCandidate]) -> None:
        html = _read_utf8(path)
        for fragment in fragments:
            if fragment.locator.kind is not SourceLocatorKind.WEB:
                _verification_failed()
            _verify_character_fragment(html, fragment)


def default_source_parser_registry(max_excerpt_chars: int) -> SourceParserRegistry:
    return SourceParserRegistry(
        (
            TextSourceParser(max_excerpt_chars),
            CsvSourceParser(),
            JsonSourceParser(max_excerpt_chars),
            PdfSourceParser(max_excerpt_chars),
            HtmlSourceParser(max_excerpt_chars),
        )
    )


class _VisibleHtmlTextCollector(HTMLParser):
    _hidden_tags = {"script", "style", "noscript", "svg", "template"}

    def __init__(self, html: str, max_excerpt_chars: int) -> None:
        super().__init__(convert_charrefs=False)
        self.html = html
        self.max_excerpt_chars = max_excerpt_chars
        self.line_offsets = _line_offsets(html)
        self.stack: list[str] = []
        self.fragments: list[ParsedFragmentCandidate] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        del attrs
        self.stack.append(tag.lower())

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        del tag, attrs

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index] == normalized:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        if not data.strip() or any(tag in self._hidden_tags for tag in self.stack):
            return
        line_number, column = self.getpos()
        if line_number < 1 or line_number > len(self.line_offsets):
            raise ValueError("HTML parser returned an invalid source position")
        raw_start = self.line_offsets[line_number - 1] + column
        if self.html[raw_start : raw_start + len(data)] != data:
            raise ValueError("HTML parser data did not match the source snapshot")
        cursor = 0
        while cursor < len(data):
            while cursor < len(data) and data[cursor].isspace():
                cursor += 1
            if cursor >= len(data):
                return
            end = min(cursor + self.max_excerpt_chars, len(data))
            if end < len(data):
                preferred = max(
                    data.rfind("\n", cursor + self.max_excerpt_chars // 2, end),
                    data.rfind(" ", cursor + self.max_excerpt_chars // 2, end),
                )
                if preferred > cursor:
                    end = preferred
            start, end = _trim_span(data, cursor, end)
            if start < end and len(data[start:end].strip()) >= 2:
                absolute_start = raw_start + start
                absolute_end = raw_start + end
                self.fragments.append(
                    ParsedFragmentCandidate(
                        locator=SourceLocator(
                            kind=SourceLocatorKind.WEB,
                            line_start=_line_number(self.html, absolute_start),
                            line_end=_line_number(self.html, absolute_end - 1),
                            char_start=absolute_start,
                            char_end=absolute_end,
                            web_path="/" + "/".join(self.stack),
                        ),
                        original_excerpt=self.html[absolute_start:absolute_end],
                    )
                )
            cursor = max(end, cursor + 1)


def _read_utf8(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise SourceParserError(
            "SOURCE_TEXT_ENCODING_UNSUPPORTED",
            "Text sources must use UTF-8 encoding.",
        ) from exc


def _load_json(text: str) -> object:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise SourceParserError("SOURCE_JSON_INVALID", "JSON content is invalid.") from exc


def _extract_pdf_pages(path: Path) -> tuple[str, ...]:
    try:
        reader = PdfReader(path)
        if reader.is_encrypted:
            raise SourceParserError(
                "SOURCE_PDF_ENCRYPTED",
                "Encrypted PDF files require an authorized decryption connector.",
                blocked=True,
            )
        return tuple((page.extract_text() or "") for page in reader.pages)
    except SourceParserError:
        raise
    except Exception as exc:
        raise SourceParserError("SOURCE_PDF_INVALID", "PDF content is invalid.") from exc


def _chunk_text(
    text: str,
    kind: SourceLocatorKind,
    max_chars: int,
    *,
    page_number: int | None = None,
    json_pointer: str | None = None,
) -> list[ParsedFragmentCandidate]:
    fragments: list[ParsedFragmentCandidate] = []
    cursor = 0
    while cursor < len(text):
        while cursor < len(text) and text[cursor].isspace():
            cursor += 1
        if cursor >= len(text):
            break
        end = min(cursor + max_chars, len(text))
        if end < len(text):
            preferred = max(
                text.rfind("\n", cursor + max_chars // 2, end),
                text.rfind(" ", cursor + max_chars // 2, end),
            )
            if preferred > cursor:
                end = preferred
        start, end = _trim_span(text, cursor, end)
        if start < end:
            fragments.append(
                ParsedFragmentCandidate(
                    locator=SourceLocator(
                        kind=kind,
                        page_number=page_number,
                        line_start=_line_number(text, start),
                        line_end=_line_number(text, end - 1),
                        char_start=start,
                        char_end=end,
                        json_pointer=json_pointer,
                    ),
                    original_excerpt=text[start:end],
                )
            )
        cursor = max(end, cursor + 1)
    return fragments


def _line_offsets(text: str) -> list[int]:
    offsets = [0]
    for index, character in enumerate(text):
        if character == "\n":
            offsets.append(index + 1)
    if offsets[-1] != len(text):
        offsets.append(len(text))
    return offsets


def _line_number(text: str, char_index: int) -> int:
    return text.count("\n", 0, char_index) + 1


def _trim_span(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def _verify_character_fragments(
    text: str, fragments: Sequence[ParsedFragmentCandidate]
) -> None:
    for fragment in fragments:
        _verify_character_fragment(text, fragment)


def _verify_character_fragment(text: str, fragment: ParsedFragmentCandidate) -> None:
    start = fragment.locator.char_start
    end = fragment.locator.char_end
    if start is None or end is None or text[start:end] != fragment.original_excerpt:
        _verification_failed()


def _verification_failed() -> NoReturn:
    raise SourceParserError(
        "SOURCE_FRAGMENT_VERIFICATION_FAILED",
        "A parsed excerpt could not be verified against the original source.",
    )
