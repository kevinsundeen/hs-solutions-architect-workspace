#!/usr/bin/env python3
"""
Automated context update script for client folders.

This script monitors client folders and automatically updates context.md when:
- New transcripts are added to transcripts/ folder
- New deliverables are added to documents/deliverables/ folders
- Files are moved from draft/ to final/ in deliverables

Usage:
    python update-context.py [client-folder-path]
    
Or run from client folder:
    python ../../_meta/scripts/update-context.py .
"""

import os
import re
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional


def parse_transcript_filename(filename: str) -> Optional[Dict[str, str]]:
    """
    Parse transcript filename to extract date, client, and topic.
    Format: [YYYY-MM-DD]_[client-name]_[topic-keywords].txt
    """
    pattern = r'(\d{4}-\d{2}-\d{2})_([^_]+)_(.+)\.(txt|md)$'
    match = re.match(pattern, filename)
    if match:
        return {
            'date': match.group(1),
            'client': match.group(2),
            'topic': match.group(3).replace('-', ' ').title()
        }
    return None


def extract_transcript_summary(filepath: Path) -> Optional[str]:
    """Extract summary from transcript file if it exists."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read(2000)  # Read first 2000 chars
            # Look for summary section
            summary_match = re.search(r'##?\s*Summary[:\n]+(.+?)(?=\n\n|\n---|\n##)', content, re.DOTALL | re.IGNORECASE)
            if summary_match:
                return summary_match.group(1).strip()[:200]  # Limit to 200 chars
    except Exception:
        pass
    return None


def get_transcripts(transcripts_dir: Path) -> List[Dict[str, str]]:
    """Get all transcripts from transcripts directory."""
    transcripts = []
    if not transcripts_dir.exists():
        return transcripts
    
    for file in sorted(transcripts_dir.glob('*.txt'), reverse=True):
        parsed = parse_transcript_filename(file.name)
        if parsed:
            transcripts.append({
                **parsed,
                'filename': file.name,
                'summary': extract_transcript_summary(file)
            })
        else:
            # Fallback for non-standard names
            transcripts.append({
                'date': datetime.fromtimestamp(file.stat().st_mtime).strftime('%Y-%m-%d'),
                'client': 'unknown',  # Default; if your naming convention varies, keep this generic
                'topic': file.stem.replace('_', ' ').title(),
                'filename': file.name,
                'summary': None
            })
    
    return transcripts


def get_deliverables(deliverables_dir: Path) -> Dict[str, List[Dict[str, str]]]:
    """Get all deliverables, separated by draft/final."""
    deliverables = {'final': [], 'draft': []}
    
    final_dir = deliverables_dir / 'final'
    draft_dir = deliverables_dir / 'draft'
    
    for status, dir_path in [('final', final_dir), ('draft', draft_dir)]:
        if dir_path.exists():
            for file in sorted(dir_path.glob('*'), reverse=True):
                if file.is_file() and not file.name.startswith('.') and not file.name.lower().startswith('readme'):
                    mtime = datetime.fromtimestamp(file.stat().st_mtime)
                    deliverables[status].append({
                        'name': file.stem,
                        'filename': file.name,
                        'date': mtime.strftime('%Y-%m-%d'),
                        'path': f'documents/deliverables/{status}/{file.name}'
                    })
    
    return deliverables


def update_transcript_index(transcripts_dir: Path, transcripts: List[Dict[str, str]]):
    """Create or update transcript index file."""
    index_path = transcripts_dir / 'transcript-index.md'
    
    content = ["# Transcript Index\n"]
    content.append(f"*Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n\n")
    content.append("| Date | Topic | File |\n")
    content.append("|------|-------|------|\n")
    
    for t in transcripts:
        topic = t['topic']
        content.append(f"| {t['date']} | {topic} | `{t['filename']}` |\n")
    
    index_path.write_text(''.join(content), encoding='utf-8')


def update_context_file(context_path: Path, transcripts: List[Dict[str, str]], deliverables: Dict[str, List[Dict[str, str]]]):
    """Update context.md with latest transcripts and deliverables."""
    if not context_path.exists():
        print(f"Warning: context.md not found at {context_path}")
        return
    
    content = context_path.read_text(encoding='utf-8')
    
    # Update last updated date
    content = re.sub(
        r'\*Last Updated: .+\*',
        f'*Last Updated: {datetime.now().strftime("%Y-%m-%d")}*',
        content
    )
    
    # Update Recent Transcripts section
    recent_transcripts_section = "## Transcripts\n\nSee `transcripts/transcript-index.md` for full list of transcripts.\n\n**Recent Transcripts:**\n"
    for t in transcripts[:5]:  # Last 5 transcripts
        topic = t['topic']
        recent_transcripts_section += f"- {t['date']} - {topic} - `transcripts/{t['filename']}`\n"
    
    # Replace transcripts section
    content = re.sub(
        r'## Transcripts.*?(?=\n## |\Z)',
        recent_transcripts_section,
        content,
        flags=re.DOTALL
    )
    
    # Update Work Delivered section
    work_delivered_pattern = r'(## Work Delivered\n)'
    if re.search(work_delivered_pattern, content):
        work_delivered_section = "## Work Delivered\n\n"
        
        # Add final deliverables
        for d in deliverables['final'][:10]:  # Last 10 final deliverables
            work_delivered_section += f"### {d['date']} - {d['name']}\n"
            work_delivered_section += f"- **Status:** Completed\n"
            work_delivered_section += f"- **Description:** [To be updated manually]\n"
            work_delivered_section += f"- **Location:** `{d['path']}`\n\n"
        
        # Add draft deliverables
        if deliverables['draft']:
            work_delivered_section += "### Draft Deliverables (Work in Progress)\n\n"
            for d in deliverables['draft'][:5]:  # Last 5 draft deliverables
                work_delivered_section += f"- {d['date']} - {d['name']} - `{d['path']}`\n"
            work_delivered_section += "\n"
        
        # Replace work delivered section (keep existing entries if they exist)
        # This is a simple approach - could be enhanced to merge with existing entries
        content = re.sub(
            r'## Work Delivered\n.*?(?=\n## |\Z)',
            work_delivered_section,
            content,
            flags=re.DOTALL
        )
    
    context_path.write_text(content, encoding='utf-8')
    print(f"✓ Updated {context_path}")


def main():
    """Main function to update context for a client folder."""
    if len(sys.argv) > 1:
        client_folder = Path(sys.argv[1]).resolve()
    else:
        client_folder = Path.cwd()
    
    if not (client_folder / 'context.md').exists():
        print(f"Error: context.md not found in {client_folder}")
        print("Usage: python update-context.py [client-folder-path]")
        sys.exit(1)
    
    print(f"Updating context for: {client_folder.name}")
    
    transcripts_dir = client_folder / 'transcripts'
    deliverables_dir = client_folder / 'documents' / 'deliverables'
    context_path = client_folder / 'context.md'
    
    # Get transcripts
    transcripts = get_transcripts(transcripts_dir)
    print(f"  Found {len(transcripts)} transcripts")
    
    # Get deliverables
    deliverables = get_deliverables(deliverables_dir)
    print(f"  Found {len(deliverables['final'])} final deliverables, {len(deliverables['draft'])} draft deliverables")
    
    # Update transcript index
    if transcripts:
        update_transcript_index(transcripts_dir, transcripts)
        print(f"  ✓ Updated transcript index")
    
    # Update context.md
    update_context_file(context_path, transcripts, deliverables)
    
    print("Done!")


if __name__ == '__main__':
    main()

