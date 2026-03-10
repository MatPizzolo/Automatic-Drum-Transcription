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
    
    # First attempt: try to write as-is
    try:
        music21_stream.write("musicxml", fp=output_path)
        logger.info("export_musicxml_complete", output=output_path, size=Path(output_path).stat().st_size)
        return output_path
    except Exception as e:
        error_msg = str(e)
        logger.warning("export_musicxml_first_attempt_failed", error=error_msg)
        
        # If it's a duration error, quantize and retry
        if "inexpressible" in error_msg.lower() or "duration" in error_msg.lower() or "cannot convert" in error_msg.lower():
            logger.info("export_musicxml_retry_with_quantization")
            try:
                # Quantize all durations to standard note values
                _quantize_stream_durations(music21_stream)
                
                # Retry the write
                music21_stream.write("musicxml", fp=output_path)
                logger.info("export_musicxml_complete_after_quantization", output=output_path, size=Path(output_path).stat().st_size)
                return output_path
            except Exception as e2:
                logger.error("export_musicxml_retry_failed", error=str(e2))
                # Last resort: create a simplified version
                logger.info("export_musicxml_creating_simplified_version")
                try:
                    _create_simplified_musicxml(music21_stream, output_path)
                    logger.info("export_musicxml_simplified_success", output=output_path)
                    return output_path
                except Exception as e3:
                    logger.error("export_musicxml_all_attempts_failed", error=str(e3))
                    raise RuntimeError(f"MusicXML export failed after all retry attempts: {error_msg}") from e
        else:
            raise RuntimeError(f"MusicXML export failed: {error_msg}") from e


def _quantize_stream_durations(music21_stream: Any) -> None:
    """
    Quantize all note durations in a stream to standard values.
    This fixes "inexpressible durations" errors.
    """
    from music21 import duration
    
    # Standard duration values (in quarter notes)
    STANDARD_DURATIONS = [0.25, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0]
    
    for element in music21_stream.flatten().notesAndRests:
        current_duration = element.duration.quarterLength
        
        # Find closest standard duration
        closest = min(STANDARD_DURATIONS, key=lambda x: abs(x - current_duration))
        
        # Only change if different
        if abs(closest - current_duration) > 0.01:
            element.duration = duration.Duration(closest)


def _create_simplified_musicxml(music21_stream: Any, output_path: str) -> None:
    """
    Create a simplified MusicXML by rebuilding the stream with only essential elements.
    This is a last resort when normal export fails.
    """
    from music21 import stream, note, meter, tempo, metadata, duration, percussion, instrument, clef
    
    # Create a new simplified stream with measures
    simplified = stream.Score()
    part = stream.Part()
    
    # Set part metadata for drums
    part.partName = "Drums"
    
    # Add metadata
    if hasattr(music21_stream, 'metadata') and music21_stream.metadata:
        simplified.insert(0, metadata.Metadata())
        if hasattr(music21_stream.metadata, 'title'):
            simplified.metadata.title = music21_stream.metadata.title
    
    # Get time signature and tempo from original
    time_sig = meter.TimeSignature('4/4')  # Default
    tempo_mark = tempo.MetronomeMark(number=120)  # Default
    
    for element in music21_stream.flatten():
        if isinstance(element, meter.TimeSignature):
            time_sig = element
            break
    
    for element in music21_stream.flatten():
        if isinstance(element, tempo.MetronomeMark):
            tempo_mark = element
            break
    
    # Insert percussion metadata at the start of the part
    part.insert(0, instrument.Percussion())
    part.insert(0, clef.PercussionClef())
    
    # Add time signature and tempo to part
    part.insert(0, time_sig)
    part.insert(0, tempo_mark)
    
    # Add all notes with standard eighth-note duration, rounded to nearest eighth
    for element in music21_stream.flatten().notesAndRests:
        # Round offset to nearest eighth note (0.5 quarter notes)
        rounded_offset = round(element.offset * 2) / 2
        
        if isinstance(element, percussion.PercussionChord):
            # Handle percussion chords
            new_chord = percussion.PercussionChord(element.pitches)
            new_chord.duration = duration.Duration(0.5)
            if hasattr(element, 'stemDirection'):
                new_chord.stemDirection = element.stemDirection
            part.insert(rounded_offset, new_chord)
        elif isinstance(element, note.Unpitched):
            # Handle unpitched drum notes
            new_note = note.Unpitched(element.displayName)
            new_note.duration = duration.Duration(0.5)  # Eighth note
            if hasattr(element, 'notehead'):
                new_note.notehead = element.notehead
            if hasattr(element, 'stemDirection'):
                new_note.stemDirection = element.stemDirection
            part.insert(rounded_offset, new_note)
        elif hasattr(element, 'pitch'):
            # Handle regular pitched notes (fallback)
            new_note = note.Note(element.pitch)
            new_note.duration = duration.Duration(0.5)
            if hasattr(element, 'notehead'):
                new_note.notehead = element.notehead
            if hasattr(element, 'stemDirection'):
                new_note.stemDirection = element.stemDirection
            part.insert(rounded_offset, new_note)
    
    # Make measures (without fillGaps parameter)
    part = part.makeMeasures()
    simplified.append(part)
    
    # Write to file
    simplified.write("musicxml", fp=output_path)


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
            # Fallback: try direct LilyPond conversion
            return _export_pdf_direct_lilypond(musicxml_path, output_path)

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


def _export_pdf_direct_lilypond(musicxml_path: str, output_path: str) -> bool:
    """
    Fallback: Use music21 to convert MusicXML to PDF via LilyPond.
    This may have compatibility issues but is better than nothing.
    """
    logger.info("export_pdf_direct_lilypond_fallback", input=musicxml_path)
    
    try:
        from music21 import converter
        
        # Load MusicXML
        score = converter.parse(musicxml_path)
        
        # Write directly to PDF (music21 will use LilyPond internally)
        score.write("lily.pdf", fp=output_path)
        
        if Path(output_path).exists():
            logger.info("export_pdf_direct_lilypond_success", output=output_path)
            return True
        else:
            logger.warning("export_pdf_direct_lilypond_failed")
            return False
            
    except Exception as e:
        logger.error("export_pdf_direct_lilypond_error", error=str(e))
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
