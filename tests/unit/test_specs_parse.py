import glob
import os

import pytest
from gherkin.parser import Parser
from gherkin.token_scanner import TokenScanner

pytestmark = pytest.mark.exact

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "specs", "features")

FEATURES = sorted(glob.glob(os.path.join(ROOT, "*.feature")))


def test_there_are_features_to_check():
    assert len(FEATURES) > 10


@pytest.mark.parametrize("path", FEATURES, ids=lambda p: os.path.basename(p))
def test_it_parses(path):
    with open(path, encoding="utf-8") as f:
        Parser().parse(TokenScanner(f.read()))


@pytest.mark.parametrize("path", FEATURES, ids=lambda p: os.path.basename(p))
def test_the_index_names_it(path):
    with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as f:
        index = f.read()
    assert os.path.basename(path) in index
