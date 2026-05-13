#!/usr/bin/env python3
"""
GTT Discord → Matrix Import Script
Chunked import with retry logic and progress tracking.

Usage:
    python import.py [--resume]

    --resume: Skip channels that already have messages imported
              (reads from import-progress.json)
"""

import json
import os
import sys
import time
import uuid
import requests
from pathlib import Path
from datetime import datetime

# --- Config ---
SYNAPSE_URL = "http://localhost:8008"
ADMIN_USER = "gttadmin"
ADMIN_PASSWORD = "gttadmin123"
EXPORTS_DIR = Path("C:/Users/colin/Documents/Merly/gtt-exports/latest")
SPACE_NAME = "Goju Tech Talk Archive"
SPACE_ALIAS = "gtt-archive"
PROGRESS_FILE = Path("import-progress.json")

# Tuning — smaller batches, longer delays to avoid hanging
BATCH_SIZE = 20
BATCH_DELAY = 0.5   # seconds between batches
RETRY_DELAY = 2.0   # seconds before retrying a failed message
MAX_RETRIES = 3


def login():
    """Register admin if needed, then login."""
    # Try login first
    resp = requests.post(f"{SYNAPSE_URL}/_matrix/client/v3/login", json={
        "type": "m.login.password",
        "user": ADMIN_USER,
        "password": ADMIN_PASSWORD
    }, timeout=10)

    if resp.status_code == 403:
        # Try registering
        requests.post(f"{SYNAPSE_URL}/_matrix/client/v3/register", json={
            "username": ADMIN_USER,
            "password": ADMIN_PASSWORD,
            "auth": {"type": "m.login.dummy"}
        }, timeout=10)
        resp = requests.post(f"{SYNAPSE_URL}/_matrix/client/v3/login", json={
            "type": "m.login.password",
            "user": ADMIN_USER,
            "password": ADMIN_PASSWORD
        }, timeout=10)

    resp.raise_for_status()
    token = resp.json()["access_token"]
    print(f"✓ Logged in as @{ADMIN_USER}:gtt.local")
    return token


def headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def get_or_create_space(token):
    """Get existing space or create new one."""
    alias_encoded = f"%23{SPACE_ALIAS}%3Agtt.local"
    resp = requests.get(
        f"{SYNAPSE_URL}/_matrix/client/v3/directory/room/{alias_encoded}",
        headers=headers(token), timeout=10
    )
    if resp.status_code == 200:
        space_id = resp.json()["room_id"]
        print(f"✓ Using existing space: {space_id}")
        return space_id

    resp = requests.post(
        f"{SYNAPSE_URL}/_matrix/client/v3/createRoom",
        headers=headers(token),
        json={
            "name": SPACE_NAME,
            "room_alias_name": SPACE_ALIAS,
            "topic": "Goju Tech Talk Discord Archive",
            "creation_content": {"type": "m.space"},
            "preset": "public_chat"
        }, timeout=10
    )
    resp.raise_for_status()
    space_id = resp.json()["room_id"]
    print(f"✓ Created space: {space_id}")
    return space_id


def get_or_create_room(token, channel_name):
    """Get existing room or create new one."""
    alias = channel_name.lower()
    alias = "".join(c if c.isalnum() or c == "-" else "-" for c in alias).strip("-")[:50]
    full_alias = f"gtt-{alias}"
    alias_encoded = f"%23{full_alias}%3Agtt.local"

    resp = requests.get(
        f"{SYNAPSE_URL}/_matrix/client/v3/directory/room/{alias_encoded}",
        headers=headers(token), timeout=10
    )
    if resp.status_code == 200:
        return resp.json()["room_id"], full_alias

    resp = requests.post(
        f"{SYNAPSE_URL}/_matrix/client/v3/createRoom",
        headers=headers(token),
        json={
            "name": f"#{channel_name}",
            "room_alias_name": full_alias,
            "topic": f"Discord #{channel_name} archive",
            "preset": "public_chat"
        }, timeout=10
    )
    resp.raise_for_status()
    return resp.json()["room_id"], full_alias


def add_to_space(token, space_id, room_id):
    requests.put(
        f"{SYNAPSE_URL}/_matrix/client/v3/rooms/{space_id}/state/m.space.child/{room_id}",
        headers=headers(token),
        json={"via": ["gtt.local"], "suggested": False},
        timeout=10
    )


def send_message(token, room_id, text, ts_ms, retries=MAX_RETRIES):
    """Send one message with unique transaction ID and retry logic."""
    txn_id = str(uuid.uuid4()).replace("-", "")
    for attempt in range(retries):
        try:
            resp = requests.put(
                f"{SYNAPSE_URL}/_matrix/client/v3/rooms/{room_id}/send/m.room.message/{txn_id}",
                headers=headers(token),
                params={"ts": ts_ms},
                json={"msgtype": "m.text", "body": text},
                timeout=15
            )
            if resp.status_code == 200:
                return True
            elif resp.status_code == 429:
                # Rate limited — wait and retry
                retry_after = resp.json().get("retry_after_ms", 2000) / 1000
                time.sleep(retry_after)
                txn_id = str(uuid.uuid4()).replace("-", "")
            else:
                time.sleep(RETRY_DELAY)
                txn_id = str(uuid.uuid4()).replace("-", "")
        except requests.exceptions.Timeout:
            time.sleep(RETRY_DELAY * (attempt + 1))
        except Exception as e:
            time.sleep(RETRY_DELAY)
    return False


def format_message(msg):
    """Format a Discord message for Matrix."""
    content = msg.get("content", "") or ""
    author = msg.get("author", "Unknown")
    timestamp = msg.get("timestamp", "")
    attachments = msg.get("attachments", [])
    reactions = msg.get("reactions", {})
    reply_to = msg.get("reply_to_id")

    parts = [f"[{author}]"]

    if reply_to:
        parts.append(f"↩ reply")

    if content:
        parts.append(content)

    for att in attachments:
        fname = att.get("filename", "file") if isinstance(att, dict) else str(att)
        url = att.get("url", "") if isinstance(att, dict) else ""
        parts.append(f"📎 {fname}" + (f": {url}" if url else ""))

    if reactions:
        rxn_str = " ".join(f"{e}({len(u)})" for e, u in reactions.items())
        parts.append(f"[{rxn_str}]")

    return " ".join(parts)


def parse_ts(timestamp):
    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000)
    except Exception:
        return int(time.time() * 1000)


def load_progress():
    if PROGRESS_FILE.exists():
        return json.loads(PROGRESS_FILE.read_text())
    return {}


def save_progress(progress):
    PROGRESS_FILE.write_text(json.dumps(progress, indent=2))


def import_channel(token, room_id, json_file, start_index=0):
    """Import messages from a channel JSON file, starting at start_index."""
    with open(json_file, encoding="utf-8") as f:
        messages = json.load(f)

    total = len(messages)
    remaining = messages[start_index:]

    if not remaining:
        return total, total

    print(f"  {total} messages ({start_index} already done, importing {len(remaining)} remaining)")

    success = start_index
    batch_num = 0

    for i in range(0, len(remaining), BATCH_SIZE):
        batch = remaining[i:i + BATCH_SIZE]
        batch_success = 0

        for msg in batch:
            text = format_message(msg)
            ts_ms = parse_ts(msg.get("timestamp", ""))
            if send_message(token, room_id, text, ts_ms):
                success += 1
                batch_success += 1

        batch_num += 1
        pct = int((success / total) * 100)
        print(f"  Batch {batch_num}: {success}/{total} ({pct}%)", end="\r", flush=True)
        time.sleep(BATCH_DELAY)

    print(f"  ✓ {success}/{total} messages imported        ")
    return success, total


def main():
    resume = "--resume" in sys.argv
    print("GTT Discord → Matrix Import")
    print("=" * 40)
    if resume:
        print("Mode: RESUME (skipping completed channels)")

    # Check Synapse
    try:
        requests.get(f"{SYNAPSE_URL}/_matrix/client/versions", timeout=5).raise_for_status()
        print(f"✓ Synapse running at {SYNAPSE_URL}")
    except Exception:
        print(f"✗ Cannot reach Synapse at {SYNAPSE_URL}")
        return

    token = login()
    space_id = get_or_create_space(token)
    progress = load_progress()

    json_files = sorted([f for f in EXPORTS_DIR.glob("*.json") if not f.name.startswith("members")])
    print(f"\nFound {len(json_files)} channel exports\n")

    total_msgs = 0
    total_rooms = 0

    for idx, json_file in enumerate(json_files):
        channel_name = json_file.stem
        prog_key = channel_name

        # Skip if complete and resuming
        if resume and progress.get(prog_key, {}).get("complete"):
            count = progress[prog_key]["count"]
            print(f"[{idx+1}/{len(json_files)}] #{channel_name} — skipped (already done, {count} msgs)")
            total_msgs += count
            total_rooms += 1
            continue

        print(f"\n[{idx+1}/{len(json_files)}] #{channel_name}")

        try:
            room_id, alias = get_or_create_room(token, channel_name)
            add_to_space(token, space_id, room_id)

            start_index = progress.get(prog_key, {}).get("imported", 0)
            success, total = import_channel(token, room_id, json_file, start_index)

            progress[prog_key] = {
                "room_id": room_id,
                "imported": success,
                "count": total,
                "complete": success >= total
            }
            save_progress(progress)

            total_msgs += success
            total_rooms += 1

        except KeyboardInterrupt:
            print("\n\nInterrupted — progress saved. Run with --resume to continue.")
            save_progress(progress)
            return
        except Exception as e:
            print(f"  ✗ Error: {e}")
            save_progress(progress)

    print(f"\n{'=' * 40}")
    print(f"Import complete!")
    print(f"  Rooms: {total_rooms}")
    print(f"  Messages: {total_msgs:,}")
    print(f"\nOpen Element: http://localhost:3000")
    print(f"Login: @{ADMIN_USER}:gtt.local / {ADMIN_PASSWORD}")


if __name__ == "__main__":
    main()