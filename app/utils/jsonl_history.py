"""
JSONL History Utility - Reusable JSONL file management with in-memory cache

This utility provides a consistent pattern for managing append-only JSONL files
with a bounded in-memory cache. Used across multiple tools for state persistence.
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections import deque
import json
from utils.logging_config import get_logger

logger = get_logger(__name__)


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
        self._history: deque[Dict[str, Any]] = deque()

        # Lazy loading flag
        self._loaded = False

    def _initialize_file(self):
        """Ensure the JSONL file exists."""
        if not self.file_path.exists() and self.auto_create:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            self.file_path.touch()
            logger.debug(f"Initialized JSONL file: {self.file_path}")

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
            logger.warning(f"Failed to append to {self.file_path}: {e}")

    def load(self):
        """
        Load entries from disk into memory.
        Loads up to max_memory_entries most recent events.
        """
        try:
            self._initialize_file()

            if not self.file_path.exists() or self.file_path.stat().st_size == 0:
                self._history = deque()
                logger.debug(f"No existing history found at {self.file_path}")
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
                        logger.warning(f"Skipping malformed line in {self.file_path}: {e}")
                        continue

            # Keep only the most recent max_memory_entries
            if len(all_events) > self.max_memory_entries:
                all_events = all_events[-self.max_memory_entries:]

            self._history = deque(all_events)
            logger.debug(f"Loaded {len(self._history)} entries from {self.file_path}")

        except Exception as e:
            logger.error(f"Failed to load history from {self.file_path}: {e}")
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

        # Skip offset from the end, then take N
        start_idx = max(0, total - offset - n)
        return all_entries[start_idx:total - offset]

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
            except (KeyError, ValueError) as e:
                logger.warning(
                    "Skipping entry in get_by_time_range due to timestamp issue: %s | Entry: %s",
                    e, entry
                )
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

        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)

        matching = []
        for entry in self._history:
            try:
                entry_time = datetime.fromisoformat(entry[timestamp_key])
                if entry_time >= cutoff_time:
                    matching.append(entry)
            except (KeyError, ValueError) as e:
                logger.warning(
                    "Skipping entry in get_by_time_window due to timestamp issue: %s | Entry: %s",
                    e, entry
                )
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

    def get_time_bucketed_sample(
        self,
        hours: int,
        samples_per_hour: int = 6,
        timestamp_key: str = "timestamp",
        aggregation: str = "middle",
        end_time: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Sample entries evenly across time, not by index.

        Divides the time window into equal-sized buckets and returns
        one sample per bucket, ensuring proper temporal distribution.
        Empty buckets (no readings) are skipped.

        Args:
            hours: Time window in hours backwards from end_time
            samples_per_hour: Target number of samples per hour (default 6)
            timestamp_key: Dict key containing ISO8601 timestamp
            aggregation: Strategy when multiple entries in bucket
                - "first": Earliest entry in bucket
                - "last": Latest entry in bucket
                - "middle": Entry closest to bucket midpoint
            end_time: End of time window (defaults to now if None)

        Returns:
            List of sampled entries with proper temporal distribution
        """
        # Default to now if no end_time specified
        if end_time is None:
            end_time = datetime.now(timezone.utc)

        # Calculate time window
        start_time = end_time - timedelta(hours=hours)

        # Get entries in the time range
        entries = self.get_by_time_range(
            start_time=start_time,
            end_time=end_time,
            timestamp_key=timestamp_key
        )

        if not entries:
            return []

        # Sort entries by timestamp to ensure chronological order
        # (JSONL load order doesn't guarantee temporal order)
        entries_with_time = []
        for entry in entries:
            try:
                entry_time = datetime.fromisoformat(entry[timestamp_key])
                entries_with_time.append((entry_time, entry))
            except (KeyError, ValueError) as e:
                logger.warning(
                    "Skipping entry in get_time_bucketed_sample during sort: %s | Entry: %s",
                    e, entry
                )

        entries_with_time.sort(key=lambda x: x[0])

        # Calculate bucket size
        bucket_duration = timedelta(hours=1) / samples_per_hour

        # Create buckets
        total_buckets = hours * samples_per_hour
        sampled = []

        for i in range(total_buckets):
            bucket_start = start_time + (bucket_duration * i)
            bucket_end = bucket_start + bucket_duration

            # Find entries in this bucket (already sorted and parsed)
            bucket_entries = [
                entry for entry_time, entry in entries_with_time
                if bucket_start <= entry_time < bucket_end
            ]

            # Skip empty buckets
            if not bucket_entries:
                continue

            # Apply aggregation strategy
            if aggregation == "first":
                sampled.append(bucket_entries[0])
            elif aggregation == "last":
                sampled.append(bucket_entries[-1])
            elif aggregation == "middle":
                # Find entry closest to bucket midpoint
                bucket_midpoint = bucket_start + (bucket_duration / 2)
                closest_entry = min(
                    bucket_entries,
                    key=lambda e: abs(
                        datetime.fromisoformat(e[timestamp_key]) - bucket_midpoint
                    )
                )
                sampled.append(closest_entry)
            else:
                raise ValueError(f"Unknown aggregation strategy: '{aggregation}'. Must be 'first', 'last', or 'middle'.")

        return sampled

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
