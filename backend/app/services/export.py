"""
Export service — generates MusicXML and PDF from music21 streams.

PDF export supports two backends (configured via PDF_BACKEND env var):
  - "lilypond"  — headless, no X11 needed, recommended for containers
  - "musescore" — requires xvfb for headless operation
  - "none"      — skip PDF generation entirely
"""

import subprocess
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


def export_musicxml(music21_stream: Any, output_path: str) -> str:
    """Export a music21 Stream to MusicXML format."""
    logger.info("export_musicxml_start", output=output_path)
    music21_stream.write("musicxml", fp=output_path)
    logger.info("export_musicxml_complete", output=output_path, size=Path(output_path).stat().st_size)
    return output_path


def export_pdf(musicxml_path: str, output_path: str) -> bool:
    """
    Export MusicXML to PDF using the configured backend.

    Returns True on success, False on failure (graceful degradation).
    """
    backend = settings.PDF_BACKEND.lower()

    if backend == "none":
        logger.info("export_pdf_disabled", reason="PDF_BACKEND=none")
        return False
    elif backend == "lilypond":
        return _export_pdf_lilypond(musicxml_path, output_path)
    elif backend == "musescore":
        return _export_pdf_musescore(musicxml_path, output_path)
    else:
        logger.warning("export_pdf_unknown_backend", backend=backend)
        return False


def _export_pdf_lilypond(musicxml_path: str, output_path: str) -> bool:
    """
    Export MusicXML to PDF via music21's LilyPond backend.

    music21 converts MusicXML → LilyPond format internally, then
    LilyPond CLI renders the .ly file to PDF. Fully headless.
    """
    logger.info("export_pdf_lilypond_start", input=musicxml_path, output=output_path)

    try:
        from music21 import converter, environment

        # Configure music21 to use the LilyPond binary
        env = environment.Environment()
        env["lilypondPath"] = settings.LILYPOND_BIN

        # Load the MusicXML and export via LilyPond
        score = converter.parse(musicxml_path)

        # music21's LilyPond export writes to a temp file; we need to
        # use the lily module directly for control over output path
        ly_path = Path(output_path).with_suffix(".ly")
        lpc = score.write("lilypond", fp=str(ly_path))

        # Run LilyPond CLI to produce PDF
        cmd = [
            settings.LILYPOND_BIN,
            "--pdf",
            "-o", str(Path(output_path).with_suffix("")),  # LilyPond appends .pdf
            str(ly_path),
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=settings.LILYPOND_TIMEOUT_SECONDS,
        )

        # Clean up intermediate .ly file
        ly_path.unlink(missing_ok=True)

        if result.returncode != 0:
            logger.warning(
                "export_pdf_lilypond_error",
                returncode=result.returncode,
                stderr=result.stderr[:500] if result.stderr else "",
            )
            return False

        if not Path(output_path).exists():
            logger.warning("export_pdf_lilypond_file_not_created", output=output_path)
            return False

        logger.info(
            "export_pdf_lilypond_complete",
            output=output_path,
            size=Path(output_path).stat().st_size,
        )
        return True

    except FileNotFoundError:
        logger.warning(
            "export_pdf_lilypond_not_found",
            bin=settings.LILYPOND_BIN,
            message="LilyPond not installed — PDF export skipped",
        )
        return False

    except subprocess.TimeoutExpired:
        logger.error(
            "export_pdf_lilypond_timeout",
            timeout=settings.LILYPOND_TIMEOUT_SECONDS,
        )
        return False

    except Exception as e:
        logger.error("export_pdf_lilypond_error", error=str(e))
        return False


def _export_pdf_musescore(musicxml_path: str, output_path: str) -> bool:
    """
    Export MusicXML to PDF via MuseScore CLI (legacy backend).

    Requires MuseScore + xvfb for headless operation.
    """
    logger.info("export_pdf_musescore_start", input=musicxml_path, output=output_path)

    musescore_bin = settings.MUSESCORE_BIN
    timeout = settings.MUSESCORE_TIMEOUT_SECONDS

    cmd = [musescore_bin, musicxml_path, "-o", output_path]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if result.returncode != 0:
            logger.warning(
                "export_pdf_musescore_error",
                returncode=result.returncode,
                stderr=result.stderr[:500] if result.stderr else "",
            )
            return False

        if not Path(output_path).exists():
            logger.warning("export_pdf_file_not_created", output=output_path)
            return False

        logger.info(
            "export_pdf_musescore_complete",
            output=output_path,
            size=Path(output_path).stat().st_size,
        )
        return True

    except FileNotFoundError:
        logger.warning(
            "export_pdf_musescore_not_found",
            bin=musescore_bin,
            message="MuseScore not installed — PDF export skipped",
        )
        return False

    except subprocess.TimeoutExpired:
        logger.error(
            "export_pdf_musescore_timeout",
            timeout=timeout,
            bin=musescore_bin,
        )
        return False

    except Exception as e:
        logger.error("export_pdf_musescore_unexpected_error", error=str(e))
        return False
