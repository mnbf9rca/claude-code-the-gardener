#\!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Static site generator for Claude the Gardener.
Parses all data and generates an interactive HTML site.
"""

import json
import shutil
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape

# Import our parsers
from parsers import stats, conversations, sensors, actions


def main():
    """Main generator function."""

    # Configuration
    project_root = Path(__file__).parent.parent
    data_dir = project_root / "app" / "data"
    photos_dir = project_root / "app" / "photos"
    templates_dir = Path(__file__).parent / "templates"
    static_dir = Path(__file__).parent / "static"
    output_dir = Path(__file__).parent / "output"

    print("Claude the Gardener - Static Site Generator")
    print("=" * 50)
    print()

    # Validate paths
    if not data_dir.exists():
        print(f"Error: Data directory not found: {data_dir}")
        print("   Run ./static_site_generator/sync_data.sh first\!")
        return 1

    # Create output directories
    print("Creating output directories...")
    output_dir.mkdir(exist_ok=True)
    (output_dir / "conversations").mkdir(exist_ok=True)
    (output_dir / "photos").mkdir(exist_ok=True)
    (output_dir / "static").mkdir(exist_ok=True)
    (output_dir / "data").mkdir(exist_ok=True)

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
    all_conversations = conversations.get_all_conversations(data_dir)
    conversation_highlights = conversations.get_highlights(all_conversations)
    print(f"    Found {len(all_conversations)} conversations ({len(conversation_highlights)} highlights)")

    print("  - Processing sensor data...")
    sensor_data = sensors.get_combined_sensor_data(data_dir)
    sensor_summary = sensors.get_sensor_summary(data_dir)
    print(f"    Moisture: {len(sensor_data['moisture'])} readings")
    print(f"    Light: {len(sensor_data['light'])} sessions")
    print(f"    Water: {len(sensor_data['water'])} events")

    print("  - Building timeline...")
    timeline = actions.get_unified_timeline(data_dir)
    timeline_highlights = actions.detect_highlights(timeline)
    print(f"    {len(timeline)} events ({len(timeline_highlights)} highlights)")

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

    # Generate summary
    print()
    print("=" * 50)
    print("Static site generation complete\!")
    print()
    print(f"Summary:")
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
