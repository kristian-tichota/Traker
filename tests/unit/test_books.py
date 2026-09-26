import os
import shutil
import tempfile

import pytest

from src.desktop import books
from src.desktop.books import Book, Chapter

pytestmark = pytest.mark.exact

LOCKED = ('<encryption xmlns="urn:oasis:names:tc:opendocument:xmlns:container" '
          'xmlns:enc="http://www.w3.org/2001/04/xmlenc#"><enc:EncryptedData><enc:CipherData>'
          '<enc:CipherReference URI="OEBPS/c0.xhtml"/></enc:CipherData></enc:EncryptedData>'
          '</encryption>')


@pytest.fixture
def unpacked():
    opened = []

    def _unpack(path):
        book = books.unpack(path)
        opened.append(book.folder)
        return book

    yield _unpack
    for folder in opened:
        shutil.rmtree(folder, ignore_errors=True)


@pytest.fixture
def scratch(tmp_path, monkeypatch):
    folder = tmp_path / "scratch"
    folder.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(folder))
    return folder


class TestUnpacking:
    def test_the_reading_order_is_the_spine(self, epub, unpacked):
        book = unpacked(epub("<p>一</p>", "<p>二</p>", title="吾輩は猫である",
                             language="ja", direction="rtl"))

        assert [os.path.basename(chapter.path) for chapter in book.chapters] == [
            "c0.xhtml", "c1.xhtml"]
        assert (book.title, book.language, book.rtl) == ("吾輩は猫である", "ja", True)

    def test_a_book_that_does_not_say_its_direction_leaves_it_to_the_text(self, epub,
                                                                           unpacked):
        assert unpacked(epub("<p>a</p>")).rtl is None

    def test_a_document_outside_the_linear_order_is_skipped(self, epub, unpacked):
        book = unpacked(epub("<p>a</p>", ("<p>notes</p>", 'linear="no"')))

        assert len(book.chapters) == 1

    def test_a_pre_paginated_page_is_marked_fixed(self, epub, unpacked):
        book = unpacked(epub("<p>a</p>", ("<p>b</p>", 'properties="rendition:layout-pre-paginated"')))

        assert [chapter.fixed for chapter in book.chapters] == [False, True]

    def test_furigana_and_spaces_are_not_counted_as_text(self, epub, unpacked):
        book = unpacked(epub("<p>吾輩は<ruby>猫<rt>ねこ</rt></ruby> です</p>"))

        assert book.chapters[0].weight == len("吾輩は猫です") * books.UNITS_PER_CHARACTER

    def test_prefixed_css_is_written_as_the_browser_reads_it(self, epub, unpacked):
        book = unpacked(epub("<p>a</p>", vertical=True))

        with open(os.path.join(book.folder, "OEBPS", "book.css"), encoding="utf-8") as f:
            assert f.read() == ".vrtl { writing-mode: vertical-rl; }"

    @pytest.mark.parametrize("written, read", [
        (b"-epub-text-combine: horizontal;", b"text-combine-upright: all;"),
        (b"-webkit-text-combine: horizontal;", b"text-combine-upright: all;"),
        (b"-epub-text-combine-horizontal: all;", b"text-combine-upright: all;"),
        (b"text-combine-upright: all;", b"text-combine-upright: all;"),
        (b"-epub-text-emphasis-style: sesame;", b"text-emphasis-style: sesame;"),
    ])
    def test_every_prefix_a_japanese_book_uses_is_rewritten(self, written, read):
        assert books.standard_css(written) == read

    def test_a_member_naming_a_path_outside_its_folder_is_not_written(self, epub, unpacked,
                                                                      scratch):
        unpacked(epub("<p>a</p>", files=[("../escaped.txt", "x")]))

        assert not (scratch / "escaped.txt").exists()

    def test_something_that_is_not_an_epub_says_so_and_leaves_nothing(self, tmp_path,
                                                                     scratch):
        written = tmp_path / "x.epub"
        written.write_bytes(b"not a zip")

        with pytest.raises(books.BadBook, match="not an EPUB"):
            books.unpack(str(written))
        assert list(scratch.iterdir()) == []

    def test_a_file_that_is_not_there_says_so(self, tmp_path):
        with pytest.raises(books.BadBook, match="no file"):
            books.unpack(str(tmp_path / "absent.epub"))

    def test_a_book_locked_by_drm_says_so(self, epub):
        with pytest.raises(books.BadBook, match="DRM"):
            books.unpack(epub("<p>a</p>", files=[("META-INF/encryption.xml", LOCKED)]))


class TestWhereInTheBook:
    BOOK = Book("/b", (Chapter("/b/0", 40), Chapter("/b/1", 400), Chapter("/b/2", 80)))

    def test_a_position_names_its_chapter_and_how_far_into_it(self):
        assert [books.locate(self.BOOK, at) for at in (0, 40, 139)] == [
            (0, 0), (1, 0), (1, 99)]

    def test_past_the_end_is_the_end_of_the_last_chapter(self):
        assert books.locate(self.BOOK, 10_000) == (2, 80)

    def test_the_characters_before_a_page_scale_to_its_chapter(self):
        assert books.position(self.BOOK, 1, 50, 100) == 40 + 200

    def test_the_last_character_of_a_chapter_stays_in_it(self):
        assert books.locate(self.BOOK, books.position(self.BOOK, 1, 99, 100))[0] == 1

    def test_the_length_is_every_chapter_together(self):
        assert books.length(self.BOOK) == 520
