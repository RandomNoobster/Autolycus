"""Dump the Politics & War Fandom wiki's mechanics articles to fandom_data.jsonl.

Reads the wiki through its MediaWiki API. The rendered wiki pages sit behind a
Cloudflare bot challenge, which this script does not try to get past; the API is
the route Fandom provides for bots. Any block ends the run and keeps the
previous dump (see scripts/scrape_guard.py).
"""
import json
import logging
import os
import sys
import time
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md
from tqdm import tqdm
from core.logging_config import setup_logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scrape_guard import BotBlockedError, check_response, partial_path, publish  # noqa: E402

# --- CONFIGURATION ---
WIKI_URL = "https://politicsandwar.fandom.com"
API_URL = f"{WIKI_URL}/api.php"
ROOT_CATEGORY = "Category:Mechanics"

# Save files in the same folder as the script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "fandom_data.jsonl")

DELAY = 1.0
HEADERS = {
    'User-Agent': 'PnWMechanicsBot/1.0 (+http://politicsandwar.fandom.com)'
}
# Root subcategories that list nations or alliances rather than game mechanics.
SKIP_SUBCATEGORY_WORDS = ("alliances in", "nations in", "browse")
GARBAGE_CLASSES = ['toc', 'category-links', 'mw-editsection', 'navbox']

# --- LOGGING SETUP ---
setup_logging(process_name="fandom_scraper", level=os.getenv("LOG_LEVEL", "INFO"))


class FandomMainCrawler:
    def __init__(self, root_category, output_file):
        self.root_category = root_category
        self.output_file = output_file
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def api(self, **params):
        """One MediaWiki API call, then the politeness delay. None on a non-block failure."""
        params.update(format="json", formatversion="2", maxlag="5")
        for attempt in range(3):
            try:
                response = self.session.get(API_URL, params=params, timeout=30)
            except requests.RequestException as e:
                logging.warning(f"API attempt {attempt + 1} failed for {params}: {e}")
                time.sleep(2)
                continue
            check_response(response)
            try:
                data = response.json()
            except ValueError:
                raise BotBlockedError(f"{response.url}: expected JSON, got {response.headers.get('content-type')}")
            time.sleep(DELAY)
            error = data.get("error")
            if error:
                if error.get("code") in ("maxlag", "ratelimited"):
                    raise BotBlockedError(f"API asked us to back off: {error.get('code')} {error.get('info')}")
                logging.warning(f"API error for {params}: {error}")
                return None
            return data
        return None

    def category_members(self, category, member_type):
        """Titles in a category; member_type is 'subcat' or 'page' (main namespace only)."""
        params = {"action": "query", "list": "categorymembers", "cmtitle": category,
                  "cmtype": member_type, "cmlimit": "500"}
        if member_type == "page":
            params["cmnamespace"] = "0"
        titles, cont = [], {}
        while True:
            data = self.api(**params, **cont)
            if not data:
                return titles
            titles += [member["title"] for member in data["query"]["categorymembers"]]
            if "continue" not in data:
                return titles
            cont = data["continue"]

    def fetch_article(self, title):
        data = self.api(action="parse", page=title, prop="text", redirects="1",
                        disableeditsection="1", disabletoc="1")
        if not data:
            return None
        parsed = data["parse"]
        soup = BeautifulSoup(parsed["text"], 'html.parser')
        for garbage in soup.find_all(class_=GARBAGE_CLASSES):
            garbage.decompose()
        page_title = parsed["title"]
        return {
            "title": page_title,
            "url": f"{WIKI_URL}/wiki/{quote(page_title.replace(' ', '_'), safe='/:(),')}",
            "content": md(str(soup), heading_style="ATX").strip(),
        }

    def run(self):
        print(f"Data will be saved to: {self.output_file}")
        logging.info(f"--- PHASE 1: SCANNING ROOT ({self.root_category}) ---")
        subcategories = [
            cat for cat in self.category_members(self.root_category, "subcat")
            if not any(word in cat.lower() for word in SKIP_SUBCATEGORY_WORDS)
        ]
        articles = self.category_members(self.root_category, "page")
        print(f"Found {len(subcategories)} sub-categories.")

        logging.info("--- PHASE 2: SCANNING SUB-CATEGORIES ---")
        for category in tqdm(subcategories, desc="Scanning Categories", unit="cat"):
            articles += self.category_members(category, "page")
        articles = list(dict.fromkeys(articles))
        print(f"Found {len(articles)} unique articles.")
        if not articles:
            print("ERROR: 0 articles found. Nothing to save.")
            return False

        logging.info("--- PHASE 3: SAVING ARTICLES ---")
        saved = set()
        with open(partial_path(self.output_file), 'w', encoding='utf-8') as f:
            for title in tqdm(articles, desc="Saving Articles", unit="page"):
                entry = self.fetch_article(title)
                # Two category members can redirect to the same article.
                if entry and entry["title"] not in saved:
                    saved.add(entry["title"])
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        publish(self.output_file)
        print(f"Done! Saved {len(saved)} articles to {self.output_file}")
        return True


if __name__ == "__main__":
    crawler = FandomMainCrawler(ROOT_CATEGORY, OUTPUT_FILE)
    try:
        ok = crawler.run()
    except BotBlockedError as e:
        logging.error(f"Blocked by the site, stopping. Previous dump kept. {e}")
        ok = False
    raise SystemExit(0 if ok else 2)
