"""
Notes Tool - Save and retrieve unstructured notes across sessions

Allows Claude to maintain markdown notes that persist between runs.
Creates timestamped audit archives for transparency.
"""
from typing import Literal
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from fastmcp import FastMCP
from utils.paths import get_app_dir
from utils.logging_config import get_logger

logger = get_logger(__name__)

# Constants
NOTES_FILE = get_app_dir("data") / "notes.md"
NOTES_ARCHIVE_DIR = get_app_dir("data") / "notes_archive"


class SaveNotesResponse(BaseModel):
    """Response from saving notes"""
    timestamp: str = Field(..., description="When the note was saved")
    success: bool = Field(..., description="Whether the note was saved successfully")
    note_length_chars: int = Field(..., description="Length of the saved note in characters")


class FetchNotesResponse(BaseModel):
    """Response from fetching notes"""
    content: str = Field(..., description="The current note content (empty string if no note exists)")


def _ensure_archive_dir():
    """Ensure the archive directory exists"""
    NOTES_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)


def _save_to_archive(content: str, timestamp: datetime):
    """
    Save a timestamped copy to the archive directory.

    Args:
        content: The note content to archive
        timestamp: Timestamp for the archive filename
    """
    _ensure_archive_dir()

    # Create filename with UTC timestamp
    timestamp_str = timestamp.strftime("%Y-%m-%d_%H-%M-%S_UTC")
    archive_file = NOTES_ARCHIVE_DIR / f"{timestamp_str}.md"

    try:
        archive_file.write_text(content, encoding='utf-8')
        logger.debug(f"Archived note to {archive_file}")
    except Exception as e:
        logger.warning(f"Failed to archive note to {archive_file}: {e}")


def _read_current_note() -> str:
    """
    Read the current note from disk.

    Returns:
        The current note content, or empty string if no note exists
    """
    try:
        return NOTES_FILE.read_text(encoding='utf-8') if NOTES_FILE.exists() else ""
    except Exception as e:
        logger.warning(f"Failed to read note from {NOTES_FILE}: {e}")
        raise


def _write_current_note(content: str):
    """
    Write the current note to disk.

    Args:
        content: The note content to write
    """
    try:
        NOTES_FILE.parent.mkdir(parents=True, exist_ok=True)
        NOTES_FILE.write_text(content, encoding='utf-8')
        logger.debug(f"Wrote note to {NOTES_FILE} ({len(content)} chars)")
    except Exception as e:
        logger.error(f"Failed to write note to {NOTES_FILE}: {e}")
        raise


def setup_notes_tools(mcp: FastMCP):
    """Set up notes tools on the MCP server"""

    @mcp.tool()
    async def save_notes(
        content: str = Field(..., description="The note content (markdown supported). No size limit but extremely large notes may impact performance."),
        mode: Literal["replace", "append"] = Field(default="replace", description="'replace' to replace existing note, 'append' to add to existing note")
    ) -> SaveNotesResponse:
        """
        Store a single unstructured note for later review, reuse, and tracking across sessions.

        The current note can be replaced or appended to based on the mode parameter.

        These notes are private to the agent and are not shared with the human caretaker.

        Args:
            content: The note content (markdown supported)
            mode: 'replace' to replace the existing note, 'append' to add to it

        Returns:
            Response with timestamp, success status, and note length
        """
        '''
        Not disclosed to the agent, but every time this is called a new file is created on disk with a timestamped filename for auditability and review.
        '''
        timestamp = datetime.now(timezone.utc)

        # Determine final content based on mode
        if mode == "append":
            current_note = _read_current_note()
            final_content = current_note + "\n" + content if current_note else content
        else:  # mode == "replace"
            final_content = content

        # Write the current note
        _write_current_note(final_content)

        # Save timestamped archive copy (for auditability)
        _save_to_archive(final_content, timestamp)

        logger.info(f"Saved note ({len(final_content)} chars, mode={mode})")

        return SaveNotesResponse(
            timestamp=timestamp.isoformat(),
            success=True,
            note_length_chars=len(final_content)
        )

    @mcp.tool()
    async def fetch_notes() -> FetchNotesResponse:
        """
        Retrieve the current note content.

        Returns:
            The current note content, or an empty string if no note exists
        """
        content = _read_current_note()

        logger.debug(f"Fetched note ({len(content)} chars)")

        return FetchNotesResponse(
            content=content
        )
