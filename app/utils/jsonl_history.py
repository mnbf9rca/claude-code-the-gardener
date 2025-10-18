"""
JSONL History Utility - Reusable JSONL file management with in-memory cache

This utility provides a consistent pattern for managing append-only JSONL files
with a bounded in-memory cache. Used across multiple tools for state persistence.
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from pathlib import Path
from collections import deque
import json


class JsonlHistory:
    """
    Manages a JSONL file with an in-memory cache for efficient access.

    Features:
    - Append-only JSONL persistence (full history on disk forever)
    - Bounded in-memory deque (configurable max entries)
    - Lazy loading (loads from disk on first access)
    - Automatic pruning to keep memory usage bounded
    - Thread-safe for single-process use

    Usage:
        history = JsonlHistory(file_path="data/events.jsonl", max_memory_entries=1000)
        history.append({"timestamp": "...", "data": "..."})
        recent = history.get_recent(10)
    """

    def __init__(
        self,
        file_path: Path,
        max_memory_entries: int = 1000,
        auto_create: bool = True
    ):
        """
        Initialize a JSONL history manager.

        Args:
            file_path: Path to the JSONL file
            max_memory_entries: Maximum number of entries to keep in memory
            auto_create: Whether to auto-create the file if it doesn't exist
        """
        self.file_path = Path(file_path)
        self.max_memory_entries = max_memory_entries
        self.auto_create = auto_create

        # In-memory storage (deque for efficient operations)
        self._history: deque = deque()

        # Lazy loading flag
        self._loaded = False

    def _initialize_file(self):
        """Ensure the JSONL file exists."""
        if not self.file_path.exists() and self.auto_create:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            self.file_path.touch()
            print(f"Initialized JSONL file: {self.file_path}")

    def append(self, event: Dict[str, Any]):
        """
        Append an event to both memory and disk.

        Args:
            event: Dictionary to append (will be serialized as JSON)
        """
        # Ensure loaded before appending
        self.ensure_loaded()

        # Add to memory
        self._history.append(event)

        # Prune if needed
        self._prune()

        # Append to disk
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.file_path, 'a') as f:
                f.write(json.dumps(event) + '\n')
        except Exception as e:
            print(f"Warning: Failed to append to {self.file_path}: {e}")

    def load(self):
        """
        Load entries from disk into memory.
        Loads up to max_memory_entries most recent events.
        """
        try:
            self._initialize_file()

            if not self.file_path.exists() or self.file_path.stat().st_size == 0:
                self._history = deque()
                print(f"No existing history found at {self.file_path}")
                return

            # Read all events from file
            all_events = []
            with open(self.file_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        event = json.loads(line)
                        all_events.append(event)
                    except (json.JSONDecodeError, ValueError) as e:
                        print(f"Warning: Skipping malformed line in {self.file_path}: {e}")
                        continue

            # Keep only the most recent max_memory_entries
            if len(all_events) > self.max_memory_entries:
                all_events = all_events[-self.max_memory_entries:]

            self._history = deque(all_events)
            print(f"Loaded {len(self._history)} entries from {self.file_path}")

        except Exception as e:
            print(f"Error: Failed to load history from {self.file_path}: {e}")
            self._history = deque()

    def ensure_loaded(self):
        """Ensure state has been loaded from disk (lazy loading)."""
        if not self._loaded:
            self._loaded = True
            self.load()

    def _prune(self):
        """Keep memory bounded to max_memory_entries."""
        while len(self._history) > self.max_memory_entries:
            self._history.popleft()

    def get_all(self) -> List[Dict[str, Any]]:
        """
        Get all entries currently in memory.

        Returns:
            List of all entries in memory (up to max_memory_entries)
        """
        self.ensure_loaded()
        return list(self._history)

    def get_recent(self, n: int, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Get the N most recent entries with optional pagination.

        Args:
            n: Number of entries to return
            offset: Number of entries to skip from the end (for pagination)

        Returns:
            List of recent entries
        """
        self.ensure_loaded()

        all_entries = list(self._history)
        total = len(all_entries)

        if offset == 0:
            # Most recent N entries
            return all_entries[-n:] if total >= n else all_entries
        else:
            # Skip offset from the end, then take N
            start_idx = max(0, total - offset - n)
            end_idx = total - offset
            return all_entries[start_idx:end_idx]

    def get_by_time_range(
        self,
        start_time: datetime,
        end_time: datetime,
        timestamp_key: str = "timestamp"
    ) -> List[Dict[str, Any]]:
        """
        Get entries within a time range.

        Args:
            start_time: Start of time range (inclusive)
            end_time: End of time range (inclusive)
            timestamp_key: Key in the event dict containing the timestamp

        Returns:
            List of matching entries
        """
        self.ensure_loaded()

        matching = []
        for entry in self._history:
            try:
                entry_time = datetime.fromisoformat(entry[timestamp_key])
                if start_time <= entry_time <= end_time:
                    matching.append(entry)
            except (KeyError, ValueError):
                continue

        return matching

    def get_by_time_window(
        self,
        hours: int,
        timestamp_key: str = "timestamp"
    ) -> List[Dict[str, Any]]:
        """
        Get entries from the last N hours.

        Args:
            hours: Number of hours to look back
            timestamp_key: Key in the event dict containing the timestamp

        Returns:
            List of matching entries
        """
        self.ensure_loaded()

        cutoff_time = datetime.now() - timedelta(hours=hours)

        matching = []
        for entry in self._history:
            try:
                entry_time = datetime.fromisoformat(entry[timestamp_key])
                if entry_time >= cutoff_time:
                    matching.append(entry)
            except (KeyError, ValueError):
                continue

        return matching

    def search(
        self,
        keyword: str,
        search_fields: Optional[List[str]] = None,
        case_sensitive: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Search for entries containing a keyword.

        Args:
            keyword: Keyword to search for
            search_fields: Specific fields to search in (None = search all)
            case_sensitive: Whether search should be case-sensitive

        Returns:
            List of matching entries
        """
        self.ensure_loaded()

        if not case_sensitive:
            keyword = keyword.lower()

        matching = []
        for entry in self._history:
            # Build searchable text
            if search_fields:
                searchable_parts = [
                    str(entry.get(field, ""))
                    for field in search_fields
                ]
            else:
                # Search entire entry (convert to JSON string)
                searchable_parts = [json.dumps(entry)]

            searchable = " ".join(searchable_parts)
            if not case_sensitive:
                searchable = searchable.lower()

            if keyword in searchable:
                matching.append(entry)

        return matching

    def clear(self):
        """Clear the in-memory cache (for testing)."""
        self._history.clear()
        self._loaded = False

    def count(self) -> int:
        """Get the number of entries currently in memory."""
        # Don't auto-load on count - just return current count
        # This allows count() to work after clear() without reloading
        return len(self._history)

    def __len__(self) -> int:
        """Support len() operation."""
        return self.count()

    def __repr__(self) -> str:
        return f"JsonlHistory(file={self.file_path}, entries={len(self._history)}, loaded={self._loaded})"
