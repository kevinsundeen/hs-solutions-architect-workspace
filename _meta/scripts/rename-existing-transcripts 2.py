#!/usr/bin/env python3
"""
One-time script to rename existing transcripts based on their content.
Extracts date and topic from transcript files and renames them.

Usage:
    python rename-existing-transcripts.py [client-folder-path]
"""

import os
import re
import sys
from pathlib import Path
from datetime import datetime

def extract_date_from_content(content: str, filename: str) -> str:
    """Extract date from transcript content."""
    content_preview = content[:2000]  # Check more content
    
    # Prefer explicit "Date: YYYY-MM-DD" line at start (e.g. Fathom-style transcripts)
    date_line = re.search(r'^Date:\s*(\d{4})-(\d{2})-(\d{2})', content_preview, re.IGNORECASE | re.MULTILINE)
    if date_line:
        y, m, d = date_line.group(1), date_line.group(2), date_line.group(3)
        if 1 <= int(m) <= 12 and 1 <= int(d) <= 31:
            return f"{y}-{m}-{d}"
    
    # Try patterns with year first
    date_patterns = [
        (r'(\w+)\s+(\d{1,2})[,\s]+(\d{4})', True),  # "February 11, 2026" or "Feb 11 2026"
        (r'(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})', False),  # "2/11/2026" or "02-11-26"
        (r'(\d{4})[/-](\d{2})[/-](\d{2})', False),  # "2026-02-11"
    ]
    
    for pattern, is_month_name in date_patterns:
        matches = re.findall(pattern, content_preview, re.IGNORECASE)
        for match in matches:
            try:
                if isinstance(match, tuple):
                    if is_month_name and len(match) == 3 and match[0].isalpha():
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
                        month = month_map.get(month_name.lower(), None)
                        if month:
                            return f"{year}-{month}-{day.zfill(2)}"
                    elif len(match) == 3:
                        parts = list(match)
                        if len(parts[0]) == 4:  # YYYY-MM-DD format
                            y, m, d = parts[0], parts[1].zfill(2), parts[2].zfill(2)
                            if 1 <= int(m) <= 12 and 1 <= int(d) <= 31:
                                return f"{y}-{m}-{d}"
                        else:  # MM-DD-YYYY or MM-DD-YY
                            month, day, year = parts
                            if len(year) == 2:
                                year = f"20{year}"
                            m, d = month.zfill(2), day.zfill(2)
                            if 1 <= int(m) <= 12 and 1 <= int(d) <= 31:
                                return f"{year}-{m}-{d}"
            except:
                continue
    
    # Try patterns without year (assume current year or infer from context)
    # Look for month name followed by day number
    month_day_pattern = r'\b(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\s+(\d{1,2})\b'
    matches = re.findall(month_day_pattern, content_preview, re.IGNORECASE)
    if matches:
        try:
            month_name, day = matches[0]  # Take first match
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
            month = month_map.get(month_name.lower(), None)
            if month:
                # Use current year, but if month is in future, use previous year
                month_num = int(month)
                current_month = datetime.now().month
                year = datetime.now().strftime('%Y')
                if month_num > current_month:
                    year = str(int(year) - 1)
                return f"{year}-{month}-{day.zfill(2)}"
        except:
            pass
    
    return None
    
    return None

def extract_topic_from_content(content: str) -> str:
    """Extract topic/keywords from transcript content."""
    content_lower = content.lower()[:2000]
    
    topic_keywords = {
        'weekly-sync': ['weekly', 'sync', 'standup', 'status update'],
        'cae-rep': ['cae', 'rep assignment', 'rep mapping', 'ccc'],
        'sdr-rep': ['sdr', 'salesforce id mapping', 'sales development'],
        'discovery': ['discovery', 'requirements', 'needs assessment'],
        'implementation': ['implementation', 'build', 'development', 'deploy'],
        'audit': ['audit', 'review', 'assessment', 'workflow audit'],
        'sync-errors': ['sync error', 'sync issue', 'data quality'],
        'integration': ['integration', 'api', 'connector'],
        'training': ['training', 'onboarding', 'enablement'],
        'demo': ['demo', 'demonstration', 'show'],
        'kickoff': ['kickoff', 'kick off', 'project start'],
        'sales-discovery': ['sales discovery', 'sales process'],
        'marketing-discovery': ['marketing discovery', 'marketing process'],
        'account-sync': ['account sync', 'account synchronization'],
    }
    
    topic_scores = {}
    for topic, keywords in topic_keywords.items():
        score = sum(1 for keyword in keywords if keyword in content_lower)
        if score > 0:
            topic_scores[topic] = score
    
    if topic_scores:
        return max(topic_scores.items(), key=lambda x: x[1])[0]
    
    return 'meeting'

def get_client_name_from_folder(folder_path: Path) -> str:
    """Extract client name from folder path."""
    folder_name = folder_path.name
    folder_name = re.sub(r'-new$', '', folder_name, flags=re.IGNORECASE)
    return folder_name.lower()

def process_transcript(filepath: Path, client_name: str) -> bool:
    """Process and rename a single transcript file."""
    try:
        content = filepath.read_text(encoding='utf-8', errors='ignore')
        
        # Always extract date from content
        content_date = extract_date_from_content(content, filepath.name)
        
        # Check if already properly named
        pattern = r'\d{4}-\d{2}-\d{2}_[^_]+_[^_]+\.(txt|md)$'
        if re.match(pattern, filepath.name):
            existing_date = re.search(r'(\d{4}-\d{2}-\d{2})', filepath.name)
            
            # If content date matches filename date, check topic
            if existing_date and content_date and existing_date.group(1) == content_date:
                # Extract topic and check if it matches
                topic = extract_topic_from_content(content)
                expected_name = f"{content_date}_{client_name}_{topic}.txt"
                if filepath.name == expected_name:
                    print(f"✓ {filepath.name} already correctly named")
                    return False
                # Topic doesn't match, rename it
                new_name = expected_name
            elif content_date:
                # Date doesn't match, use content date
                topic = extract_topic_from_content(content)
                new_name = f"{content_date}_{client_name}_{topic}.txt"
            else:
                # Can't extract date, keep existing
                print(f"⚠ Could not extract date from content in {filepath.name}, keeping as is")
                return False
        else:
            # Not properly named, extract both date and topic
            if not content_date:
                print(f"⚠ Could not extract date from {filepath.name}, skipping")
                return False
            topic = extract_topic_from_content(content)
            new_name = f"{content_date}_{client_name}_{topic}.txt"
        
        new_path = filepath.parent / new_name
        
        if filepath.name == new_name:
            print(f"✓ {filepath.name} already correctly named")
            return False
        
        # If target exists, add a number suffix
        counter = 1
        original_new_path = new_path
        while new_path.exists():
            new_name = f"{content_date}_{client_name}_{topic}-{counter}.txt"
            new_path = filepath.parent / new_name
            counter += 1
        
        filepath.rename(new_path)
        print(f"✓ Renamed: {filepath.name} → {new_path.name}")
        return True
    except Exception as e:
        print(f"✗ Error processing {filepath.name}: {e}")
        return False

def main():
    """Main function."""
    if len(sys.argv) > 1:
        client_folder = Path(sys.argv[1]).resolve()
    else:
        client_folder = Path.cwd()
    
    if not (client_folder / 'context.md').exists():
        print(f"Error: context.md not found in {client_folder}")
        print("Usage: python rename-existing-transcripts.py [client-folder-path]")
        sys.exit(1)
    
    transcripts_dir = client_folder / 'transcripts'
    if not transcripts_dir.exists():
        print(f"Error: transcripts folder not found: {transcripts_dir}")
        sys.exit(1)
    
    client_name = get_client_name_from_folder(client_folder)
    print(f"Processing transcripts in: {transcripts_dir}")
    print(f"Client name: {client_name}\n")
    
    # Process all .txt and .md files
    transcript_files = list(transcripts_dir.glob('*.txt')) + list(transcripts_dir.glob('*.md'))
    transcript_files = [f for f in transcript_files if f.name != 'transcript-index.md']
    
    if not transcript_files:
        print("No transcript files found.")
        return
    
    renamed_count = 0
    for file in sorted(transcript_files):
        if process_transcript(file, client_name):
            renamed_count += 1
    
    print(f"\n✓ Processed {len(transcript_files)} files, renamed {renamed_count}")
    
    # Update context
    try:
        import subprocess
        script_path = Path(__file__).parent / 'update-context.py'
        print("\nUpdating context.md...")
        subprocess.run([
            sys.executable, str(script_path), str(client_folder)
        ], check=False)
        print("✓ Context updated")
    except Exception as e:
        print(f"  (Context update failed: {e})")

if __name__ == '__main__':
    main()
