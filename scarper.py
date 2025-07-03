import argparse
import csv
import logging
import os
from dotenv import load_dotenv
import re
from pathlib import Path
from typing import Iterable, List, Dict
import time
import requests

########## [INSTRUCTIONS] ##########

# Before you get started, create a .env file and put SERPAPI_API_KEY=""
# Log into SerpAPI https://serpapi.com/ and create an account. Paste the API key into the .env file
# You get 100 free searches a month, which should yield ~2,000 profiles, use these sparingly. 
# If you run out, just create a new account w a different email and use that API key instead

COMPANIES = ["Google"] # The company you want to source. If you want multiple, add them all to this list
ROLES = ["Product Manager"] # The titles that you source. If you are looking for multiple, add them to this list
OUTPUT_DIR = "exports" # Default folder for outputs. You can change this, but you will need to hardcode path down in code
MAX_PEOPLE_PER_FILE = 100  # How many people you want per csv file. You want to seperate by company.
NUM_RESULTS = 100           # How many resulst each search gives you. Each google search gives 20 per page, and SerpAPI can scroll 5 pages. Max is 100, this is default.
OUTPUT_FILE_NAME = "Google_PMs_Example" # Name of the output csv file. Change this to wwahtever floats your boat. 

########## XXXXXXXXXXXXX ##########

load_dotenv()

# SerpAPI settings
SERPAPI_KEY = os.getenv("SERPAPI_API_KEY")
if not SERPAPI_KEY:
    raise RuntimeError("SERPAPI_API_KEY environment variable not set")
SERPAPI_URL = "https://serpapi.com/search"

# Regex for splitting name and title
NAME_TITLE_RE = re.compile(r"^(.+?)\s*[–—\-]\s*(.+)$")

def serpapi_search(query: str, num: int = NUM_RESULTS) -> List[Dict]:
    params = {
        "engine": "google",
        "q": query,
        "num": num,
        "hl": "en",
        "api_key": SERPAPI_KEY,
    }
    resp = requests.get(SERPAPI_URL, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data.get("organic_results", [])


def extract_linkedin(results: List[Dict]) -> Iterable[Dict[str, str]]:
    """Filter organic_results for LinkedIn profile entries."""
    for entry in results:
        link = entry.get("link", "")
        title = entry.get("title", "")
        if link.startswith("https://www.linkedin.com/in/"):
            yield {"title": title, "url": link}


def split_name_title(text: str) -> (str, str):
    m = NAME_TITLE_RE.match(text)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    parts = text.split(" - ", 1)
    return (parts[0].strip(), parts[1].strip()) if len(parts) == 2 else (text, "")

def collect_people(companies: List[str], roles: List[str]) -> Iterable[Dict[str, str]]:
    seen = set()
    for company in companies:
        for role in roles:
            query = f"site:linkedin.com/in/ \"{role}\" \"{company}\""
            logging.info("Querying SerpAPI: %s", query)
            results = serpapi_search(query)
            for item in extract_linkedin(results):
                url = item["url"]
                if url in seen:
                    continue
                seen.add(url)
                name, title = split_name_title(item["title"])
                yield {
                    "name": name,
                    "title": title,
                    "company_filter": company,
                    "role_filter": role,
                    "profile_url": url,
                }
            time.sleep(1)  # may change this to speed up code, but may be banned from SerpAPI. 


def write_csv(path: Path, rows: List[Dict[str, str]]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    logging.info("Wrote %d rows to %s", len(rows), path)

def main():
    parser = argparse.ArgumentParser(
        description="LinkedIn scraper using SerpAPI",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--companies",
        help="Comma-separated companies",
        default=','.join(COMPANIES)
    )
    parser.add_argument(
        "--roles",
        help="Comma-separated job titles",
        default=','.join(ROLES)
    )
    parser.add_argument(
        "--output-dir",
        help="Directory for CSV exports",
        default=OUTPUT_DIR
    )
    parser.add_argument(
        "--max-per-file",
        type=int,
        help="Max rows per CSV before splitting (0 = no split)",
        default=MAX_PEOPLE_PER_FILE
    )
    parser.add_argument(
        "--num-results",
        type=int,
        help="Results per SerpAPI call (max 100)",
        default=NUM_RESULTS
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s: %(message)s",
    )

    companies = [c.strip() for c in args.companies.split(',') if c.strip()]
    roles = [r.strip() for r in args.roles.split(',') if r.strip()]
    out_dir = Path(args.output_dir)
    max_per = args.max_per_file

    people = list(collect_people(companies, roles))
    if max_per > 0 and len(people) > max_per:
        for i in range(0, len(people), max_per):
            write_csv(
                out_dir / f"{OUTPUT_FILE_NAME}_part{i//max_per+1}.csv",
                people[i : i + max_per],
            )
    else:
        write_csv(out_dir / f"{OUTPUT_FILE_NAME}.csv", people)

if __name__ == "__main__":
    main()


