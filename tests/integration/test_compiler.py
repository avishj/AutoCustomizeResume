"""Integration tests for the LaTeX compiler (real PDF I/O)."""

from __future__ import annotations

import pytest

from autocustomizeresume.compiler import (
    CompileError,
    get_page_count,
)


class TestGetPageCount:
    def test_invalid_file_raises(self, tmp_path):
        bad = tmp_path / "bad.pdf"
        bad.write_bytes(b"not a pdf")
        with pytest.raises(CompileError, match="Failed to read page count"):
            get_page_count(bad)

    def test_real_pdf(self, tmp_path):
        """Create minimal valid PDFs via pypdf and verify page count."""
        from pypdf import PdfWriter

        for n_pages in (1, 3):
            writer = PdfWriter()
            for _ in range(n_pages):
                writer.add_blank_page(width=612, height=792)
            pdf_path = tmp_path / f"test_{n_pages}.pdf"
            with open(pdf_path, "wb") as f:
                writer.write(f)
            assert get_page_count(pdf_path) == n_pages
