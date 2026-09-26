import json
import logging
import os
import shutil
from functools import partial

from PyQt6.QtCore import QThreadPool, QUrl, Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from src.config import PALETTE
from src.desktop import books
from src.gui.workers import run_in_background
from src.profile import UserProfile

log = logging.getLogger(__name__)

PAPER, INK = 'base3', 'base00'

FONT_PX = 28
WIDTH_EM, HEIGHT_EM = 32, 30
MOST_OF_THE_PANE = 0.9

PAGER = r"""
(() => {
  const SKIPPED = new Set(["rt", "rp", "rtc", "script", "style", "noscript", "template"]);
  const SPACE = /\s/;
  const XML = "http://www.w3.org/XML/1998/namespace";
  const range = document.createRange();
  let sheet = null, given = null, vertical = false, backwards = false, rtl = false;
  let pitch = 1, page = 0, anchor = 0, texts = [], total = 0;

  const scroller = () => document.scrollingElement || document.documentElement;
  const surrogate = code => (code & 0xFC00) === 0xDC00;

  function visible(data) {
    let count = 0;
    for (let i = 0; i < data.length; i++)
      if (!surrogate(data.charCodeAt(i)) && !SPACE.test(data[i])) count++;
    return count;
  }

  function index() {
    texts = [];
    total = 0;
    if (!document.body) return;
    const walker = document.createTreeWalker(document.body,
      NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, {
        acceptNode: node => node.nodeType === Node.ELEMENT_NODE && SKIPPED.has(node.localName)
          ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT,
      });
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      if (node.nodeType !== Node.TEXT_NODE) continue;
      const count = visible(node.data);
      range.selectNodeContents(node);
      if (count && range.getClientRects().length) {
        texts.push({node, start: total});
        total += count;
      }
    }
  }

  function where(k) {
    let low = 0, high = texts.length - 1;
    while (low < high) {
      const middle = (low + high + 1) >> 1;
      if (texts[middle].start <= k) low = middle; else high = middle - 1;
    }
    const {node, start} = texts[low];
    for (let i = 0, seen = start; i < node.data.length; i++) {
      const code = node.data.charCodeAt(i);
      if (surrogate(code) || SPACE.test(node.data[i])) continue;
      if (seen++ === k) return [node, i, i + ((code & 0xFC00) === 0xD800 ? 2 : 1)];
    }
    return [node, 0, node.data.length];
  }

  function pageOf(k) {
    if (!total) return 0;
    const [node, from, to] = where(Math.max(0, Math.min(total - 1, k)));
    range.setStart(node, from);
    range.setEnd(node, to);
    const rects = range.getClientRects();
    if (!rects.length) return -1;
    const r = rects[0], s = scroller();
    const x = r.left + r.width / 2 + s.scrollLeft;
    const along = vertical ? r.top + r.height / 2 + s.scrollTop : backwards ? pitch - x : x;
    return Math.floor(along / pitch);
  }

  function firstOn(p) {
    let low = 0, high = total;
    while (low < high) {
      const middle = (low + high) >> 1, on = pageOf(middle);
      if (on < 0 || on >= p) high = middle; else low = middle + 1;
    }
    return Math.min(low, Math.max(0, total - 1));
  }

  function count() {
    if (!given || given.fixed) return 1;
    const s = scroller();
    return Math.max(1, Math.round((vertical ? s.scrollHeight : s.scrollWidth) / pitch));
  }

  function show(p) {
    page = Math.max(0, Math.min(count() - 1, p));
    const along = page * pitch;
    if (vertical) window.scrollTo(0, along);
    else window.scrollTo(backwards ? -along : along, 0);
  }

  function frame() {
    const meta = document.querySelector('meta[name="viewport"]');
    const said = meta ? meta.getAttribute("content") || "" : "";
    const width = /width\s*=\s*([\d.]+)/.exec(said), height = /height\s*=\s*([\d.]+)/.exec(said);
    if (width && height) return [parseFloat(width[1]), parseFloat(height[1])];
    const root = document.documentElement, box = root.viewBox && root.viewBox.baseVal;
    if (box && box.width && box.height) return [box.width, box.height];
    const picture = document.querySelector("img, svg");
    if (picture && picture.localName === "img" && picture.naturalWidth)
      return [picture.naturalWidth, picture.naturalHeight];
    const drawn = picture && picture.viewBox && picture.viewBox.baseVal;
    if (drawn && drawn.width && drawn.height) return [drawn.width, drawn.height];
    return [window.innerWidth, window.innerHeight];
  }

  function lay() {
    const root = document.documentElement, body = document.body || root;
    const w = window.innerWidth, h = window.innerHeight, gap = given.gap;
    const mode = getComputedStyle(body).writingMode;
    vertical = mode.startsWith("vertical") || mode.startsWith("sideways");
    backwards = !vertical && getComputedStyle(body).direction === "rtl";
    rtl = vertical ? !mode.endsWith("lr") : backwards;
    pitch = vertical ? h : w;
    if (given.fixed) {
      const [fw, fh] = frame(), scale = Math.min(w / fw, h / fh);
      sheet.textContent = `
        html { writing-mode: horizontal-tb !important;
          width: ${fw}px !important; height: ${fh}px !important; margin: 0 !important;
          overflow: hidden !important; transform-origin: 0 0 !important;
          transform: translate(${(w - fw * scale) / 2}px, ${(h - fh * scale) / 2}px)
            scale(${scale}) !important; background: ${given.paper} !important; }
        body { margin: 0 !important; }`;
      return;
    }
    const column = pitch - 2 * gap;
    sheet.textContent = `
      html {
        writing-mode: ${mode} !important;
        box-sizing: border-box !important;
        ${vertical ? `width: ${w}px !important; height: auto !important;`
                   : `height: ${h}px !important; width: auto !important;`}
        max-width: none !important; max-height: none !important;
        min-width: 0 !important; min-height: 0 !important;
        margin: 0 !important;
        padding: ${vertical ? `${gap}px ${gap / 2}px` : `${gap / 2}px ${gap}px`} !important;
        columns: ${column}px auto !important;
        column-gap: ${2 * gap}px !important;
        column-fill: auto !important;
        overflow: hidden !important;
        background: ${given.paper} !important;
        color: ${given.ink} !important;
      }
      body {
        margin: 0 !important;
        ${vertical ? "width: auto !important;" : "height: auto !important;"}
        max-width: none !important; max-height: none !important;
        min-width: 0 !important; min-height: 0 !important;
        background: transparent !important;
      }
      body, body * { color: inherit !important; background-color: transparent !important; }
      img, svg, video, canvas, object, embed {
        max-width: ${vertical ? w - gap : column}px !important;
        max-height: ${vertical ? column : h - gap}px !important;
        object-fit: contain !important;
        break-inside: avoid !important;
      }`;
  }

  function state(moved) {
    return {moved, page, pages: count(), offset: anchor, total, rtl};
  }

  function relay() {
    if (!given) return;
    lay();
    show(given.fixed ? 0 : Math.max(0, pageOf(anchor)));
  }

  window.traker = {
    open(config) {
      given = config;
      const root = document.documentElement, body = document.body || root;
      const named = element => element.getAttribute("lang") || element.getAttributeNS(XML, "lang");
      if (config.lang && !named(root) && !named(body)) root.setAttribute("lang", config.lang);
      sheet = document.createElementNS(root.namespaceURI, "style");
      (document.head || root).appendChild(sheet);
      lay();
      index();
      if (!total && !given.fixed && document.querySelectorAll("img, svg").length === 1) {
        given.fixed = true;
        lay();
      }
      if (config.go.end) show(count() - 1);
      else show(Math.max(0, pageOf(Math.ceil(config.go.offset * total / Math.max(1, config.go.of)))));
      anchor = firstOn(page);
      return state(false);
    },
    turn(step) {
      const to = page + step;
      if (!given || to < 0 || to >= count()) return state(false);
      show(to);
      anchor = firstOn(page);
      return state(true);
    },
  };
  window.addEventListener("resize", relay);
  document.fonts.addEventListener("loadingdone", relay);
})();
"""


def _unpack(generation, path) -> tuple:
    """Unpack one book: (the opening that asked, the book, what went wrong)."""
    try:
        return generation, books.unpack(path), None
    except books.BadBook as error:
        return generation, None, error


class BookPane(QWidget):
    """One EPUB, a page at a time, set in the middle of the screen."""

    changed = pyqtSignal()

    def __init__(self, path=None, start_at=0, parent=None):
        super().__init__(parent)
        profile = UserProfile()
        self.font_px = int(profile.number("strict_break.book", "font_px", FONT_PX,
                                          low=8, high=96))
        self.page_em = (profile.number("strict_break.book", "width_em", WIDTH_EM, low=4),
                        profile.number("strict_break.book", "height_em", HEIGHT_EM, low=4))
        self.book = None
        self.chapter = 0
        self.laid_out = None
        self.busy = False
        self._resume_at = 0
        self._going = None
        self._generation = 0
        self._message = None
        self._world = None
        self.view = None

        self.setObjectName("bookPane")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setStyleSheet(f"#bookPane {{ background-color: {PALETTE[PAPER]}; }}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        try:
            from PyQt6.QtWebEngineCore import QWebEngineScript, QWebEngineSettings
            from PyQt6.QtWebEngineWidgets import QWebEngineView
        except ImportError as error:
            log.warning("No book in a break: %s", error)
            self._show_message(f"COULD NOT READ\n{error}")
            return

        self._world = QWebEngineScript.ScriptWorldId.ApplicationWorld
        self.view = QWebEngineView(self)
        self.view.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.view.setEnabled(False)
        page = self.view.page()
        page.setBackgroundColor(QColor(PALETTE[PAPER]))
        page.setAudioMuted(True)
        settings = page.settings()
        attribute = QWebEngineSettings.WebAttribute
        for name, on in ((attribute.JavascriptEnabled, False),
                         (attribute.ShowScrollBars, False),
                         (attribute.FocusOnNavigationEnabled, False),
                         (attribute.ErrorPageEnabled, False),
                         (attribute.PluginsEnabled, False),
                         (attribute.LocalContentCanAccessFileUrls, True)):
            settings.setAttribute(name, on)
        for size in (QWebEngineSettings.FontSize.DefaultFontSize,
                     QWebEngineSettings.FontSize.DefaultFixedFontSize):
            settings.setFontSize(size, self.font_px)
        pager = QWebEngineScript()
        pager.setName("traker-pager")
        pager.setSourceCode(PAGER)
        pager.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
        pager.setWorldId(self._world)
        pager.setRunsOnSubFrames(False)
        page.scripts().insert(pager)
        self.view.loadFinished.connect(self._chapter_loaded)
        layout.addWidget(self.view, alignment=Qt.AlignmentFlag.AlignCenter)
        self._size_the_page()

        if path:
            self.open(path, start_at)

    @property
    def rtl(self) -> bool:
        """Report whether the next page lies to the left."""
        if self.book is not None and self.book.rtl is not None:
            return self.book.rtl
        return bool(self.laid_out and self.laid_out.get("rtl"))

    def open(self, path, start_at=0):
        """Read path from the place it was left."""
        self._let_go()
        self._resume_at = max(0, int(start_at or 0))
        if self.view is None:
            return
        self._clear_message()
        self.busy = True
        run_in_background(QThreadPool.globalInstance(), _unpack, self._unpacked,
                          self._crashed, self._generation, os.path.abspath(path))

    def toggle(self):
        """Turn to the next page."""
        self.turn(1)

    def step(self, direction):
        """Turn the way the arrow points; the next page lies left in right-to-left books."""
        self.turn(-int(direction) if self.rtl else int(direction))

    def undo(self):
        """Turn back a page."""
        self.turn(-1)

    def turn(self, direction):
        """Turn a page forward or back in reading order, across a chapter's edge as well."""
        if self.busy or self.laid_out is None:
            return
        self.busy = True
        self.view.page().runJavaScript(
            f"traker.turn({1 if int(direction) > 0 else -1})", self._world,
            partial(self._turned, self._generation, int(direction)))

    def nudge(self, direction):
        """Up goes to this chapter's start, then the previous; down goes to the next."""
        if self.busy or self.laid_out is None:
            return
        if int(direction) > 0:
            to = self.chapter - 1 if self.laid_out["page"] == 0 else self.chapter
        else:
            to = self.chapter + 1
        if 0 <= to < len(self.book.chapters):
            self._load(to, {"offset": 0, "of": 1})

    def title(self) -> str:
        """Return the title the book gives itself, or nothing."""
        return self.book.title if self.book is not None else ""

    def position(self) -> int:
        """Return where the page begins in the book, or its length on the last page."""
        if self.book is None or self.laid_out is None:
            return self._resume_at
        shown = self.laid_out
        if self.chapter == len(self.book.chapters) - 1 \
                and shown["page"] >= shown["pages"] - 1:
            return books.length(self.book)
        return books.position(self.book, self.chapter, shown["offset"], shown["total"])

    def duration(self) -> int:
        """Return how long the book is, in the units a position counts."""
        return books.length(self.book) if self.book is not None else 0

    def stop(self):
        """Let go of the book and of the folder it was unpacked into."""
        self._let_go()
        if self.view is not None:
            self.view.setHtml("")

    def shutdown(self):
        self._let_go()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._size_the_page()

    def _size_the_page(self):
        """Give the page its size in type, within most of the pane."""
        if self.view is None:
            return
        width = min(self.page_em[0] * self.font_px, self.width() * MOST_OF_THE_PANE)
        height = min(self.page_em[1] * self.font_px, self.height() * MOST_OF_THE_PANE)
        self.view.setFixedSize(max(1, int(width)), max(1, int(height)))

    def _let_go(self):
        self._generation += 1
        self.busy, self.laid_out, self._going = False, None, None
        if self.book is not None:
            shutil.rmtree(self.book.folder, ignore_errors=True)
            self.book = None

    def _unpacked(self, outcome):
        generation, book, error = outcome
        if generation != self._generation:
            if book is not None:
                shutil.rmtree(book.folder, ignore_errors=True)
            return
        self.busy = False
        if error is not None:
            log.warning("Could not read a book: %s", error)
            self._show_message(f"COULD NOT READ\n{error}")
            return
        self.book = book
        index, into = books.locate(book, self._resume_at)
        self._load(index, {"offset": into, "of": book.chapters[index].weight})
        self.changed.emit()

    def _crashed(self, failure):
        """Show an unpacking that failed in a way nothing expected."""
        error, _formatted = failure
        self.busy = False
        self._show_message(f"COULD NOT READ\n{error}")

    def _load(self, index, going):
        """Open chapter index and go where going says once it is laid out."""
        if self.laid_out is not None:
            self._resume_at = self.position()
        self.chapter, self._going, self.laid_out, self.busy = index, going, None, True
        self.view.load(QUrl.fromLocalFile(self.book.chapters[index].path))

    def _chapter_loaded(self, ok):
        if not ok or self.book is None or self._going is None:
            return
        config = {"gap": max(4, self.font_px // 2), "paper": PALETTE[PAPER],
                  "ink": PALETTE[INK], "lang": self.book.language,
                  "fixed": self.book.chapters[self.chapter].fixed, "go": self._going}
        self._going = None
        self.view.page().runJavaScript(f"traker.open({json.dumps(config)})", self._world,
                                       partial(self._laid_out, self._generation))

    def _laid_out(self, generation, shown):
        if generation != self._generation:
            return
        self.busy = False
        was = self.rtl
        self.laid_out = shown if isinstance(shown, dict) else {
            "page": 0, "pages": 1, "offset": 0, "total": 0, "rtl": was}
        if not isinstance(shown, dict):
            log.warning("Chapter %d of a book could not be laid out.", self.chapter + 1)
        if self.rtl != was:
            self.changed.emit()

    def _turned(self, generation, direction, shown):
        if generation != self._generation:
            return
        self.busy = False
        if not isinstance(shown, dict):
            return
        self.laid_out = shown
        if shown.get("moved"):
            return
        to = self.chapter + (1 if direction > 0 else -1)
        if 0 <= to < len(self.book.chapters):
            self._load(to, {"offset": 0, "of": 1} if direction > 0 else {"end": True})

    def _show_message(self, text):
        self._clear_message()
        if self.view is not None:
            self.view.hide()
        self._message = QLabel(text, self)
        self._message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._message.setStyleSheet(f"color: {PALETTE['red']}; font-size: 16px; "
                                    f"font-family: 'Fira Code'; letter-spacing: 2px;")
        self.layout().addWidget(self._message)

    def _clear_message(self):
        if self._message is not None:
            self._message.deleteLater()
            self._message = None
        if self.view is not None:
            self.view.show()
