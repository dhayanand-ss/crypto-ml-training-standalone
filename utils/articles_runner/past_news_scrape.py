"""
Historical news scraper for Yahoo Finance cryptocurrency news.
"""

from playwright.sync_api import sync_playwright, TimeoutError
from bs4 import BeautifulSoup
from tqdm import tqdm
import time
import random
import os
import pandas as pd
from .scrape import scrape_post


def scroll_until_end(page, max_scrolls=50, back_off=1, max_wait=66):
    """
    Scroll page until all articles are loaded (infinite scroll).
    
    Args:
        page: Playwright page object
        max_scrolls: Maximum number of scroll attempts
        back_off: Initial pause between scrolls
        max_wait: Maximum wait time between scrolls
    
    Returns:
        page: The page object after scrolling
    """
    prev_count = 0
    scrolls = 0
    pause = back_off
    
    while scrolls < max_scrolls and pause < max_wait:
        # Scroll to bottom
        page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
        scrolls += 1
        
        # Random small delay to mimic human scrolling
        time.sleep(random.uniform(pause, pause + 1.5))
        
        html = page.content()
        soup = BeautifulSoup(html, "html.parser")
        articles = soup.find_all(attrs={"role": "article"})
        current_count = len(articles)
        
        print(f"Scroll {scrolls}: found {current_count} articles")
        
        if current_count == prev_count:
            print("No new articles loaded, increasing pause time.")
            pause *= 2
        else:
            print("New articles loaded, resetting pause time.")
            pause = back_off
            prev_count = current_count
        
        if pause >= max_wait:
            print("Reached max wait time, stopping scroll.")
            break
    
    return page


def scrape_historical_news(coins, output_path="data/articles.csv", max_articles=2000, min_date=None):
    """
    Scrape historical news articles for cryptocurrency coins.
    
    Args:
        coins: List of coin symbols (e.g., ['BTC-USD', 'ETH-USD'])
        output_path: Path to save articles CSV
        max_articles: Maximum number of articles to scrape per coin (increased to get more historical articles)
        min_date: Minimum date to keep articles (e.g., '2023-01-01'). Articles before this date will be filtered out.
    """
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
    
    all_articles = []
    
    try:
        with sync_playwright() as p:
            # Launch browser in headless mode
            browser = p.chromium.launch(
                headless=True, 
                args=["--no-sandbox", "--disable-setuid-sandbox"]
            )
            
            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/117.0.0.0 Safari/537.36",
                extra_http_headers={
                    "Accept-Language": "en-US,en;q=0.9"
                }
            )
            
            page = context.new_page()
            page.set_default_timeout(300000)
            page.set_default_navigation_timeout(300000)
        
            for coin in tqdm(coins, desc="Scraping coins"):
                url = f"https://finance.yahoo.com/quote/{coin}/news/"
                print(f"Scraping URL: {url}")
                
                try:
                    page.goto(url, wait_until="domcontentloaded")
                    time.sleep(2)  # Allow initial content to load
                    
                    # Handle cookie consent
                    try:
                        page.wait_for_selector("button.accept-all", timeout=5000)
                        page.click("button.accept-all")
                        print("Cookie consent accepted")
                        page.wait_for_timeout(3000)  # wait for articles to load
                    except TimeoutError:
                        print("No cookie banner detected")
                    
                    # Scroll and load all articles
                    page = scroll_until_end(page, max_scrolls=100)
                    
                    # Extract links
                    html = page.content()
                    soup = BeautifulSoup(html, "html.parser")
                    articles = soup.find_all(attrs={"role": "article"})
                    
                    links = []
                    for article in articles[:max_articles]:
                        link_elem = article.find('a', href=True)
                        if link_elem:
                            link = link_elem.get('href')
                            if link and link.startswith('/'):
                                link = f"https://finance.yahoo.com{link}"
                            elif link and not link.startswith('http'):
                                link = f"https://finance.yahoo.com{link}"
                            if link:
                                links.append(link)
                    
                    print(f"Total articles found for {coin}: {len(links)}")
                    
                    # Scrape article content
                    try:
                        scraped = scrape_post(links, page, output_path)
                        all_articles.extend(scraped.values())
                    except Exception as e:
                        print(f"Error scraping articles for {coin}: {e}")
                        import traceback
                        traceback.print_exc()
                    
                    time.sleep(2)  # Rate limiting between coins
                    
                except Exception as e:
                    print(f"Error scraping {coin}: {e}")
                    import traceback
                    traceback.print_exc()
                    continue
            
            browser.close()
    except Exception as e:
        print(f"Fatal error during scraping: {e}")
        print("Note: If Playwright browsers are not installed, run: playwright install chromium")
        import traceback
        traceback.print_exc()
        # Don't raise - allow partial results to be saved
    
    # Results are already saved incrementally by scrape_post
    # Just report summary
    if os.path.exists(output_path):
        df = pd.read_csv(output_path)
        
        # Filter by date if min_date specified
        if min_date and 'date' in df.columns and len(df) > 0:
            df['date_parsed'] = pd.to_datetime(df['date'], errors='coerce', utc=True)
            min_date_dt = pd.to_datetime(min_date, utc=True)
            initial_count = len(df)
            df_filtered = df[df['date_parsed'] >= min_date_dt].copy()
            df_filtered = df_filtered.drop(columns=['date_parsed'], errors='ignore')
            
            if len(df_filtered) < initial_count:
                print(f"\nFiltered {initial_count - len(df_filtered)} articles before {min_date}")
                print(f"Keeping {len(df_filtered)} articles from {min_date} onwards")
                df_filtered.to_csv(output_path, index=False)
                df = df_filtered
    
    print(f"\nTotal articles scraped: {len(all_articles)}")
    if os.path.exists(output_path):
        df_final = pd.read_csv(output_path)
        print(f"Total articles in file: {len(df_final)}")
    print(f"Articles saved to: {output_path}")
    return all_articles


def scrape_current_news(coins, output_path="data/articles.csv"):
    """Scrape current/latest news articles"""
    return scrape_historical_news(coins, output_path, max_articles=100)


def main():
    """Main function to run news scraping"""
    print("=" * 60)
    print("Past News Scraper")
    print("=" * 60)
    
    # Default coins to scrape
    coins = ['BTC-USD', 'ETH-USD']
    output_path = "data/articles.csv"
    
    print(f"Scraping news for: {coins}")
    print(f"Output path: {output_path}")
    print()
    
    try:
        articles = scrape_current_news(coins, output_path)
        print(f"\nSuccessfully scraped {len(articles)} articles")
        return 0
    except Exception as e:
        print(f"\nError during scraping: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())

