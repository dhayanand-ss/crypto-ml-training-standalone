#!/usr/bin/env python3
"""
Complete pipeline to create news/article dataset.
Run this script to:
1. Scrape news articles from Yahoo Finance
2. Annotate with price changes
3. Save final dataset
"""

import argparse
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from utils.articles_runner.past_news_scrape import scrape_historical_news
from datetime import datetime, timedelta
# Import from trainer.train_utils (consolidated annotation function)
from trainer.train_utils import annotate_news, validate_news_dataset
import pandas as pd


def main():
    parser = argparse.ArgumentParser(
        description="Create annotated news dataset for crypto ML",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Option 1: Scrape only (no price data needed)
  python create_news_dataset.py --coins BTC-USD
  
  # Option 2: Scrape and annotate in one go (requires price data)
  python create_news_dataset.py --coins BTC-USD --price-data data/btcusdt.csv
  
  # Option 3: Annotate existing articles (requires price data)
  python create_news_dataset.py --skip-scraping --price-data data/btcusdt.csv
  
  # Scrape multiple coins
  python create_news_dataset.py --coins BTC-USD ETH-USD
  
  # Custom annotation parameters
  python create_news_dataset.py --skip-scraping --price-data data/btcusdt.csv --window-hours 24 --threshold 0.01
  
Note: Scraping and annotation are independent:
  - Scraping: Doesn't need price data, creates articles.csv without labels
  - Annotation: Needs price data, adds price_change and label columns
  - You can run them separately in any order
        """
    )
    parser.add_argument(
        "--coins",
        type=str,
        nargs="+",
        default=["BTC-USD"],
        help='List of coin symbols (e.g., BTC-USD ETH-USD). Default: ["BTC-USD"]'
    )
    parser.add_argument(
        "--price-data",
        type=str,
        default="data/btcusdt.csv",
        help="Path to price data CSV (default: data/btcusdt.csv)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/articles.csv",
        help="Output path for articles CSV (default: data/articles.csv)"
    )
    parser.add_argument(
        "--window-hours",
        type=int,
        default=12,
        help="Hours after news to measure price change (default: 12)"
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.005,
        help="Price change threshold for labels (default: 0.005 = 0.5%%)"
    )
    parser.add_argument(
        "--skip-scraping",
        action="store_true",
        help="Skip scraping phase, only annotate existing articles. "
             "Use this if you already have articles.csv and want to add labels."
    )
    
    args = parser.parse_args()
    
    # Step 1: Scrape articles (if not skipped)
    if not args.skip_scraping:
        print("=" * 60)
        print("PHASE 1: Scraping News Articles")
        print("=" * 60)
        print("NOTE: Scraping is independent and doesn't require price data.")
        print(f"Coins: {args.coins}")
        print(f"Output: {args.output}")
        print()
        
        # Create output directory
        os.makedirs(os.path.dirname(args.output) if os.path.dirname(args.output) else '.', exist_ok=True)
        
        try:
            # Calculate min_date as 2023-01-01 to get articles from 2023 onwards
            min_date = '2023-01-01'
            
            print(f"Scraping articles (will filter to keep only articles from {min_date} onwards)...")
            print("Note: Yahoo Finance only shows recent articles. We'll scrape as many as possible")
            print("and filter to keep articles from 2023-01-01 onwards.")
            scrape_historical_news(args.coins, args.output, max_articles=2000, min_date=min_date)
            print(f"\n[OK] Scraping complete. Articles saved to {args.output}\n")
            print("Articles are saved WITHOUT labels (price_change and label will be None).")
            print("Run annotation later with --skip-scraping when you have price data.\n")
        except Exception as e:
            print(f"\n[ERROR] Error during scraping: {e}")
            print("You can still annotate existing articles with --skip-scraping")
            if not os.path.exists(args.output):
                print(f"Error: No articles found at {args.output}")
                return 1
    
    # Step 2: Validate that articles file exists
    if not os.path.exists(args.output):
        print(f"[ERROR] Articles file not found: {args.output}")
        print("Please run scraping first (remove --skip-scraping flag)")
        return 1
    
    # Step 3: Annotate articles (OPTIONAL - requires price data)
    print("=" * 60)
    print("PHASE 2: Annotating Articles with Price Changes")
    print("=" * 60)
    print("NOTE: Annotation requires price data to calculate labels.")
    print("If you don't have price data yet, you can skip annotation.")
    print("Articles will be saved without labels (can annotate later).")
    print()
    print(f"Price data: {args.price_data}")
    
    # Check if price data exists
    if not os.path.exists(args.price_data):
        print(f"\n⚠️  Warning: Price data file not found: {args.price_data}")
        print("Annotation will be skipped. Articles saved without labels.")
        print("You can annotate later by running:")
        print(f"  python create_news_dataset.py --skip-scraping --price-data {args.price_data}")
        print()
        print("[OK] Scraping phase complete!")
        print(f"Articles saved to: {args.output} (without labels)")
        return 0
    
    print(f"Window: {args.window_hours} hours")
    print(f"Threshold: {args.threshold} ({args.threshold*100:.2f}%)")
    print()
    
    try:
        # Load data
        df_news = pd.read_csv(args.output)
        print(f"Loaded {len(df_news)} articles")
        
        df_prices = pd.read_csv(args.price_data)
        print(f"Loaded {len(df_prices)} price data points")
        
        # Check required columns
        if 'open_time' not in df_prices.columns or 'close' not in df_prices.columns:
            print("[ERROR] Price data must have 'open_time' and 'close' columns")
            return 1
        
        if 'date' not in df_news.columns:
            print("[ERROR] Articles must have 'date' column")
            return 1
        
        # Annotate
        print("\nAnnotating articles...")
        df_annotated = annotate_news(
            df_prices,
            df_news,
            window_hours=args.window_hours,
            threshold=args.threshold
        )
        
        # Save annotated dataset
        df_annotated.to_csv(args.output, index=False)
        
        print("\n[OK] Annotation complete!")
        print(f"\nDataset saved to: {args.output}")
        print(f"Total articles: {len(df_annotated)}")
        
        # Print statistics
        print("\n=== Dataset Statistics ===")
        if 'label' in df_annotated.columns:
            print(f"\nLabel distribution (based on {args.window_hours}-hour price change):")
            label_counts = df_annotated['label'].value_counts()
            # Label mapping: Sell=0, Hold=1, Buy=2 (corresponds to market reaction)
            label_map = {0: "Sell", 1: "Hold", 2: "Buy"}
            threshold_pct = args.threshold * 100
            for label, count in label_counts.items():
                label_name = label_map.get(label, f"Label {label}")
                if label == 0:
                    desc = f"(price decreased > {threshold_pct:.2f}%)"
                elif label == 1:
                    desc = f"(price change within ±{threshold_pct:.2f}%)"
                else:  # label == 2
                    desc = f"(price increased > {threshold_pct:.2f}%)"
                print(f"  {label_name}: {count} ({count/len(df_annotated)*100:.1f}%) {desc}")
        
        if 'price_change' in df_annotated.columns:
            print(f"\nPrice change statistics:")
            print(f"  Mean: {df_annotated['price_change'].mean():.4f} ({df_annotated['price_change'].mean()*100:.2f}%)")
            print(f"  Std: {df_annotated['price_change'].std():.4f}")
            print(f"  Min: {df_annotated['price_change'].min():.4f}")
            print(f"  Max: {df_annotated['price_change'].max():.4f}")
        
        # Validate dataset
        print("\n=== Validation ===")
        validation = validate_news_dataset(df_annotated)
        if validation['valid']:
            print("[OK] Dataset validation passed!")
        else:
            print("[WARNING] Validation issues found:")
            for issue in validation['issues']:
                print(f"  - {issue}")
        
        return 0
        
    except Exception as e:
        print(f"\n[ERROR] Error during annotation: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

