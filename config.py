import os
import sys
from pathlib import Path

# Paths
BASE_DIR = Path("/root/YT_PursuingAi")
REPO_DIR = BASE_DIR
CATALOG_FILE = BASE_DIR / "catalog.json"
STATE_FILE = BASE_DIR / "state.json"
WORK_DIR = Path("/tmp/yt_pursuingai_work")
SCREENSHOTS_DIR = BASE_DIR / "screenshots"
LOG_FILE = Path("/var/log/yt_pursuingai.log")

# Channel Information
CHANNEL_ID = "UC3P0rlhvB3IFda41lb77EHg"
CHANNEL_NAME = "Pursuing AI"
CHANNEL_HANDLE = "@PursuingAi"
CHANNEL_URL = "https://www.youtube.com/@PursuingAi"
RSS_FEED_URL = f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}"
CHANNEL_DOMAIN = "Intelligence Artificielle, LLM, Agentic AI, TypeSafe, Jev, System One, Benchmarks, Coding Agents, IA locale"

# Models
GEMINI_MODEL = "gemini-3.5-flash-lite"
WHISPER_MODEL = "large-v3-turbo"
MODEL_SIGNATURE = f"whisper-v3-large-turbo+{GEMINI_MODEL}"

# API Keys & Network
GEMINI_KEYS_FILE = BASE_DIR / ".gemini_keys"
PROXY = "socks5://127.0.0.1:4001"
PLAYER_CLIENT = "android"

# Processing parameters
BATCH_SIZE = 7
MAX_BLOCK_DURATION = 32.0
MIN_BLOCK_DURATION = 18.0
FRAME_DIFF_THRESHOLD = 15.0
FRAME_MAX_WIDTH = 1280

# Ensure directories exist
BASE_DIR.mkdir(parents=True, exist_ok=True)
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
WORK_DIR.mkdir(parents=True, exist_ok=True)
