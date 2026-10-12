#!/usr/bin/env python3
"""
Automatic transcript renamer - watches for new files in client transcripts folders
and automatically renames them according to the convention: [date]_[client]_[topic].txt

Usage:
    python auto-rename-transcripts.py [client-folder-path]
    
Or run from client folder:
    python ../../_meta/scripts/auto-rename-transcripts.py .
"""

import logging
import os
import re
import sys
import time
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional

logger = logging.getLogger("s2.transcript_watch")


def _load_env(repo_root: Path) -> None:
    """Load .env from repo root so OPENAI_API_KEY, OPENAI_MODEL are set."""
    for name in (".env", "env"):
        env_file = repo_root / name
        if not env_file.is_file():
            continue
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip("'\"")
            if key and key not in os.environ:
                os.environ[key] = value
        return

def extract_date_from_content(content: str, filename: str) -> str:
    """Extract date from transcript content."""
    # Try to find date in content (common patterns)
    date_patterns = [
        r'(\w+)\s+(\d{1,2})[,\s]+(\d{4})',        # "February 9, 2026" or "Feb 9 2026"
        r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})',     # "2026-02-09" or "2026-2-9"
        r'(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})',   # "2/9/2026" or "02-09-26"
    ]
    
    # Check first 1000 chars for date
    content_preview = content[:1000]
    
    for pattern in date_patterns:
        matches = re.findall(pattern, content_preview)
        for match in matches:
            try:
                if isinstance(match, tuple):
                    # Handle "February 9, 2026" format
                    if len(match) == 3 and match[0].isalpha():
                        month_name, day, year = match
                        month_map = {
                            'january': '01', 'jan': '01',
                            'february': '02', 'feb': '02',
                            'march': '03', 'mar': '03',
                            'april': '04', 'apr': '04',
                            'may': '05',
                            'june': '06', 'jun': '06',
                            'july': '07', 'jul': '07',
                            'august': '08', 'aug': '08',
                            'september': '09', 'sep': '09', 'sept': '09',
                            'october': '10', 'oct': '10',
                            'november': '11', 'nov': '11',
                            'december': '12', 'dec': '12'
                        }
                        month = month_map.get(month_name.lower(), '01')
                        return f"{year}-{month}-{day.zfill(2)}"
                    # Handle numeric dates
                    elif len(match) == 3:
                        parts = list(match)
                        if len(parts[0]) == 4:  # YYYY-MM-DD
                            year, month, day = parts
                            return f"{year}-{str(month).zfill(2)}-{str(day).zfill(2)}"
                        else:  # MM-DD-YYYY or MM-DD-YY (or DD-MM-YYYY/YY)
                            month, day, year = parts
                            # Basic sanity check to avoid impossible dates like "26-03-05" → 2005-26-03
                            try:
                                m_int = int(month)
                                d_int = int(day)
                                if not (1 <= m_int <= 12 and 1 <= d_int <= 31):
                                    continue
                            except ValueError:
                                continue
                            if len(year) == 2:
                                year = f"20{year}"
                            return f"{year}-{str(month).zfill(2)}-{str(day).zfill(2)}"
            except:
                continue
    
    # Fallback: use file modification date
    return datetime.now().strftime('%Y-%m-%d')

def extract_topic_from_content(content: str) -> str:
    """Extract topic/keywords from transcript content."""
    content_lower = content.lower()[:2000]  # Check first 2000 chars
    
    # Common topic patterns
    topic_keywords = {
        'weekly-sync': ['weekly', 'sync', 'standup', 'status update'],
        'cae-rep': ['cae', 'rep assignment', 'rep mapping', 'ccc'],
        'sdr-rep': ['sdr', 'sales development'],
        'discovery': ['discovery', 'requirements', 'needs assessment'],
        'implementation': ['implementation', 'build', 'development', 'deploy'],
        'audit': ['audit', 'review', 'assessment'],
        'sync-errors': ['sync error', 'sync issue', 'data quality'],
        'integration': ['integration', 'api', 'connector'],
        'training': ['training', 'onboarding', 'enablement'],
        'demo': ['demo', 'demonstration', 'show'],
    }
    
    # Score each topic based on keyword matches
    topic_scores = {}
    for topic, keywords in topic_keywords.items():
        score = sum(1 for keyword in keywords if keyword in content_lower)
        if score > 0:
            topic_scores[topic] = score
    
    if topic_scores:
        # Return topic with highest score
        return max(topic_scores.items(), key=lambda x: x[1])[0]
    
    # Default fallback
    return 'meeting'

def get_client_name_from_folder(folder_path: Path) -> str:
    """Extract client name from folder path."""
    # Client folder name should be the client name
    folder_name = folder_path.name
    # Remove common suffixes like "-New"
    folder_name = re.sub(r'-new$', '', folder_name, flags=re.IGNORECASE)
    return folder_name.lower()

def is_generic_filename(filename: str, client_name: str) -> bool:
    """Heuristic: decide if a filename looks generic (safe to rename)."""
    name = filename.lower()
    # Strip extension
    if '.' in name:
        name = name.rsplit('.', 1)[0]

    # If it already looks like our convention with a topic, treat as non-generic
    if re.match(r'\d{4}-\d{2}-\d{2}_[^_]+_[^_]+$', name):
        return False

    # If it already contains the client name and some descriptive words, treat as non-generic
    descriptive_keywords = [
        'workshop',
        'discovery',
        'kickoff',
        'training',
        'implementation',
        'weekly',
        'sync',
        'audit',
        'roadmap',
        'service',
        'marketing',
        'sales',
        'integration',
        'warranty',
        'ticket',
    ]
    if client_name.lower() in name:
        if any(word in name for word in descriptive_keywords):
            return False

    # Common "generic" transcript/recording style names
    generic_substrings = [
        'recording',
        'transcript',
        'meeting',
        'zoom',
        'teams meeting',
        'webex',
        'otter',
    ]
    if any(sub in name for sub in generic_substrings):
        return True

    # Very short or mostly numeric names are probably generic (e.g. GMT timestamps)
    compact = re.sub(r'[^a-z0-9]', '', name)
    if len(compact) < 10 or compact.isdigit():
        return True

    # Default: treat as already "good enough", do not rename
    return False


def generate_topic_with_ai(summary_text: str) -> Optional[str]:
    """
    Use OpenAI (OPENAI_API_KEY, OPENAI_MODEL) to suggest a short kebab-case topic
    from the transcript preview. Returns None if no key or on error.
    """
    if not summary_text.strip():
        return None
    script_dir = Path(__file__).resolve().parent
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))
    try:
        import llm_helper
        from prompts_loader import get_prompt
    except ImportError:
        return None
    instruction = (
        get_prompt("transcript-topic").strip()
        or "Based on this transcript preview, output ONLY a short filename-safe topic in 2-6 words, kebab-case. Examples: 360-workshop-service, discovery-kickoff, weekly-sync. No other text, no quotes."
    )
    reply = llm_helper.summarize(summary_text[:3000], instruction, max_tokens=80)
    if not reply:
        return None
    # Normalize to kebab-case: lowercase, non-alphanumeric -> hyphen, collapse/strip
    topic = reply.strip().lower()
    topic = re.sub(r"[^a-z0-9]+", "-", topic)
    topic = re.sub(r"-+", "-", topic).strip("-")
    if not topic or len(topic) > 60:
        return None
    return topic or None


def rename_transcript(filepath: Path, client_name: str) -> Optional[Path]:
    """Rename a transcript file according to convention."""
    try:
        content = filepath.read_text(encoding='utf-8', errors='ignore')

        date = extract_date_from_content(content, filepath.name)
        # Use simple heuristic topic first
        topic = extract_topic_from_content(content)

        # Give an AI-based namer a chance to refine the topic based on a "summary"
        ai_topic = generate_topic_with_ai(content[:3000])
        if ai_topic:
            topic = ai_topic

        new_name = f"{date}_{client_name}_{topic}.txt"
        new_path = filepath.parent / new_name

        # Don't rename if it already follows the convention
        if filepath.name == new_name:
            return filepath

        # If target exists, add a number suffix
        counter = 1
        while new_path.exists():
            new_name = f"{date}_{client_name}_{topic}-{counter}.txt"
            new_path = filepath.parent / new_name
            counter += 1

        filepath.rename(new_path)
        print(f"✓ Renamed: {filepath.name} → {new_name}")
        return new_path
    except Exception as e:
        print(f"✗ Error renaming {filepath.name}: {e}")
        return None


def maybe_run_call_coach(transcript_path: Path) -> None:
    """
    Optional: run facilitation coach on newly filed client transcript.

    Enabled when S2_CALL_COACH_ON_WATCH=1 (or true/yes).
    Requires OPENAI_API_KEY or ANTHROPIC_API_KEY in env.
    """
    flag = os.environ.get("S2_CALL_COACH_ON_WATCH", "").strip().lower()
    path_display = transcript_path.resolve()
    logger.debug("Coach hook: evaluating %s", path_display)
    logger.debug(
        "S2_CALL_COACH_ON_WATCH=%r OPENAI_API_KEY=%s ANTHROPIC_API_KEY=%s",
        os.environ.get("S2_CALL_COACH_ON_WATCH", ""),
        "set" if os.environ.get("OPENAI_API_KEY") else "unset",
        "set" if os.environ.get("ANTHROPIC_API_KEY") else "unset",
    )
    if flag not in ("1", "true", "yes", "y", "on"):
        logger.debug(
            "Coach skipped: S2_CALL_COACH_ON_WATCH not enabled "
            "(set to 1/true/yes to run after new transcripts)"
        )
        return
    if not (
        os.environ.get("OPENAI_API_KEY")
        or os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("S2_ANTHROPIC_API_KEY")
    ):
        msg = "Coach skipped: no OPENAI_API_KEY / ANTHROPIC_API_KEY / S2_ANTHROPIC_API_KEY set"
        logger.warning("%s (file=%s)", msg, path_display)
        print(f"  ({msg})")
        return

    script_dir = Path(__file__).resolve().parent
    coach_script = script_dir / "fathom-call-coach.py"
    if not coach_script.is_file():
        msg = "Coach skipped: fathom-call-coach.py not found"
        logger.error("%s at %s", msg, coach_script)
        print(f"  ({msg})")
        return

    cmd = [sys.executable, str(coach_script), str(path_display)]
    logger.info("Running call coach for %s", path_display)
    logger.info("Command: %s", " ".join(cmd))
    try:
        # No capture_output — coach script output goes to the terminal
        proc = subprocess.run(cmd, check=False)
        logger.info("Coach subprocess finished rc=%s", proc.returncode)
        if proc.returncode != 0:
            logger.warning("Coach exited with non-zero status")
    except Exception as e:
        logger.exception("Coach failed: %s", e)
        print(f"  (Coach failed: {e})")


def watch_and_rename(client_folder: Path):
    """Watch transcripts folder and auto-rename new files."""
    transcripts_dir = client_folder / 'transcripts'
    
    if not transcripts_dir.exists():
        print(f"Error: transcripts folder not found: {transcripts_dir}")
        return
    
    client_name = get_client_name_from_folder(client_folder)
    logger.info(
        "Watch started client_folder=%s transcripts_dir=%s client_name=%s",
        client_folder.resolve(),
        transcripts_dir.resolve(),
        client_name,
    )
    print(f"Watching {transcripts_dir} for new transcripts...")
    print(f"Client name: {client_name}")
    print("Drag transcript files here and they will be automatically renamed.")
    print("Press Ctrl+C to stop.\n")
    
    # Get initial set of files
    existing_files = set(transcripts_dir.glob('*.txt'))
    existing_files.update(transcripts_dir.glob('*.md'))
    logger.debug("Initial transcript count: %s", len(existing_files))
    
    try:
        while True:
            # Check for new files
            current_files = set(transcripts_dir.glob('*.txt'))
            current_files.update(transcripts_dir.glob('*.md'))
            
            new_files = current_files - existing_files
            if new_files:
                logger.debug(
                    "Poll: %s total files, %s new this tick: %s",
                    len(current_files),
                    len(new_files),
                    sorted(p.name for p in new_files),
                )

            for new_file in new_files:
                # Wait a moment for file to be fully written
                time.sleep(0.5)

                logger.info("New transcript file detected: %s", new_file.resolve())

                # Check if file follows convention already
                pattern = r'\d{4}-\d{2}-\d{2}_[^_]+_[^_]+\.(txt|md)$'
                final_path: Optional[Path] = None

                if re.match(pattern, new_file.name):
                    print(f"✓ {new_file.name} already follows convention")
                    logger.info(
                        "Rename skipped: filename matches strict convention pattern"
                    )
                    final_path = new_file
                elif not is_generic_filename(new_file.name, client_name):
                    print(f"• Skipping rename for {new_file.name} (already looks descriptive)")
                    logger.info(
                        "Rename skipped: is_generic_filename=False (descriptive name)"
                    )
                    final_path = new_file
                else:
                    renamed = rename_transcript(new_file, client_name)
                    if renamed:
                        final_path = renamed
                        try:
                            script_path = Path(__file__).parent / 'update-context.py'
                            subprocess.run([
                                sys.executable, str(script_path), str(client_folder)
                            ], check=False)
                            print(f"✓ Updated context.md")
                            logger.info("Ran update-context.py for %s", client_folder)
                        except Exception as e:
                            print(f"  (Context update failed: {e})")
                            logger.warning("Context update failed: %s", e)
                    else:
                        logger.warning(
                            "rename_transcript returned None for %s; not running coach",
                            new_file.name,
                        )

                if final_path is not None:
                    maybe_run_call_coach(final_path)
            
            existing_files = current_files
            time.sleep(1)  # Check every second
            
    except KeyboardInterrupt:
        logger.info("Watch stopped (KeyboardInterrupt)")
        print("\n\nStopped watching.")

def main():
    """Main function."""
    if len(sys.argv) > 1:
        client_folder = Path(sys.argv[1]).resolve()
    else:
        client_folder = Path.cwd()

    if not (client_folder / "context.md").exists():
        print(f"Error: context.md not found in {client_folder}")
        print("Usage: python auto-rename-transcripts.py [client-folder-path]")
        sys.exit(1)

    repo_root = client_folder.parent
    _load_env(repo_root)

    log_level_name = (
        os.environ.get("S2_WATCH_LOG_LEVEL", "INFO").strip().upper() or "INFO"
    )
    level = getattr(logging, log_level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger.debug("Log level %s (override with S2_WATCH_LOG_LEVEL=DEBUG)", log_level_name)

    watch_and_rename(client_folder)

if __name__ == '__main__':
    main()
