"""End-to-end tests for the LaTeX compiler (requires tectonic)."""

from __future__ import annotations

import shutil

import pytest

from autocustomizeresume.compiler import (
    CompileError,
    compile_tex,
    get_page_count,
)

pytestmark = pytest.mark.e2e


def _tectonic_available() -> bool:
    """Check if tectonic is available on PATH."""
    return shutil.which("tectonic") is not None


@pytest.mark.skipif(
    not _tectonic_available(),
    reason="tectonic not installed",
)
class TestTectonicIntegration:
    """E2E tests that invoke tectonic. Skipped if not installed."""

    def test_compile_minimal(self, tmp_path):
        tex = (
            r"\documentclass{article}"
            "\n"
            r"\begin{document}"
            "\n"
            r"Hello, world!"
            "\n"
            r"\end{document}"
        )
        pdf_path = compile_tex(tex, keep_dir=tmp_path)
        assert pdf_path.exists()
        assert pdf_path.suffix == ".pdf"
        assert get_page_count(pdf_path) == 1

    def test_compile_error_bad_latex(self, tmp_path):
        tex = r"\documentclass{article}\begin{document}\badcommand\end{document}"
        with pytest.raises(CompileError):
            compile_tex(tex, keep_dir=tmp_path)
