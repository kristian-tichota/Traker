import re

import pytest

from src.config import PALETTE, STYLESHEET
from src.gui.components.vim_table_view import VimTableView

pytestmark = pytest.mark.gui

BUILT_ON_DEMAND = {"QDialog"}


@pytest.fixture
def styled(qapp):
    previous = qapp.styleSheet()
    qapp.setStyleSheet(STYLESHEET)
    yield qapp
    qapp.setStyleSheet(previous)


def type_selectors(qss):
    qss = re.sub(r"/\*.*?\*/", "", qss, flags=re.S)
    found = set()
    for head in re.findall(r"([^{}]+)\{", qss):
        for part in head.split(","):
            for token in re.split(r"[ >]+", part.strip()):
                name = token.split("::")[0].split(":")[0]
                if re.fullmatch(r"Q[A-Za-z]+", name):
                    found.add(name)
    return found


class TestTheTablesAreStyled:
    def test_a_log_table_resolves_the_monospace_face(self, styled):
        table = VimTableView()
        table.show()
        styled.processEvents()

        assert table.font().family() == "Fira Code"
        assert table.font().pixelSize() == 12

        table.deleteLater()
        styled.processEvents()

    def test_the_selector_names_the_base_class_the_tables_derive_from(self):
        from PyQt6.QtWidgets import QTableView

        assert issubclass(VimTableView, QTableView)
        assert "QTableView" in type_selectors(STYLESHEET)

    def test_the_solarized_ground_reaches_the_table_too(self, styled):
        table = VimTableView()
        table.show()
        styled.processEvents()

        rule = re.search(r"QTableView \{([^}]*)\}", STYLESHEET, re.S).group(1)
        assert PALETTE["base3"] in rule
        assert PALETTE["base2"] in rule

        table.deleteLater()
        styled.processEvents()


class TestNoRuleIsDead:
    def test_every_selector_names_a_class_the_window_actually_builds(self, window, qapp):
        from PyQt6.QtWidgets import QWidget

        window.show()
        qapp.processEvents()

        built = {c.__name__ for c in type(window).__mro__}
        for child in window.findChildren(QWidget):
            built.update(c.__name__ for c in type(child).__mro__)

        dead = type_selectors(STYLESHEET) - built - BUILT_ON_DEMAND
        assert not dead, f"stylesheet rules that reach no widget: {sorted(dead)}"
