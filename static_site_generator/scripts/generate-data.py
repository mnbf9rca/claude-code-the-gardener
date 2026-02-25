#!/usr/bin/env python3
"""
Data generator for Astro static site.
Orchestrates existing parsers to generate JSON files.
"""

import argparse
import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from parsers import stats, conversations, sensors, actions


def main():
    parser = argparse.ArgumentParser(description="Generate JSON data for Astro site")
    parser.add_argument(
        "--data-dir",
        type=Path,
        required=True,
        help="Path to data directory (JSONL files)"
    )
    parser.add_argument(
        "--photos-dir",
        type=Path,
        required=True,
        help="Path to photos directory"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Path to output directory for JSON files"
    )

    args = parser.parse_args()

    # Validate input directories
    if not args.data_dir.exists():
        print(f"ERROR: Data directory not found: {args.data_dir}")
        sys.exit(1)

    # Create output directory
    args.output_dir.mkdir(parents=True, exist_ok=True)

    print("Parsing statistics...")
    stats_data = stats.parse_stats(args.data_dir)
    with open(args.output_dir / "stats.json", "w") as f:
        json.dump(stats_data, f, indent=2, default=str)

    print("Parsing conversations...")
    conversations_data = conversations.parse_conversations(args.data_dir / "claude")
    with open(args.output_dir / "conversations.json", "w") as f:
        json.dump(conversations_data, f, indent=2, default=str)

    print("Parsing sensor data...")
    sensor_data = sensors.parse_sensors(args.data_dir)
    with open(args.output_dir / "sensors.json", "w") as f:
        json.dump(sensor_data, f, indent=2, default=str)

    print("Parsing timeline...")
    timeline_data = actions.parse_timeline(args.data_dir)
    with open(args.output_dir / "timeline.json", "w") as f:
        json.dump(timeline_data, f, indent=2, default=str)

    print(f"✓ Generated data files in {args.output_dir}")


if __name__ == "__main__":
    main()
