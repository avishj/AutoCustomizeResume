"""End-to-end tests for the cover letter generator (requires tectonic)."""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from autocustomizeresume.config import (
    Config,
    CoverLetterConfig,
    LLMConfig,
    NamingConfig,
    PathsConfig,
    UserConfig,
    WatcherConfig,
)
from autocustomizeresume.cover_letter import (
    _plain_text_to_latex,
    compile_cover_letter,
    inject_template,
)

# Minimal valid 1x1 RGB PNG (avoids struct/zlib at runtime).
_MINIMAL_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00"
    b"\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8"
    b"\xff\xff?\x00\x05\xfe\x02\xfe\r\xefF\xb8\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _tectonic_available() -> bool:
    return shutil.which("tectonic") is not None


def _make_config(**overrides) -> Config:
    """Build a Config with sensible defaults for testing."""
    user_kw = overrides.pop("user", {})
    cl_kw = overrides.pop("cover_letter", {})

    user_defaults = {
        "first_name": "Jane",
        "last_name": "Doe",
        "phone": "555-123-4567",
        "email": "jane@example.com",
        "linkedin": "linkedin.com/in/janedoe",
        "website": "janedoe.dev",
        "degree": "MS Computer Science",
        "university": "MIT",
    }
    user_defaults.update(user_kw)

    cl_enabled: bool = cl_kw.get("enabled", True)
    cl_template: str = cl_kw.get("template", "templates/cover_letter_template.tex")
    cl_sig: str = cl_kw.get("signature_path", "")

    return Config(
        user=UserConfig(**user_defaults),
        naming=NamingConfig(
            output_resume="{company}_{role}_Resume.pdf",
            output_cover="{company}_{role}_CoverLetter.pdf",
            history_resume="{date}_{company}_{role}_Resume.pdf",
            history_cover="{date}_{company}_{role}_CoverLetter.pdf",
        ),
        llm=LLMConfig(
            base_url="https://api.example.com/v1",
            model="test-model",
            api_key_env="TEST_API_KEY",
        ),
        cover_letter=CoverLetterConfig(
            enabled=cl_enabled,
            template=cl_template,
            signature_path=cl_sig,
        ),
        paths=PathsConfig(
            master_resume="resume.tex",
            jd_file="jd.txt",
            output_dir="output",
            history_dir="history",
        ),
        watcher=WatcherConfig(debounce_seconds=5),
    )


@pytest.mark.skipif(
    not _tectonic_available(),
    reason="tectonic not installed",
)
class TestCoverLetterIntegration:
    """E2E compilation using the real template and tectonic."""

    def test_compile_cover_letter_produces_pdf(self, tmp_path):
        """Fill the real template and compile to a valid PDF."""
        template_path = Path("templates/cover_letter_template.tex")
        if not template_path.exists():
            pytest.skip("Template not available")

        cfg = _make_config(
            cover_letter={
                "enabled": True,
                "template": str(template_path),
                "signature_path": "",
            }
        )

        template_tex = template_path.read_text(encoding="utf-8")

        with patch("autocustomizeresume.cover_letter.date") as mock_date:
            mock_date.today.return_value = date(2026, 2, 28)
            mock_date.side_effect = date
            filled_tex = inject_template(
                template_tex,
                config=cfg,
                body_text="This is a test cover letter body paragraph.",
            )

        pdf_path = compile_cover_letter(filled_tex, config=cfg, keep_dir=tmp_path)

        assert pdf_path.exists()
        assert pdf_path.suffix == ".pdf"
        header = pdf_path.read_bytes()[:5]
        assert header == b"%PDF-"

    def test_compile_with_signature(self, tmp_path):
        """Compile with a signature image (fake PNG)."""
        template_path = Path("templates/cover_letter_template.tex")
        if not template_path.exists():
            pytest.skip("Template not available")

        sig_file = tmp_path / "signature.png"
        sig_file.write_bytes(_MINIMAL_PNG)

        cfg = _make_config(
            cover_letter={
                "enabled": True,
                "template": str(template_path),
                "signature_path": str(sig_file),
            }
        )

        template_tex = template_path.read_text(encoding="utf-8")

        with patch("autocustomizeresume.cover_letter.date") as mock_date:
            mock_date.today.return_value = date(2026, 2, 28)
            mock_date.side_effect = date
            filled_tex = inject_template(
                template_tex,
                config=cfg,
                body_text="Test body with signature.",
            )

        work = tmp_path / "build"
        pdf_path = compile_cover_letter(filled_tex, config=cfg, keep_dir=work)

        assert pdf_path.exists()
        assert pdf_path.suffix == ".pdf"
        assert (work / "signature.png").exists()

    def test_compile_with_special_chars_in_body(self, tmp_path):
        """Body with LaTeX special chars compiles cleanly after escaping."""
        template_path = Path("templates/cover_letter_template.tex")
        if not template_path.exists():
            pytest.skip("Template not available")

        cfg = _make_config(
            cover_letter={
                "enabled": True,
                "template": str(template_path),
                "signature_path": "",
            }
        )

        body_plain = (
            "I improved performance by 100% and saved $50k.\n\n"
            "Technologies: C++ & Python. Used the #1 framework."
        )
        body_latex = _plain_text_to_latex(body_plain)

        template_tex = template_path.read_text(encoding="utf-8")

        with patch("autocustomizeresume.cover_letter.date") as mock_date:
            mock_date.today.return_value = date(2026, 2, 28)
            mock_date.side_effect = date
            filled_tex = inject_template(template_tex, config=cfg, body_text=body_latex)

        pdf_path = compile_cover_letter(filled_tex, config=cfg, keep_dir=tmp_path)

        assert pdf_path.exists()
        assert pdf_path.suffix == ".pdf"
