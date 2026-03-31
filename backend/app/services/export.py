"""
Export service — generates MusicXML and PDF from symusic scores.

PDF export supports two backends (configured via PDF_BACKEND env var):
  - "lilypond"  — headless, no X11 needed, recommended for containers
  - "musescore" — requires xvfb for headless operation
  - "none"      — skip PDF generation entirely
"""

import subprocess
from pathlib import Path
from typing import Any, Union

from app.core.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


def export_musicxml(score: Any, output_path: str) -> str:
    """
    Export a symusic Score to MusicXML format.
    
    symusic natively supports MusicXML export via dump_musicxml() method.
    Falls back to MIDI export if MusicXML is not supported.
    """
    logger.info("export_musicxml_start", output=output_path)
    
    try:
        # Check if this is a symusic Score object
        if hasattr(score, 'dump_musicxml'):
            # symusic native MusicXML export
            score.dump_musicxml(output_path)
            logger.info("export_musicxml_complete", output=output_path, size=Path(output_path).stat().st_size)
            return output_path
        elif hasattr(score, 'dump_midi'):
            # Fallback: export as MIDI, then convert to MusicXML
            logger.warning("musicxml_not_supported_using_midi_fallback")
            midi_path = str(Path(output_path).with_suffix('.mid'))
            score.dump_midi(midi_path)
            
            # Convert MIDI to MusicXML using music21 as converter
            try:
                from music21 import converter
                midi_score = converter.parse(midi_path)
                midi_score.write("musicxml", fp=output_path)
                Path(midi_path).unlink(missing_ok=True)  # Clean up temp MIDI
                logger.info("export_musicxml_complete_via_midi", output=output_path, size=Path(output_path).stat().st_size)
                return output_path
            except Exception as conv_error:
                logger.error("midi_to_musicxml_conversion_failed", error=str(conv_error))
                # Keep the MIDI file as fallback
                logger.info("keeping_midi_file_as_fallback", path=midi_path)
                raise RuntimeError(f"MusicXML export failed, MIDI available at {midi_path}") from conv_error
        else:
            raise RuntimeError(f"Unsupported score type: {type(score)}. Expected symusic.Score")
            
    except Exception as e:
        error_msg = str(e)
        logger.error("export_musicxml_failed", error=error_msg)
        raise RuntimeError(f"MusicXML export failed: {error_msg}") from e


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
    Export MusicXML to PDF via LilyPond CLI.
    
    Uses musicxml2ly to convert MusicXML to LilyPond format, then
    LilyPond CLI to render PDF. This bypasses music21's LilyPond
    conversion which has compatibility issues.
    """
    logger.info("export_pdf_lilypond_start", input=musicxml_path, output=output_path)

    try:
        # Step 1: Convert MusicXML to LilyPond format using musicxml2ly
        ly_path = Path(output_path).with_suffix(".ly")
        
        # musicxml2ly is included with LilyPond
        musicxml2ly_cmd = ["musicxml2ly", "-o", str(ly_path), musicxml_path]
        
        result = subprocess.run(
            musicxml2ly_cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        
        if result.returncode != 0:
            logger.warning(
                "musicxml2ly_conversion_failed",
                returncode=result.returncode,
                stderr=result.stderr[:500] if result.stderr else "",
            )
            return False

        # Step 2: Run LilyPond CLI to produce PDF
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

    except FileNotFoundError as e:
        logger.warning(
            "export_pdf_lilypond_not_found",
            bin=str(e),
            message="LilyPond or musicxml2ly not installed — PDF export skipped",
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
