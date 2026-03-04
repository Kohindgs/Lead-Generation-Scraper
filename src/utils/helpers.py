"""
Shared utility helpers: delays, logging, proxy, user-agent rotation.
"""
import random
import time
import logging
import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.config import scraper_cfg

# ── Logging ─────────────────────────────────────────────────────────────────

LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)

        fmt = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # Console handler
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        ch.setFormatter(fmt)
        logger.addHandler(ch)

        # File handler (daily rotation)
        log_file = LOG_DIR / f"{datetime.now():%Y-%m-%d}.log"
        fh = logging.FileHandler(log_file)
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    return logger


# ── Random delay (human-like) ────────────────────────────────────────────────

def human_delay(min_s: Optional[float] = None, max_s: Optional[float] = None):
    """Sleep for a random human-like interval to avoid rate limiting."""
    lo = min_s if min_s is not None else scraper_cfg.delay_min
    hi = max_s if max_s is not None else scraper_cfg.delay_max
    wait = random.uniform(lo, hi)
    time.sleep(wait)


# ── User-Agent rotation ──────────────────────────────────────────────────────

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) "
    "Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3_1) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.3 Safari/605.1.15",
]


def random_user_agent() -> str:
    return random.choice(USER_AGENTS)


# ── ID generation ────────────────────────────────────────────────────────────

def generate_lead_id(source: str, identifier: str) -> str:
    raw = f"{source}:{identifier}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


# ── Text cleaning ────────────────────────────────────────────────────────────

def clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_domain(url: str) -> str:
    """Extract bare domain from a URL."""
    if not url:
        return ""
    url = re.sub(r"^https?://", "", url)
    url = re.sub(r"^www\.", "", url)
    return url.split("/")[0].lower()


def extract_email(text: str) -> Optional[str]:
    """Find first email address in a block of text."""
    match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text)
    return match.group(0).lower() if match else None


def extract_phone(text: str) -> Optional[str]:
    """Find first phone number in a block of text."""
    match = re.search(
        r"(?:\+?\d{1,3}[\s\-.]?)?\(?\d{3}\)?[\s\-.]?\d{3}[\s\-.]?\d{4}", text
    )
    return match.group(0) if match else None


# ── Proxy helper ─────────────────────────────────────────────────────────────

def build_proxy_dict() -> Optional[dict]:
    from src.config import scraper_cfg
    if not scraper_cfg.use_proxy:
        return None
    auth = ""
    if scraper_cfg.proxy_user:
        auth = f"{scraper_cfg.proxy_user}:{scraper_cfg.proxy_pass}@"
    proxy_url = f"http://{auth}{scraper_cfg.proxy_host}:{scraper_cfg.proxy_port}"
    return {"http": proxy_url, "https": proxy_url}
