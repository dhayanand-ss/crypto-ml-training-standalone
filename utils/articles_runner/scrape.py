"""
Article scraping module for Yahoo Finance news articles.
"""

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from tqdm import tqdm
import pandas as pd
import os
import time


def scrape_post(links, page, output_path):
    """
    Scrape individual article content from a list of links.
    
    Args:
        links: List of article URLs to scrape
        page: Playwright page object
        output_path: Path to CSV file for storing articles
        
    Returns:
        Dictionary of scraped articles
    """
    # Load existing articles or create new DataFrame
    if os.path.exists(output_path):
        df = pd.read_csv(output_path)
    else:
        df = pd.DataFrame(columns=["title", "text", "date", "link", "price_change", "label"])
    
    link_set = set(df["link"].tolist() if "link" in df.columns else [])
    articles_scrapped = {}
    
    for link in tqdm(links, desc="Scraping articles"):
        if link in link_set:
            print("Already scrapped:", link)
            continue
        
        time.sleep(1)
        print("--" * 20)
        print("\nProcessing link:", link)
        
        # Validate URL prefix
        prefix_allowed = ["https://finance.yahoo.com/" + i for i in ['news', 'personal-finance', 'video', 'm']]
        allow = False
        for prefix in prefix_allowed:
            if link.startswith(prefix):
                allow = True
                break
        
        if not allow:
            print("!!!Skipping link:", link)
            continue
        
        if "https://finance.yahoo.com/" in link:
            print(link)
            try:
                page.goto(link, wait_until="domcontentloaded")
                html = page.content()
                soup = BeautifulSoup(html, "html.parser")
                
                # Extract date - try multiple selectors
                date = None
                date_elem = soup.find("time", class_="byline-attr-meta-time")
                if date_elem:
                    date = date_elem.get('datetime')
                else:
                    date_elem = soup.find("time")
                    if date_elem:
                        date = date_elem.get('datetime')
                
                # Extract title - try multiple selectors
                title = None
                title_elem = soup.find("h1", class_="cover-title")
                if title_elem:
                    title = title_elem.text
                else:
                    title_elem = soup.find('h1')
                    if title_elem:
                        title = title_elem.get_text(strip=True)
                
                # Extract article content
                articles = soup.find(attrs={"data-testid": "article-content-wrapper"})
                if articles is None:
                    article_wraps = soup.find_all("div", class_="article-wrap")
                    if article_wraps:
                        articles = article_wraps[-1].div
                    else:
                        articles = soup.find('div', class_='caas-body')
                else:
                    articles = articles.find("div", class_="body-wrap")
                
                all_text = []
                if articles is not None:
                    p_tags = articles.find_all("p")
                    for p_tag in p_tags:
                        text_content = p_tag.text.strip()
                        if text_content:
                            all_text.append(text_content)
                else:
                    print("Empty article content for link:", link)
                
                # Join text as string for storage
                text = '\n'.join(all_text) if all_text else ""
                
                print("Title:", title, len(text), "characters")
                
                if title and text:
                    articles_scrapped[link] = {
                        "title": title,
                        "text": text,  # Store as string
                        "date": date,
                        "link": link
                    }
                    
                    # Save incrementally
                    df_new = pd.DataFrame([{
                        "title": title,
                        "text": text,  # Save as string
                        "date": date,
                        "link": link,
                        "price_change": None,
                        "label": None
                    }])
                    df = pd.concat([df, df_new], ignore_index=True)
                    df.to_csv(output_path, index=False)
                    link_set.add(link)
                else:
                    print(f"Missing title or text for link: {link}")
                    
            except Exception as e:
                print(f"Error scraping {link}: {e}")
                import traceback
                traceback.print_exc()
                continue
    
    return articles_scrapped

