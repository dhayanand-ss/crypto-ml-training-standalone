#!/usr/bin/env python3
"""
TRL Inference Module
Runs TRL (FinBERT) sentiment analysis on scraped news articles and saves predictions.
"""

import os
import sys
import logging
from pathlib import Path
import pandas as pd

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Now we can import models
from models.finbert_sentiment import FinBERTSentimentAnalyzer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Main function to run TRL inference on news articles"""
    print("=" * 60)
    print("Running TRL Inference")
    print("=" * 60)
    
    # Path to articles CSV
    articles_path = "data/articles.csv"
    
    # Check if articles file exists
    if not os.path.exists(articles_path):
        logger.error(f"Articles file not found at {articles_path}")
        logger.info("Please run past_news_scrape first to collect articles")
        return 1
    
    # Load articles
    logger.info(f"Loading articles from {articles_path}")
    try:
        articles_df = pd.read_csv(articles_path)
        logger.info(f"Loaded {len(articles_df)} articles")
    except Exception as e:
        logger.error(f"Error loading articles: {e}")
        return 1
    
    if len(articles_df) == 0:
        logger.warning("No articles found in the CSV file")
        return 0
    
    # Initialize FinBERT analyzer
    logger.info("Initializing FinBERT sentiment analyzer...")
    try:
        analyzer = FinBERTSentimentAnalyzer()
        logger.info("FinBERT analyzer initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing FinBERT analyzer: {e}")
        logger.error("Make sure peft library is installed: pip install peft")
        return 1
    
    # Run sentiment analysis
    logger.info("Running sentiment analysis on articles...")
    try:
        # Analyze sentiment for all articles
        sentiment_df = analyzer.analyze_news_sentiment(articles_df)
        logger.info(f"Analyzed sentiment for {len(sentiment_df)} articles")
        
        # Get daily sentiment features
        daily_sentiment = analyzer.get_daily_sentiment_features(sentiment_df)
        logger.info(f"Generated daily sentiment features for {len(daily_sentiment)} days")
        
    except Exception as e:
        logger.error(f"Error during sentiment analysis: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # Save results
    os.makedirs("results", exist_ok=True)
    
    # Save detailed predictions
    output_path = "results/trl_predictions.csv"
    try:
        sentiment_df.to_csv(output_path, index=False)
        logger.info(f"Saved detailed predictions to {output_path}")
    except Exception as e:
        logger.error(f"Error saving predictions: {e}")
        return 1
    
    # Save daily sentiment features
    daily_output_path = "results/daily_sentiment_features.csv"
    try:
        daily_sentiment.to_csv(daily_output_path, index=False)
        logger.info(f"Saved daily sentiment features to {daily_output_path}")
    except Exception as e:
        logger.error(f"Error saving daily sentiment: {e}")
        return 1
    
    # Try to save to database if available
    try:
        from utils.database.db import CryptoDB
        
        logger.info("Saving predictions to database...")
        db = CryptoDB()
        
        # Convert sentiment predictions to format expected by database
        # Note: This is a simplified version - adjust based on your database schema
        if 'date' in sentiment_df.columns and 'finbert_prediction' in sentiment_df.columns:
            # Prepare data for database
            dates = pd.to_datetime(sentiment_df['date'], errors='coerce', utc=True)
            predictions = sentiment_df['finbert_prediction'].values
            
            # Save to database (adjust table/model/version as needed)
            # This is a placeholder - adjust based on your actual database schema
            logger.info("Database save functionality - implement based on your schema")
            # db.upsert_predictions(table_name="trl_predictions", model="trl", version="v1", 
            #                      open_times=dates, predictions=predictions, original_df=sentiment_df)
        
        logger.info("Database operations completed")
    except ImportError:
        logger.warning("Database module not available, skipping database save")
    except Exception as e:
        logger.warning(f"Could not save to database: {e}")
        logger.info("Predictions saved to CSV files instead")
    
    print("=" * 60)
    print("TRL Inference completed successfully!")
    print("=" * 60)
    logger.info(f"Total articles processed: {len(sentiment_df)}")
    logger.info(f"Daily sentiment features: {len(daily_sentiment)} days")
    
    return 0


if __name__ == "__main__":
    exit(main())





