import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, unquote
import time
import json
import logging
import os
from markdownify import markdownify as md
from core.logging_config import setup_logging

# --- CONFIGURATION ---
START_URL = "https://politicsandwar.com/pwpedia/index"

# Define directory and file paths
DATA_DIR = "/scripts/pwpedia_scraper/"
OUTPUT_FILE = os.path.join(DATA_DIR, "pwpedia_data.jsonl")
LOG_FILE = os.path.join(DATA_DIR, "crawler_errors.log")

# Ensure the directory exists
os.makedirs(DATA_DIR, exist_ok=True)

# Politeness: Time to wait between requests (seconds)
DELAY = 1.0 
# User Agent: Identifies your bot to the server
HEADERS = {
    'User-Agent': 'PWPediaAICollector/1.0 (+https://politicsandwar.com)'
}

# --- LOGGING SETUP ---
setup_logging(process_name="pwpedia_scraper", level=os.getenv("LOG_LEVEL", "INFO"))

class PWPediaCrawler:
    def __init__(self, start_url, output_file):
        self.start_url = start_url
        self.output_file = output_file
        
        # Set to track visited URLs (prevents loops)
        self.visited = set()
        # List to act as a queue for URLs to visit
        self.queue = [start_url]
        
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def get_title_from_url(self, url):
        """
        Extracts a readable title from the URL.
        Example: .../pwpedia/article/Naval-Battles -> Naval-Battles
        """
        try:
            parsed = urlparse(url)
            path = parsed.path
            
            # Logic: If it contains /article/, take what comes after.
            if "/article/" in path:
                title_slug = path.split("/article/")[-1]
            else:
                # Fallback for index or category pages
                title_slug = path.split("/")[-1]
            
            # Unquote removes %20 and replaces with spaces if present, 
            # though we keep dashes if that's preferred.
            return unquote(title_slug) or "Index"
        except Exception as e:
            logging.error(f"Error parsing title from {url}: {e}")
            return "Unknown"

    def fetch_page(self, url):
        """
        Fetches the raw HTML with retry logic and error handling.
        """
        retries = 3
        for i in range(retries):
            try:
                response = self.session.get(url, timeout=10)
                
                # Check for HTTP errors (404, 500, etc.)
                if response.status_code != 200:
                    logging.warning(f"Status {response.status_code} for {url}")
                    return None
                
                return response.text
            except requests.exceptions.RequestException as e:
                logging.warning(f"Connection attempt {i+1} failed for {url}: {e}")
                time.sleep(2)
        
        logging.error(f"Failed to fetch {url} after {retries} attempts.")
        return None

    def process_queue(self):
        """
        Main execution loop.
        """
        logging.info(f"Starting Crawl at {self.start_url}...")
        logging.info(f"Saving data to: {self.output_file}")
        
        # Open file in 'w' (Write) mode. 
        # This guarantees we overwrite old data with fresh data every time the script runs.
        with open(self.output_file, 'w', encoding='utf-8') as f:
            
            while self.queue:
                current_url = self.queue.pop(0)
                
                # Skip if already visited
                if current_url in self.visited:
                    continue
                
                self.visited.add(current_url)
                
                # 1. Fetch the Raw HTML
                html = self.fetch_page(current_url)
                if not html:
                    continue

                # 2. Parse HTML
                soup = BeautifulSoup(html, 'html.parser')

                # 3. HARVEST LINKS (Check the ENTIRE page)
                # We do this on the whole 'soup' object to ensure we catch links 
                # in sidebars, footers, and headers, not just the content area.
                self.find_new_links(soup, current_url)

                # 4. EXTRACT CONTENT (Narrow down to .ck-content)
                # We only save data if the specific content class exists.
                self.extract_and_save_content(soup, current_url, f)

                # Politeness delay
                time.sleep(DELAY)

        logging.info("Crawl Completed.")
        logging.info(f"Total pages crawled: {len(self.visited)}")

    def find_new_links(self, soup, current_url):
        """
        Scans the ENTIRE page for internal links to add to the queue.
        """
        # Find all <a> tags with an href attribute
        for link in soup.find_all('a', href=True):
            href = link['href']
            
            # Convert relative paths (/pwpedia/...) to full URLs
            full_url = urljoin(current_url, href)
            
            # Remove anchor fragments (e.g., #section-1) to avoid duplicates
            full_url = full_url.split('#')[0]

            # --- SCOPE FILTERS ---
            # 1. Must be within /pwpedia/
            # 2. Must NOT be the main game (login, register, etc) unless it's inside pwpedia
            # 3. Ensure we haven't visited or queued it yet
            if ("/pwpedia/" in full_url) and \
               (full_url not in self.visited) and \
               (full_url not in self.queue):
                
                self.queue.append(full_url)

    def extract_and_save_content(self, soup, url, file_handle):
        """
        Extracts only the relevant article content and saves it to JSONL.
        """
        # Target the specific content class
        content_div = soup.find(class_='ck-content')

        if not content_div:
            # It's common for index pages or category pages not to have this class.
            # We log it but don't stop.
            logging.info(f"Skipping save for {url} - No .ck-content found.")
            return

        try:
            # Convert HTML to Markdown
            # heading_style="ATX" ensures headers use # instead of underlining
            markdown_text = md(str(content_div), heading_style="ATX")
            
            # Clean up title from URL
            title = self.get_title_from_url(url)

            # Construct Data Object
            entry = {
                "title": title,
                "url": url,
                "content": markdown_text.strip()
            }

            # Write one line of JSON
            file_handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
            logging.info(f"Saved: {title}")

        except Exception as e:
            logging.error(f"Error parsing content for {url}: {e}")

# --- ENTRY POINT ---
if __name__ == "__main__":
    crawler = PWPediaCrawler(START_URL, OUTPUT_FILE)
    crawler.process_queue()