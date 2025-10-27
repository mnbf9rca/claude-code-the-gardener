#\!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Static site generator for Claude the Gardener.
Parses all data and generates an interactive HTML site.

SECURITY NOTE: XSS Warnings from Static Analysis Tools
-------------------------------------------------------
This is a STATIC SITE GENERATOR, not a Flask web application. Code analysis tools
may flag the direct use of Jinja2 as an XSS risk, but this is a false positive because:

1. All content comes from TRUSTED LOCAL FILES (conversation logs, sensor data)
2. There is NO user-submitted content or external input
3. The generated HTML is served statically (e.g., from S3), not dynamically
4. The | safe filter in templates is intentionally used to render pre-formatted
   HTML from Python formatter functions

This code does not have the same threat model as a Flask web app accepting user input.
The use of Jinja2 here is safe and appropriate for static site generation.
"""

import argparse
import json
import shutil
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape

# Import our parsers
from parsers import stats, conversations, sensors, actions


def parse_args():
    """Parse command line arguments."""
    # Default paths relative to script location
    script_dir = Path(__file__).parent
    project_root = script_dir.parent

    parser = argparse.ArgumentParser(
        description="Static site generator for Claude the Gardener",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "--data-dir",
        type=Path,
        default=project_root / "app" / "data",
        help="Path to data directory containing JSONL files",
    )

    parser.add_argument(
        "--conversations-dir",
        type=Path,
        default=None,
        help="Path to conversations directory (defaults to data-dir/claude)",
    )

    parser.add_argument(
        "--photos-dir",
        type=Path,
        default=project_root / "app" / "photos",
        help="Path to photos directory containing plant images",
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=script_dir / "output",
        help="Path to output directory for generated site",
    )

    args = parser.parse_args()

    # Default conversations_dir to data_dir/claude if not specified
    if args.conversations_dir is None:
        args.conversations_dir = args.data_dir / "claude"

    return args


def main():
    """Main generator function."""

    # Parse command line arguments
    args = parse_args()

    # Convert to absolute paths and validate
    data_dir = args.data_dir.resolve()
    conversations_dir = args.conversations_dir.resolve()
    photos_dir = args.photos_dir.resolve()
    output_dir = args.output_dir.resolve()

    # Fixed paths (relative to script location)
    templates_dir = Path(__file__).parent / "templates"
    static_dir = Path(__file__).parent / "static"

    print("Claude the Gardener - Static Site Generator")
    print("=" * 50)
    print()
    print("Configuration:")
    print(f"  Data directory:          {data_dir}")
    print(f"  Conversations directory: {conversations_dir}")
    print(f"  Photos directory:        {photos_dir}")
    print(f"  Output directory:        {output_dir}")
    print()

    # Validate required paths
    if not data_dir.exists():
        print(f"Error: Data directory not found: {data_dir}")
        print("   Run ./static_site_generator/sync_data.sh first!")
        return 1

    if not templates_dir.exists():
        print(f"Error: Templates directory not found: {templates_dir}")
        print("   This should be part of the repository structure!")
        return 1

    # Create output directories
    print("Creating output directories...")
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "conversations").mkdir(parents=True, exist_ok=True)
    (output_dir / "photos").mkdir(parents=True, exist_ok=True)
    (output_dir / "static").mkdir(parents=True, exist_ok=True)
    (output_dir / "data").mkdir(parents=True, exist_ok=True)

    # Setup Jinja2
    print("Setting up template engine...")
    env = Environment(
        loader=FileSystemLoader(templates_dir),
        autoescape=select_autoescape(['html', 'xml']),
        trim_blocks=True,
        lstrip_blocks=True,
    )

    # Add custom filters
    env.filters['format_number'] = lambda x: f"{x:,}"
    env.filters['format_bytes'] = lambda x: f"{x / 1_000_000:.2f}M" if x > 1_000_000 else f"{x / 1_000:.1f}K"

    # Parse all data
    print()
    print("Parsing data...")
    print("-" * 50)

    print("  - Calculating overall statistics...")
    overall_stats = stats.calculate_overall_stats(data_dir)
    daily_summary = stats.get_daily_summary(data_dir)

    print("  - Parsing conversations...")
    all_conversations = conversations.get_all_conversations(conversations_dir)
    conversation_highlights = conversations.get_highlights(all_conversations)
    print(f"    Found {len(all_conversations)} conversations ({len(conversation_highlights)} highlights)")

    print("  - Processing sensor data...")
    sensor_data = sensors.get_combined_sensor_data(data_dir, all_conversations)
    sensor_summary = sensors.get_sensor_summary(data_dir)
    print(f"    Moisture: {len(sensor_data['moisture'])} readings")
    print(f"    Light: {len(sensor_data['light'])} sessions")
    print(f"    Water: {len(sensor_data['water'])} events")
    print(f"    Cost tracking: {len(sensor_data.get('cost', []))} data points")
    print(f"    Tokens tracking: {len(sensor_data.get('tokens', []))} data points")

    print("  - Building timeline...")
    timeline = actions.get_unified_timeline(data_dir)
    timeline_highlights = actions.detect_highlights(timeline)
    print(f"    {len(timeline)} events ({len(timeline_highlights)} highlights)")

    print("  - Correlating timeline with conversations...")
    timeline = actions.correlate_timeline_with_conversations(timeline, all_conversations)
    linked_events = sum(bool('session_id' in e) for e in timeline)
    print(f"    {linked_events}/{len(timeline)} events linked to conversations")

    # Export data as JSON for JavaScript
    print()
    print("Exporting data for JavaScript...")
    (output_dir / "data" / "sensor_data.json").write_text(json.dumps(sensor_data, indent=2))
    (output_dir / "data" / "timeline.json").write_text(json.dumps(timeline[:1000], indent=2))  # Limit to 1000 recent events
    (output_dir / "data" / "stats.json").write_text(json.dumps(overall_stats, indent=2))

    # Generate pages
    print()
    print("Generating HTML pages...")
    print("-" * 50)

    # Index page
    print("  - index.html (dashboard)")
    index_template = env.get_template("index.html")
    index_html = index_template.render(
        nav_base="",
        stats=overall_stats,
        sensor_summary=sensor_summary,
        recent_conversations=all_conversations[:10],
        recent_timeline=timeline[:20],
        highlights=conversation_highlights[:5] + timeline_highlights[:5],
        daily_summary=daily_summary[-7:],  # Last 7 days
    )
    (output_dir / "index.html").write_text(index_html)

    # Conversations list
    print("  - conversations/index.html (conversation browser)")
    conv_list_template = env.get_template("conversations.html")
    conv_list_html = conv_list_template.render(
        nav_base="../",
        conversations=all_conversations,
        highlights=conversation_highlights,
        stats=overall_stats,
    )
    (output_dir / "conversations" / "index.html").write_text(conv_list_html)

    # Individual conversation pages
    print(f"  - Generating {len(all_conversations)} conversation detail pages...")
    conv_detail_template = env.get_template("conversation_detail.html")
    for conv in all_conversations:
        conv_html = conv_detail_template.render(nav_base="../", conversation=conv)
        (output_dir / "conversations" / f"{conv['session_id']}.html").write_text(conv_html)

    # Timeline page
    print("  - timeline.html (interactive timeline)")
    timeline_template = env.get_template("timeline.html")
    timeline_html = timeline_template.render(
        nav_base="",
        timeline=timeline[:500],  # Limit to 500 recent for initial load
        highlights=timeline_highlights,
        stats=overall_stats,
    )
    (output_dir / "timeline.html").write_text(timeline_html)

    # Sensors page
    print("  - sensors.html (sensor charts)")
    sensors_template = env.get_template("sensors.html")
    sensors_html = sensors_template.render(
        nav_base="",
        sensor_summary=sensor_summary,
        stats=overall_stats,
    )
    (output_dir / "sensors.html").write_text(sensors_html)

    # Photos page
    print("  - photos.html (photo gallery)")
    photos_template = env.get_template("photos.html")
    camera_file = data_dir / "camera_usage.jsonl"
    camera_records = stats.load_jsonl(camera_file)

    # Check which photos actually exist on disk
    for record in camera_records:
        if record.get("photo_path"):
            photo_filename = Path(record["photo_path"]).name
            photo_exists = (photos_dir / photo_filename).exists()
            record["photo_exists"] = photo_exists

    photos_html = photos_template.render(
        nav_base="",
        photos=camera_records,
        stats=overall_stats,
    )
    (output_dir / "photos.html").write_text(photos_html)

    # Notes evolution page
    print("  - notes.html (notes evolution)")
    notes_template = env.get_template("notes.html")
    notes_archive_dir = data_dir / "notes_archive"
    current_notes_file = data_dir / "notes.md"

    notes_versions = []
    if notes_archive_dir.exists():
        for notes_file in sorted(notes_archive_dir.glob("*.md")):
            notes_versions.append({
                "filename": notes_file.name,
                "timestamp": notes_file.name.split("_UTC")[0].replace("_", " ").replace("-", "/"),
                "content": notes_file.read_text(),
            })

    current_notes = current_notes_file.read_text() if current_notes_file.exists() else ""

    notes_html = notes_template.render(
        nav_base="",
        current_notes=current_notes,
        versions=notes_versions[-50:],  # Last 50 versions
        stats=overall_stats,
    )
    (output_dir / "notes.html").write_text(notes_html)

    # Copy static assets
    print()
    print("Copying static assets...")
    if static_dir.exists():
        shutil.copytree(static_dir, output_dir / "static", dirs_exist_ok=True)

    # Copy photos
    if photos_dir.exists():
        print(f"Copying photos from {photos_dir}...")
        photo_count = 0
        for photo in photos_dir.glob("plant_*.jpg"):
            shutil.copy2(photo, output_dir / "photos" / photo.name)
            photo_count += 1
        print(f"   Copied {photo_count} photos")
    else:
        print(f"   Note: Photos directory not found: {photos_dir}")
        print(f"   Site will be generated without photos")

    # Generate summary
    print()
    print("=" * 50)
    print("Static site generation complete!")
    print()
    print("Summary:")
    print(f"  - {len(all_conversations)} conversations processed")
    print(f"  - {len(timeline)} timeline events")
    print(f"  - {overall_stats['project'].get('duration_days', 0)} days of plant care")
    print(f"  - ${overall_stats['conversations'].get('estimated_cost_usd', {}).get('total', 0):.2f} estimated total cost")
    print()
    print(f"Output directory: {output_dir}")
    print()
    print("View the site:")
    print(f"  - Open: {output_dir / 'index.html'}")
    print(f"  - Or serve: python -m http.server -d {output_dir} 8080")
    print()

    return 0


if __name__ == "__main__":
    exit(main())
