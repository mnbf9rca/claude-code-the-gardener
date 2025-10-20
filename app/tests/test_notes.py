"""
Unit Tests for Notes Module

These tests verify the notes functionality including:
- Saving notes with replace mode
- Saving notes with append mode
- Fetching notes (empty and with content)
- Archive file creation and naming
- State persistence across tool calls
- Edge cases (append to empty, large notes)
"""

import pytest
import pytest_asyncio
import json
from datetime import datetime, timezone
from freezegun import freeze_time
from fastmcp import FastMCP
import tools.notes as notes_module
from tools.notes import setup_notes_tools


@pytest_asyncio.fixture(autouse=True)
async def setup_notes_state(tmp_path):
    """Reset notes state before each test"""
    # Store original paths
    original_notes_file = notes_module.NOTES_FILE
    original_archive_dir = notes_module.NOTES_ARCHIVE_DIR

    # Use temp directory for state files (don't touch production state!)
    notes_module.NOTES_FILE = tmp_path / "notes.md"
    notes_module.NOTES_ARCHIVE_DIR = tmp_path / "notes_archive"

    # Create MCP instance and setup tools
    mcp = FastMCP("test")
    setup_notes_tools(mcp)

    yield mcp

    # Restore original paths
    notes_module.NOTES_FILE = original_notes_file
    notes_module.NOTES_ARCHIVE_DIR = original_archive_dir


@pytest.mark.asyncio
async def test_save_notes_replace_mode(setup_notes_state):
    """Test saving a note with replace mode"""
    mcp = setup_notes_state
    save_tool = mcp._tool_manager._tools["save_notes"]

    # Save initial note
    tool_result = await save_tool.run(arguments={
        "content": "# My First Note\n\nThis is the content.",
        "mode": "replace"
    })
    result = json.loads(tool_result.content[0].text)

    assert result["success"] is True
    assert "timestamp" in result
    assert result["note_length_chars"] == 37  # "# My First Note\n\nThis is the content."

    # Verify file was created
    assert notes_module.NOTES_FILE.exists()
    content = notes_module.NOTES_FILE.read_text()
    assert content == "# My First Note\n\nThis is the content."


@pytest.mark.asyncio
async def test_save_notes_append_mode(setup_notes_state):
    """Test appending to an existing note"""
    mcp = setup_notes_state
    save_tool = mcp._tool_manager._tools["save_notes"]

    # Save initial note
    await save_tool.run(arguments={
        "content": "First paragraph.",
        "mode": "replace"
    })

    # Append to it
    tool_result = await save_tool.run(arguments={
        "content": "Second paragraph.",
        "mode": "append"
    })
    result = json.loads(tool_result.content[0].text)

    assert result["success"] is True
    # Length should be: "First paragraph." (16) + "\n" (1) + "Second paragraph." (17) = 34
    assert result["note_length_chars"] == 34

    # Verify content
    content = notes_module.NOTES_FILE.read_text()
    assert content == "First paragraph.\nSecond paragraph."


@pytest.mark.asyncio
async def test_append_to_empty_note(setup_notes_state):
    """Test appending when no note exists (should work like replace)"""
    mcp = setup_notes_state
    save_tool = mcp._tool_manager._tools["save_notes"]

    # Append to non-existent note
    tool_result = await save_tool.run(arguments={
        "content": "First content via append.",
        "mode": "append"
    })
    result = json.loads(tool_result.content[0].text)

    assert result["success"] is True
    assert result["note_length_chars"] == 25

    # Should not have extra newlines
    content = notes_module.NOTES_FILE.read_text()
    assert content == "First content via append."


@pytest.mark.asyncio
async def test_fetch_notes_empty(setup_notes_state):
    """Test fetching notes when no note exists"""
    mcp = setup_notes_state
    fetch_tool = mcp._tool_manager._tools["fetch_notes"]

    tool_result = await fetch_tool.run(arguments={})
    result = json.loads(tool_result.content[0].text)

    assert result["content"] == ""


@pytest.mark.asyncio
async def test_fetch_notes_with_content(setup_notes_state):
    """Test fetching existing note content"""
    mcp = setup_notes_state
    save_tool = mcp._tool_manager._tools["save_notes"]
    fetch_tool = mcp._tool_manager._tools["fetch_notes"]

    # Save a note
    await save_tool.run(arguments={
        "content": "# Test Note\n\nSome content here.",
        "mode": "replace"
    })

    # Fetch it
    tool_result = await fetch_tool.run(arguments={})
    result = json.loads(tool_result.content[0].text)

    assert result["content"] == "# Test Note\n\nSome content here."


@pytest.mark.asyncio
async def test_archive_file_creation(setup_notes_state):
    """Test that archive files are created on save"""
    mcp = setup_notes_state
    save_tool = mcp._tool_manager._tools["save_notes"]

    # Save a note
    await save_tool.run(arguments={
        "content": "Archived content.",
        "mode": "replace"
    })

    # Check archive directory was created
    assert notes_module.NOTES_ARCHIVE_DIR.exists()
    assert notes_module.NOTES_ARCHIVE_DIR.is_dir()

    # Check archive file was created
    archive_files = list(notes_module.NOTES_ARCHIVE_DIR.glob("*.md"))
    assert len(archive_files) == 1

    # Verify archive content
    archive_content = archive_files[0].read_text()
    assert archive_content == "Archived content."


@pytest.mark.asyncio
async def test_archive_file_naming(setup_notes_state):
    """Test that archive files have correct timestamp format"""
    mcp = setup_notes_state
    save_tool = mcp._tool_manager._tools["save_notes"]

    # Freeze time for predictable filename
    test_time = datetime(2024, 10, 20, 14, 30, 45, tzinfo=timezone.utc)
    with freeze_time(test_time):
        await save_tool.run(arguments={
            "content": "Test content.",
            "mode": "replace"
        })

    # Check filename format: YYYY-MM-DD_HH-MM-SS_UTC.md
    expected_filename = "2024-10-20_14-30-45_UTC.md"
    archive_file = notes_module.NOTES_ARCHIVE_DIR / expected_filename
    assert archive_file.exists()


@pytest.mark.asyncio
async def test_multiple_saves_create_multiple_archives(setup_notes_state):
    """Test that each save creates a new archive file"""
    mcp = setup_notes_state
    save_tool = mcp._tool_manager._tools["save_notes"]

    # Save first note
    base_time = datetime(2024, 10, 20, 10, 0, 0, tzinfo=timezone.utc)
    with freeze_time(base_time):
        await save_tool.run(arguments={
            "content": "First save.",
            "mode": "replace"
        })

    # Save second note (1 hour later)
    with freeze_time(base_time.replace(hour=11)):
        await save_tool.run(arguments={
            "content": "Second save.",
            "mode": "replace"
        })

    # Save third note (2 hours later)
    with freeze_time(base_time.replace(hour=12)):
        await save_tool.run(arguments={
            "content": "Third save.",
            "mode": "append"
        })

    # Check we have 3 archive files
    archive_files = list(notes_module.NOTES_ARCHIVE_DIR.glob("*.md"))
    assert len(archive_files) == 3

    # Verify filenames are different
    filenames = {f.name for f in archive_files}
    assert len(filenames) == 3


@pytest.mark.asyncio
async def test_replace_mode_overwrites_existing(setup_notes_state):
    """Test that replace mode completely replaces existing content"""
    mcp = setup_notes_state
    save_tool = mcp._tool_manager._tools["save_notes"]

    # Save initial note
    await save_tool.run(arguments={
        "content": "Original content that should be replaced.",
        "mode": "replace"
    })

    # Replace it
    await save_tool.run(arguments={
        "content": "New content.",
        "mode": "replace"
    })

    # Verify only new content exists
    content = notes_module.NOTES_FILE.read_text()
    assert content == "New content."
    assert "Original" not in content


@pytest.mark.asyncio
async def test_large_note_content(setup_notes_state):
    """Test saving and fetching a large note"""
    mcp = setup_notes_state
    save_tool = mcp._tool_manager._tools["save_notes"]
    fetch_tool = mcp._tool_manager._tools["fetch_notes"]

    # Create large content (10KB)
    large_content = "# Large Note\n\n" + ("Lorem ipsum dolor sit amet. " * 400)

    # Save it
    tool_result = await save_tool.run(arguments={
        "content": large_content,
        "mode": "replace"
    })
    result = json.loads(tool_result.content[0].text)

    assert result["success"] is True
    assert result["note_length_chars"] == len(large_content)

    # Fetch it
    tool_result = await fetch_tool.run(arguments={})
    result = json.loads(tool_result.content[0].text)

    assert result["content"] == large_content


@pytest.mark.asyncio
async def test_markdown_formatting_preserved(setup_notes_state):
    """Test that markdown formatting is preserved"""
    mcp = setup_notes_state
    save_tool = mcp._tool_manager._tools["save_notes"]
    fetch_tool = mcp._tool_manager._tools["fetch_notes"]

    markdown_content = """# Plant Care Notes

## Current Status
- Moisture: Good
- Light: Adequate

### Recent Actions
1. Watered 40ml
2. Light on for 90 minutes

**Next Steps:**
- Monitor moisture levels
- Consider increasing light duration

> Note: Plant showing healthy growth
"""

    # Save markdown
    await save_tool.run(arguments={
        "content": markdown_content,
        "mode": "replace"
    })

    # Fetch and verify
    tool_result = await fetch_tool.run(arguments={})
    result = json.loads(tool_result.content[0].text)

    assert result["content"] == markdown_content


@pytest.mark.asyncio
async def test_empty_content(setup_notes_state):
    """Test saving an empty note"""
    mcp = setup_notes_state
    save_tool = mcp._tool_manager._tools["save_notes"]
    fetch_tool = mcp._tool_manager._tools["fetch_notes"]

    # Save empty note
    tool_result = await save_tool.run(arguments={
        "content": "",
        "mode": "replace"
    })
    result = json.loads(tool_result.content[0].text)

    assert result["success"] is True
    assert result["note_length_chars"] == 0

    # Fetch it
    tool_result = await fetch_tool.run(arguments={})
    result = json.loads(tool_result.content[0].text)

    assert result["content"] == ""


@pytest.mark.asyncio
async def test_unicode_content(setup_notes_state):
    """Test saving notes with unicode characters"""
    mcp = setup_notes_state
    save_tool = mcp._tool_manager._tools["save_notes"]
    fetch_tool = mcp._tool_manager._tools["fetch_notes"]

    unicode_content = "🌱 Plant notes with émojis and spëcial çharacters! 日本語 العربية"

    # Save unicode content
    await save_tool.run(arguments={
        "content": unicode_content,
        "mode": "replace"
    })

    # Fetch and verify
    tool_result = await fetch_tool.run(arguments={})
    result = json.loads(tool_result.content[0].text)

    assert result["content"] == unicode_content

    # Verify archive also preserved unicode
    archive_files = list(notes_module.NOTES_ARCHIVE_DIR.glob("*.md"))
    assert len(archive_files) == 1
    archive_content = archive_files[0].read_text(encoding='utf-8')
    assert archive_content == unicode_content
