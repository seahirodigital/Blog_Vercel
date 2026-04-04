import os
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

NOTE_STORAGE_STATE = os.getenv("NOTE_STORAGE_STATE", "")
SCRIPT_DIR = Path(__file__).parent.parent / "scripts" / "pipeline"
LOCAL_STATE_FILE = SCRIPT_DIR / "note_storage_state.json"

def _get_storage_state_path():
    if LOCAL_STATE_FILE.exists():
        return str(LOCAL_STATE_FILE)
    return None

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    state_path = _get_storage_state_path()
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        storage_state=state_path
    )
    page = context.new_page()
    page.goto("https://editor.note.com/notes/n826b038d22a5/edit/")
    print("⏳ Waiting for content to load...")
    time.sleep(15) # Wait for SPA
    
    # Dump HTML to a file
    html = page.content()
    Path("dump.html").write_text(html, encoding="utf-8")
    
    # Save a screenshot to visually see the page state
    page.screenshot(path="screenshot.png")
    
    print("✅ Dumped to dump.html and screenshot.png")
    browser.close()
