import html.parser
import logging
import os
import posixpath
import re
import shutil
import tempfile
import zipfile
import zlib
from typing import NamedTuple
from urllib.parse import unquote
from xml.etree import ElementTree

log = logging.getLogger(__name__)

UNITS_PER_CHARACTER = 4

CONTAINER = "META-INF/container.xml"
ENCRYPTION = "META-INF/encryption.xml"
READABLE = {"application/xhtml+xml", "text/html", "image/svg+xml"}
DOCUMENTS = (".xhtml", ".html", ".htm")
REWRITTEN = (".css",) + DOCUMENTS
UNCOUNTED = {"rt", "rp", "rtc", "script", "style", "noscript", "template"}

FIXED_LAYOUT = "pre-paginated"

EPUB_PREFIX = re.compile(
    rb"-epub-(?=writing-mode|text-orientation|text-emphasis|word-break|line-break"
    rb"|hyphens|text-align-last|ruby-position|text-underline-position)")
TEXT_COMBINE = re.compile(
    rb"(?<![\w-])(?:-epub-|-webkit-)?text-combine(?:-horizontal)?\s*:\s*(?:horizontal|all)")


class BadBook(ValueError):
    """An EPUB that cannot be read, carrying the reason as the wall states it."""


class Chapter(NamedTuple):
    """One document of the reading order, and how much of the book it holds."""

    path: str
    weight: int
    fixed: bool = False


class Book(NamedTuple):
    """An unpacked EPUB: where it lies, its reading order and what it says of itself."""

    folder: str
    chapters: tuple
    title: str = ""
    language: str = ""
    rtl: bool | None = None


def unpack(path) -> Book:
    """Unpack the EPUB at path into a new temporary folder and read its reading order."""
    folder = tempfile.mkdtemp(prefix="traker-book-")
    try:
        with zipfile.ZipFile(path) as archive:
            names = _extract(archive, folder)
        return _read(folder, _package_path(folder, names))
    except BadBook:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    except FileNotFoundError as error:
        shutil.rmtree(folder, ignore_errors=True)
        raise BadBook(f"there is no file at {path}") from error
    except (OSError, zipfile.BadZipFile, zlib.error, EOFError, NotImplementedError,
            RuntimeError, ElementTree.ParseError) as error:
        shutil.rmtree(folder, ignore_errors=True)
        raise BadBook(f"it is not an EPUB that can be opened: {error}") from error


def length(book) -> int:
    return sum(chapter.weight for chapter in book.chapters)


def locate(book, at) -> tuple:
    """Return (chapter index, units into that chapter) for a position in the whole book."""
    left = max(0, int(at or 0))
    for index, chapter in enumerate(book.chapters):
        if left < chapter.weight:
            return index, left
        left -= chapter.weight
    return len(book.chapters) - 1, book.chapters[-1].weight


def position(book, index, offset, total) -> int:
    """Return where offset of a chapter's total visible characters lies in the whole book."""
    start = sum(chapter.weight for chapter in book.chapters[:index])
    weight = book.chapters[index].weight
    return start + min(weight - 1, max(0, int(offset)) * weight // max(1, int(total)))


def _extract(archive, folder) -> set:
    """Write every member under folder, standard CSS in place of prefixed, and return the names."""
    root = os.path.realpath(folder)
    written = set()
    for member in archive.infolist():
        name = member.filename.replace("\\", "/")
        target = os.path.realpath(os.path.join(root, name))
        if member.is_dir() or not target.startswith(root + os.sep):
            continue
        data = archive.read(member)
        if name.lower().endswith(REWRITTEN):
            data = standard_css(data)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as f:
            f.write(data)
        written.add(name)
    return written


def standard_css(data) -> bytes:
    """Rewrite the -epub- properties a browser drops into their standard names."""
    return EPUB_PREFIX.sub(b"", TEXT_COMBINE.sub(b"text-combine-upright: all", data))


def _local(tag) -> str:
    return str(tag).rpartition("}")[2].rpartition(":")[2].lower()


def _package_path(folder, names) -> str:
    """Return the package document container.xml names, or the first there is."""
    try:
        for element in ElementTree.parse(os.path.join(folder, CONTAINER)).iter():
            if _local(element.tag) == "rootfile" and element.get("full-path"):
                return element.get("full-path")
    except (OSError, ElementTree.ParseError) as error:
        log.debug("No usable %s: %s", CONTAINER, error)
    packages = sorted(name for name in names if name.lower().endswith(".opf"))
    if not packages:
        raise BadBook("it has no package document")
    return packages[0]


def _read(folder, package) -> Book:
    """Read the reading order, the title and the language out of the package document."""
    root = ElementTree.parse(os.path.join(folder, package)).getroot()
    base = posixpath.dirname(package)
    manifest, spine, title, language, fixed_book = {}, None, "", "", False
    for element in root.iter():
        tag = _local(element.tag)
        if tag == "item" and element.get("id") and element.get("href"):
            manifest[element.get("id")] = element
        elif tag == "spine" and spine is None:
            spine = element
        elif tag == "title" and not title:
            title = (element.text or "").strip()
        elif tag == "language" and not language:
            language = (element.text or "").strip()
        elif tag == "meta" and element.get("property") == "rendition:layout":
            fixed_book = (element.text or "").strip() == FIXED_LAYOUT
    if spine is None:
        raise BadBook("its package document has no reading order")

    locked = _encrypted(folder)
    linear, extra = [], []
    for itemref in spine:
        item = manifest.get(itemref.get("idref"))
        if _local(itemref.tag) != "itemref" or item is None:
            continue
        name = posixpath.normpath(posixpath.join(base, unquote(item.get("href"))))
        if item.get("media-type") not in READABLE and not name.lower().endswith(DOCUMENTS):
            continue
        if name in locked:
            raise BadBook("it is locked by DRM")
        properties = str(itemref.get("properties") or "").split()
        fixed = item.get("media-type") == "image/svg+xml" \
            or "rendition:layout-pre-paginated" in properties \
            or (fixed_book and "rendition:layout-reflowable" not in properties)
        path = os.path.join(folder, *name.split("/"))
        if not os.path.isfile(path):
            continue
        chapter = Chapter(path, max(1, _visible_characters(path)) * UNITS_PER_CHARACTER, fixed)
        (extra if itemref.get("linear") == "no" else linear).append(chapter)
    chapters = tuple(linear or extra)
    if not chapters:
        raise BadBook("its reading order names nothing that can be read")
    direction = str(spine.get("page-progression-direction") or "").lower()
    rtl = True if direction == "rtl" else False if direction == "ltr" else None
    return Book(folder, chapters, title, language, rtl)


def _encrypted(folder) -> set:
    """Return every file encryption.xml names as enciphered."""
    try:
        tree = ElementTree.parse(os.path.join(folder, ENCRYPTION))
    except (OSError, ElementTree.ParseError):
        return set()
    return {posixpath.normpath(unquote(element.get("URI")))
            for element in tree.iter()
            if _local(element.tag) == "cipherreference" and element.get("URI")}


class _Counter(html.parser.HTMLParser):
    """A count of the characters a reader sees in a body, without furigana or scripts."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_body = False
        self.skipping = 0
        self.count = 0

    def handle_starttag(self, tag, attrs):
        if tag == "body":
            self.in_body = True
        elif _local(tag) in UNCOUNTED:
            self.skipping += 1

    def handle_endtag(self, tag):
        if _local(tag) in UNCOUNTED:
            self.skipping = max(0, self.skipping - 1)

    def handle_data(self, data):
        if self.in_body and not self.skipping:
            self.count += sum(1 for character in data if not character.isspace())


def _visible_characters(path) -> int:
    with open(path, "rb") as f:
        raw = f.read()
    encoding = "utf-16" if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else "utf-8"
    counter = _Counter()
    counter.feed(raw.decode(encoding, errors="replace"))
    counter.close()
    return counter.count
