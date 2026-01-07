import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, unquote
import time
import json
import logging
import os
from markdownify import markdownify as md
from tqdm import tqdm

# --- CONFIGURATION ---
ROOT_URL = "https://politicsandwar.fandom.com/wiki/Category:Mechanics"

# --- PATH CONFIGURATION (FIXED) ---
# This gets the directory where THIS script is currently running
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Save files in the same folder as the script
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "fandom_data.jsonl")
LOG_FILE = os.path.join(SCRIPT_DIR, "mechanics_main_errors.log")

DELAY = 1.0 
HEADERS = {
    'User-Agent': 'PnWMechanicsBot/1.0 (+http://politicsandwar.fandom.com)'
}

# --- LOGGING SETUP ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, mode='w')
    ]
)

class FandomMainCrawler:
    def __init__(self, root_url, output_file):
        self.root_url = root_url
        self.output_file = output_file
        
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        
        self.target_subcategories = [] 
        self.target_articles = []
        
        self.scanned_urls = set()
        self.saved_urls = set()

    def fetch_page(self, url):
        retries = 3
        for i in range(retries):
            try:
                response = self.session.get(url, timeout=10)
                if response.status_code != 200:
                    logging.warning(f"Status {response.status_code} for {url}")
                    return None
                return response.text
            except requests.exceptions.RequestException as e:
                logging.warning(f"Connection attempt {i+1} failed for {url}: {e}")
                time.sleep(2)
        return None

    def get_clean_title(self, url):
        try:
            path = urlparse(url).path
            slug = path.split("/wiki/")[-1] if "/wiki/" in path else path.split("/")[-1]
            return unquote(slug).replace("_", " ")
        except:
            return "Unknown"

    def run(self):
        print(f"Data will be saved to: {self.output_file}")
        
        # --- PHASE 1 ---
        print(f"--- PHASE 1: SCANNING ROOT ---")
        logging.info("--- PHASE 1: SCANNING ROOT (Category:Mechanics) ---")
        
        # Scan root (collect_subcats=True)
        self.scan_category_page(self.root_url, collect_subcats=True)
        
        if not self.target_subcategories and not self.target_articles:
            print("WARNING: No links found at root. Check Internet connection or Fandom layout changes.")
            return

        # --- PHASE 2 ---
        print(f"Found {len(self.target_subcategories)} initial sub-categories.")
        logging.info(f"--- PHASE 2: SCANNING SUB-CATEGORIES ---")
        
        i = 0
        with tqdm(total=len(self.target_subcategories), desc="Scanning Categories", unit="cat") as pbar:
            while i < len(self.target_subcategories):
                cat_url = self.target_subcategories[i]
                i += 1
                
                if cat_url == self.root_url: continue

                self.scan_category_page(cat_url, collect_subcats=False)
                
                # Update progress bar if list grew
                pbar.total = len(self.target_subcategories)
                pbar.refresh()
                pbar.update(1)
                
                time.sleep(DELAY)
        
        # --- PHASE 3 ---
        print(f"Found {len(self.target_articles)} unique articles.")
        
        if len(self.target_articles) == 0:
            print("ERROR: 0 articles found. Nothing to save.")
            return

        logging.info(f"--- PHASE 3: SAVING ARTICLES ---")
        self.save_all_articles()
        
        print(f"Done! Check {self.output_file}")

    def scan_category_page(self, url, collect_subcats=False):
        if url in self.scanned_urls: return
        self.scanned_urls.add(url)

        html = self.fetch_page(url)
        if not html: return

        soup = BeautifulSoup(html, 'html.parser')
        
        # --- ROBUST SELECTOR STRATEGY ---
        # 1. Try Main
        main_content = soup.find('main')
        # 2. Try Standard MediaWiki body
        if not main_content: main_content = soup.find(id='mw-content-text')
        # 3. Try Content Body class
        if not main_content: main_content = soup.find(class_='mw-body')

        if not main_content:
            logging.warning(f"Could not find Main Content area for {url}")
            return

        IGNORE_PREFIXES = [
            "Special:", "User:", "User_blog:", "Talk:", "File:", 
            "Message_Wall:", "Thread:", "Category_talk:", "Template:", 
            "Template_talk:", "Blog:", "Community_Central:", "Help:"
        ]

        found_new_cats = 0
        found_new_arts = 0

        for link in main_content.find_all('a', href=True):
            href = link['href']
            full_url = urljoin(url, href)
            
            if "politicsandwar.fandom.com" not in full_url: continue
            
            parsed = urlparse(full_url)
            path_part = parsed.path
            link_title_slug = path_part.split("/wiki/")[-1] if "/wiki/" in path_part else ""
            clean_link_title = unquote(link_title_slug).replace("_", " ")

            # Handle Pagination
            if "from=" in href or "pagefrom=" in href:
                if full_url not in self.target_subcategories and full_url not in self.scanned_urls:
                    self.target_subcategories.append(full_url)
                continue

            if "?" in href: continue 
            if any(link_title_slug.startswith(p) for p in IGNORE_PREFIXES): continue

            # Classify
            if "Category:" in link_title_slug:
                if collect_subcats:
                    # Filter
                    lower_t = clean_link_title.lower()
                    if "alliances in" in lower_t or "nations in" in lower_t or "browse" in lower_t:
                        continue
                    
                    if full_url not in self.target_subcategories:
                        self.target_subcategories.append(full_url)
                        found_new_cats += 1
            else:
                if full_url not in self.target_articles:
                    self.target_articles.append(full_url)
                    found_new_arts += 1

        logging.info(f"Scanned {url}: +{found_new_cats} Subcats, +{found_new_arts} Articles.")

    def save_all_articles(self):
        unique_urls = list(set(self.target_articles))
        logging.info(f"Unique Articles to scrape: {len(unique_urls)}")

        # 'w' mode here creates the file immediately
        with open(self.output_file, 'w', encoding='utf-8') as f:
            for url in tqdm(unique_urls, desc="Saving Articles", unit="page"):
                
                if url in self.saved_urls: continue
                self.saved_urls.add(url)

                html = self.fetch_page(url)
                if not html: continue

                soup = BeautifulSoup(html, 'html.parser')
                
                content_div = soup.find(class_='mw-content-ltr')
                if not content_div: content_div = soup.find(id='mw-content-text')
                if not content_div: content_div = soup.find('main')

                if content_div:
                    # Cleanup
                    for garbage in content_div.find_all(class_=['toc', 'category-links', 'mw-editsection', 'navbox']):
                        garbage.decompose()

                    markdown_text = md(str(content_div), heading_style="ATX")
                    title = self.get_clean_title(url)

                    entry = {
                        "title": title,
                        "url": url,
                        "content": markdown_text.strip()
                    }

                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                
                time.sleep(DELAY)

if __name__ == "__main__":
    crawler = FandomMainCrawler(ROOT_URL, OUTPUT_FILE)
    crawler.run()