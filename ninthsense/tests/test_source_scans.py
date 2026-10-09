import ast
import io
import pathlib
import re
import tokenize

from odoo.addons.base.tests.common import BaseCommon

PACKAGE_ROOT = pathlib.Path(__file__).resolve().parents[1]
SELF_PATH = pathlib.Path(__file__).resolve()
LOG_MODULE_PATH = PACKAGE_ROOT / "core" / "log.py"
LOG_TEST_PATH = PACKAGE_ROOT / "core" / "tests" / "test_log.py"
FIXTURES_PREFIX = str(pathlib.Path("core") / "tests" / "fixtures")

_LOGGING_MARKERS = (
    re.compile(r"\bimport logging\b"),
    re.compile(r"\bfrom logging\b"),
    re.compile(r"\blogging\.getLogger\b"),
    re.compile(r"\b_logger\b"),
    re.compile(r"\bprint\("),
)
_ID_PATTERN = re.compile(r"\b(FR|NFR|SC|R|H|Q|F|T|C|US)-?\d+\b")
_DOCUMENT_PATTERN = re.compile(r"\b(spec|plan\.md|tasks\.md|research\.md|quickstart)\b", re.I)
_XML_COMMENT = re.compile(r"<!--(.*?)-->", re.S)


def _files(suffix):
    for path in sorted(PACKAGE_ROOT.rglob(f"*{suffix}")):
        relative = str(path.relative_to(PACKAGE_ROOT))
        if relative.startswith(FIXTURES_PREFIX) or path == SELF_PATH:
            continue
        yield path


def _python_comments_and_docstrings(path):
    source = path.read_text(encoding="utf-8")
    texts = [
        token.string
        for token in tokenize.generate_tokens(io.StringIO(source).readline)
        if token.type == tokenize.COMMENT
    ]
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            docstring = ast.get_docstring(node, clean=False)
            if docstring:
                texts.append(docstring)
    return texts


def _xml_comments(path):
    return _XML_COMMENT.findall(path.read_text(encoding="utf-8"))


def _commentary():
    for path in _files(".py"):
        yield path, _python_comments_and_docstrings(path)
    for path in _files(".xml"):
        yield path, _xml_comments(path)


class TestSourceScans(BaseCommon):
    def _relative(self, path):
        return str(path.relative_to(PACKAGE_ROOT))

    def test_no_stray_logging_or_print_calls(self):
        offenders = []
        for path in [*_files(".py"), *_files(".xml")]:
            if path in (LOG_MODULE_PATH, LOG_TEST_PATH):
                continue
            source = path.read_text(encoding="utf-8")
            for marker in _LOGGING_MARKERS:
                if marker.search(source):
                    offenders.append(f"{self._relative(path)}: {marker.pattern!r}")
        self.assertEqual(offenders, [])

    def test_comments_and_docstrings_carry_no_task_or_spec_ids(self):
        offenders = []
        for path, texts in _commentary():
            for text in texts:
                match = _ID_PATTERN.search(text)
                if match:
                    offenders.append(f"{self._relative(path)}: {match.group(0)!r}")
        self.assertEqual(offenders, [])

    def test_comments_and_docstrings_do_not_name_the_planning_documents(self):
        offenders = []
        for path, texts in _commentary():
            for text in texts:
                match = _DOCUMENT_PATTERN.search(text)
                if match:
                    offenders.append(f"{self._relative(path)}: {match.group(0)!r}")
        self.assertEqual(offenders, [])
