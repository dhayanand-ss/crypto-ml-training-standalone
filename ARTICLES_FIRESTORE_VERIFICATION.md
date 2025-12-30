# Articles Firestore Access Verification

## Current Status: ❌ Articles are NOT accessed from Firestore

### Finding Summary

After analyzing the codebase, **articles/news data is currently only read from CSV files**, not from Firestore.

## Current Implementation

### ✅ What IS using Firestore:

1. **Price Data (CryptoDB)**:
   - ✅ Written to Firestore (collections: `btcusdt`, etc.)
   - ✅ Read from Firestore via methods like:
     - `get_data()` - Get price data from Firestore
     - `get_last_date()` - Get latest date from Firestore
     - `bulk_insert_df()` - Write price data to Firestore

2. **TRL Predictions**:
   - ✅ Written to Firestore (`trl` collection)
   - ✅ Contains processed articles with predictions, labels, price changes
   - ❌ Does NOT contain raw articles

3. **Status Tracking**:
   - ✅ Training status stored in Firestore (`crypto_batch_status`, `crypto_batch_events`)

### ❌ What is NOT using Firestore:

1. **Raw Articles/News Data**:
   - ❌ **NOT written to Firestore**
   - ❌ **NOT read from Firestore**
   - ✅ **Only read from CSV**: `data/articles.csv`

## Code Evidence

### Where Articles are Read (CSV only):

1. **`simplified_integrated_model.py`** (line 135-150):
   ```python
   news_path = os.path.join("data", "articles.csv")
   news_df = pd.read_csv(news_path)
   ```

2. **`utils/serve/trl_inference.py`** (line 35-46):
   ```python
   articles_path = "data/articles.csv"
   articles_df = pd.read_csv(articles_path)
   ```

3. **`utils/trainer/trl_train.py`** (line 142):
   ```python
   news_df = pd.read_csv(args.articles_path)
   ```

4. **`models/finbert_sentiment.py`** (line 593):
   ```python
   news_path = "data/articles.csv"
   ```

### Where Articles Could Be Written to Firestore:

- **`utils/database/db.py`** has `insert_if_not_exists()` method that writes to `trl` collection, but this is for **processed articles with predictions**, not raw articles.

### Where Price Data IS Read from Firestore:

- **`utils/database/db.py`** has `get_data()` method that reads price data from Firestore collections.

## Missing Functionality

### No Methods to:
1. ❌ Read raw articles from Firestore
2. ❌ Write raw articles to Firestore
3. ❌ Query articles by date from Firestore
4. ❌ Sync articles CSV to Firestore (like `update_from_csv()` does for prices)

## Recommendation

If you want articles to be accessed from Firestore, you need to:

1. **Add a method to write articles to Firestore** (similar to `bulk_insert_df()` for prices)
2. **Add a method to read articles from Firestore** (similar to `get_data()` for prices)
3. **Update training/inference code** to read from Firestore instead of CSV
4. **Add sync functionality** to keep Firestore and CSV in sync

Would you like me to implement Firestore support for articles?





