#!/usr/bin/env python3
"""
Script to download more articles from GCS or scrape additional articles
"""

import os
import sys
import pandas as pd
from pathlib import Path

def download_from_gcs():
    """Try to download articles from GCS"""
    try:
        from trainer.train_utils import download_s3_dataset
        print("Downloading articles from GCS...")
        download_s3_dataset('BTCUSDT', trl_model=True)
        print("Articles downloaded successfully!")
        return True
    except Exception as e:
        print(f"Failed to download from GCS: {e}")
        print("Note: GCS credentials may not be configured")
        return False

def scrape_more_articles():
    """Scrape more articles using the news scraper"""
    try:
        from utils.articles_runner.past_news_scrape import scrape_historical_news
        from datetime import datetime, timedelta
        
        print("Scraping additional articles...")
        
        # Scrape articles from the past 30 days
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        
        articles = scrape_historical_news(
            coins=["BTC-USD"],
            start_date=start_date.strftime("%Y-%m-%d"),
            end_date=end_date.strftime("%Y-%m-%d")
        )
        
        if articles and len(articles) > 0:
            # Load existing articles
            existing_path = Path("data/articles.csv")
            if existing_path.exists():
                existing_df = pd.read_csv(existing_path)
                print(f"Existing articles: {len(existing_df)}")
            else:
                existing_df = pd.DataFrame()
            
            # Combine with new articles
            new_df = pd.DataFrame(articles)
            combined_df = pd.concat([existing_df, new_df], ignore_index=True)
            
            # Remove duplicates
            combined_df = combined_df.drop_duplicates(subset=['link'], keep='first')
            
            # Save
            combined_df.to_csv(existing_path, index=False)
            print(f"Total articles after scraping: {len(combined_df)}")
            print(f"New articles added: {len(combined_df) - len(existing_df)}")
            return True
        else:
            print("No new articles scraped")
            return False
            
    except Exception as e:
        print(f"Failed to scrape articles: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("=" * 60)
    print("Download/Scrape More Articles for TRL Training")
    print("=" * 60)
    print()
    
    # Check current article count
    articles_path = Path("data/articles.csv")
    if articles_path.exists():
        df = pd.read_csv(articles_path)
        print(f"Current articles: {len(df)}")
    else:
        print("No existing articles file found")
    
    print()
    print("Attempting to download from GCS...")
    if download_from_gcs():
        print("Successfully downloaded from GCS!")
        return
    
    print()
    print("GCS download failed. Attempting to scrape more articles...")
    if scrape_more_articles():
        print("Successfully scraped additional articles!")
    else:
        print("Failed to get more articles. Using existing articles.")

if __name__ == "__main__":
    main()

















