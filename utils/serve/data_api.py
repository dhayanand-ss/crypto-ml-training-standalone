import os
import logging
import asyncio
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from fastapi import APIRouter, Query, HTTPException, Path as PathParam
from contextlib import asynccontextmanager

# Import project utilities
from utils.database.db import CryptoDB
from utils.database.status_db import CryptoBatchDB
from utils.project_output_formatter import ProjectOutputFormatter
from data_fetcher import load_or_fetch_price_data

# Configure logging
logger = logging.getLogger(__name__)

# Global state
class DataState:
    def __init__(self):
        self.prices: Dict[str, pd.DataFrame] = {}
        self.trl: pd.DataFrame = pd.DataFrame()
        self.last_sync: datetime = datetime.utcnow()
        self.is_syncing = False
        self.db = None
        self.status_db = None
        
        # Configuration
        self.coins = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT"]
        self.data_path = os.getenv("DATA_PATH", "data")
        
        # Initialize DB connections
        self.db = None
        self.status_db = None

    async def initialize(self):
        """Initial data load"""
        logger.info("Initializing DataState...")
        
        # Initialize DB connections asynchronously (or at least not at import time)
        if not self.db:
            try:
                # Note: CryptoDB init might be slow as it syncs data
                # We run it here to avoid blocking server startup
                logger.info("Initializing CryptoDB...")
                self.db = CryptoDB(coins=self.coins, data_path=self.data_path)
                logger.info("CryptoDB initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize CryptoDB: {e}")
                
        if not self.status_db:
            try:
                logger.info("Initializing CryptoBatchDB...")
                self.status_db = CryptoBatchDB()
                logger.info("CryptoBatchDB initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize CryptoBatchDB: {e}")

        await self.sync_data_periodic()
        logger.info("DataState initialization complete")

    async def sync_data_periodic(self):
        """Full data sync"""
        if self.is_syncing:
            return
        
        self.is_syncing = True
        try:
            logger.info("Starting periodic data sync...")
            
            # 1. Load Prices
            for coin in self.coins:
                try:
                    # Use data_fetcher to load from CSV/API
                    # Run in thread pool to avoid blocking event loop
                    loop = asyncio.get_event_loop()
                    df = await loop.run_in_executor(
                        None, 
                        lambda: load_or_fetch_price_data(
                            symbol=coin,
                            interval="1m",
                            data_path=self.data_path,
                            end_date=None # Fetch up to now
                        )
                    )
                    
                    if df is not None and not df.empty:
                        # Ensure open_time is datetime for filtering
                        if df["open_time"].dtype == 'object':
                            df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
                        
                        self.prices[coin] = df
                        logger.info(f"Loaded {len(df)} rows for {coin}")
                except Exception as e:
                    logger.error(f"Error loading price data for {coin}: {e}")

            # 2. Load TRL Data
            try:
                # TRL data usually comes from a CSV or DB
                # For now, we'll try to load from CSV if DB fetch isn't implemented
                trl_path = os.path.join(self.data_path, "articles.csv")
                if os.path.exists(trl_path):
                    trl_df = pd.read_csv(trl_path)
                    if "date" in trl_df.columns:
                        trl_df["date"] = pd.to_datetime(trl_df["date"], utc=True)
                    self.trl = trl_df
                    logger.info(f"Loaded {len(trl_df)} TRL records")
                else:
                    logger.warning(f"TRL data file not found at {trl_path}")
            except Exception as e:
                logger.error(f"Error loading TRL data: {e}")

            self.last_sync = datetime.utcnow()
            
        except Exception as e:
            logger.error(f"Error during data sync: {e}")
        finally:
            self.is_syncing = False

    async def update_price_periodic(self):
        """Lightweight update for prices (e.g. fetch last few minutes)"""
        # For simplicity in this implementation, we'll rely on sync_data_periodic
        # In a production env, this would query DB for just the latest rows
        pass

    async def update_trl_periodic(self):
        """Lightweight update for TRL"""
        pass

# Initialize global state
data_state = DataState()

# Create Router
router = APIRouter()
print(f"DEBUG: Created APIRouter in data_api.py. ID: {id(router)}")

# --- Endpoints ---

@router.get("/prices/{coin}")
async def get_prices(
    coin: str = PathParam(..., description="Cryptocurrency symbol (e.g. BTCUSDT)"),
    start: str = Query(..., description="Start date (ISO format)"),
    end: str = Query(..., description="End date (ISO format)"),
    interval: Optional[str] = Query(None, description="Aggregation interval (e.g. 1h, 1d)"),
    step: int = Query(1, description="Sampling step")
):
    print(f"DEBUG: /prices/{coin} called")
    """
    Retrieves historical price data and model predictions.
    """
    coin = coin.upper()
    
    # Check if coin exists in state
    if coin not in data_state.prices:
        # Try to load it on demand
        try:
            df = load_or_fetch_price_data(symbol=coin, data_path=data_state.data_path)
            if df is not None and not df.empty:
                if df["open_time"].dtype == 'object':
                    df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
                data_state.prices[coin] = df
            else:
                raise HTTPException(status_code=404, detail=f"No data found for {coin}")
        except Exception as e:
            logger.error(f"Error loading {coin}: {e}")
            raise HTTPException(status_code=404, detail=f"Coin {coin} not found")

    df = data_state.prices[coin]
    
    # Parse dates
    try:
        start_dt = pd.to_datetime(start, utc=True)
        end_dt = pd.to_datetime(end, utc=True)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid date format")

    # Filter
    mask = (df["open_time"] >= start_dt) & (df["open_time"] <= end_dt)
    filtered_df = df.loc[mask].copy()
    
    if filtered_df.empty:
        return []

    # Resample if interval provided
    if interval:
        try:
            # Set index for resampling
            filtered_df.set_index("open_time", inplace=True)
            
            # Define aggregation dict
            agg_dict = {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum"
            }
            
            # Add prediction columns to aggregation (take last value)
            for col in filtered_df.columns:
                if col.startswith("tst_") or col.startswith("lightgbm_"):
                    agg_dict[col] = "last"
            
            # Resample
            filtered_df = filtered_df.resample(interval).agg(agg_dict).dropna()
            filtered_df.reset_index(inplace=True)
        except Exception as e:
            logger.error(f"Resampling error: {e}")
            raise HTTPException(status_code=400, detail=f"Invalid interval: {interval}")

    # Step sampling
    if step > 1:
        filtered_df = filtered_df.iloc[::step]

    # Format output using ProjectOutputFormatter logic
    # We need to extract prediction columns to pass to formatter
    # The formatter expects separate dicts for versions, but here they are columns
    # So we'll adapt the formatter logic or just format directly here to match spec
    
    results = []
    for _, row in filtered_df.iterrows():
        item = {
            "open_time": row["open_time"].isoformat().replace("+00:00", "Z"),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row["volume"])
        }
        
        # Add predictions
        for col in filtered_df.columns:
            if col.startswith("tst_") or col.startswith("lightgbm_"):
                val = row[col]
                if isinstance(val, (np.ndarray, list)):
                    item[col] = list(val)
                elif pd.notna(val):
                     # Handle string representation of list if necessary
                    if isinstance(val, str) and val.startswith("["):
                        try:
                            import ast
                            item[col] = ast.literal_eval(val)
                        except:
                            item[col] = val
                    else:
                        item[col] = val
                        
        results.append(item)
        
    return results

@router.get("/trl")
async def get_trl(
    start: str = Query(..., description="Start date"),
    end: str = Query(..., description="End date")
):
    """
    Retrieves TRL data.
    """
    print("DEBUG: /trl called")
    if data_state.trl.empty:
        return []
        
    try:
        start_dt = pd.to_datetime(start, utc=True)
        end_dt = pd.to_datetime(end, utc=True)
    except:
        raise HTTPException(status_code=400, detail="Invalid date format")
        
    df = data_state.trl
    mask = (df["date"] >= start_dt) & (df["date"] <= end_dt)
    filtered_df = df.loc[mask].copy()
    
    results = []
    for _, row in filtered_df.iterrows():
        item = {
            "title": str(row.get("title", "")),
            "link": str(row.get("link", "")),
            "date": row["date"].isoformat().replace("+00:00", "Z")
        }
        
        # Add predictions
        for col in filtered_df.columns:
            if col.startswith("trl_"):
                val = row[col]
                if isinstance(val, (np.ndarray, list)):
                    item[col] = list(val)
                elif pd.notna(val):
                    if isinstance(val, str) and val.startswith("["):
                        try:
                            import ast
                            item[col] = ast.literal_eval(val)
                        except:
                            item[col] = val
                    else:
                        item[col] = val
        results.append(item)
        
    return results

@router.get("/last_success")
async def get_last_success():
    """
    Checks last successful execution.
    """
    # Default response if DB not available
    response = {
        "last_success": None,
        "task_name": None,
        "overall_last_sync": data_state.last_sync.isoformat() + "Z"
    }
    
    if data_state.status_db and data_state.status_db._firestore_available:
        try:
            # Query for last success
            # Note: CryptoBatchDB doesn't have a direct method for this specific query
            # We'll implement a basic version using get_status if possible, 
            # or add a raw query here if we had access to the client.
            # Since we can't easily modify CryptoBatchDB right now, we'll try to find it
            # from the 'crypto_batch_status' collection directly if possible.
            
            # Using the internal db client from status_db
            status_ref = data_state.status_db.db.collection('crypto_batch_status')
            query = status_ref.where('status', '==', 'SUCCESS')\
                              .order_by('updated_at', direction='DESCENDING')\
                              .limit(1)
            docs = query.stream()
            
            for doc in docs:
                data = doc.to_dict()
                if 'task_name' in data and data['task_name'].startswith('post_train_'):
                    response["last_success"] = data['updated_at'].isoformat()
                    response["task_name"] = data['task_name']
                    break
                    
        except Exception as e:
            logger.error(f"Error querying last success: {e}")
            
    return response

@router.get("/status/events")
async def get_status_events(
    dag_name: Optional[str] = None,
    task_name: Optional[str] = None,
    limit: int = 100
):
    """Retrieves batch events."""
    if not data_state.status_db:
        return []
        
    # CryptoBatchDB.get_events filters by dag_name/run_id
    # We might need to filter manually for task_name if not supported
    events = data_state.status_db.get_events(dag_name=dag_name if dag_name else "crypto_pipeline", limit=limit)
    
    if task_name:
        events = [e for e in events if e.get('task_name') == task_name]
        
    return events

@router.get("/status/batch_status")
async def get_batch_status(
    dag_name: Optional[str] = None,
    task_name: Optional[str] = None,
    limit: int = 100
):
    """Retrieves batch status."""
    if not data_state.status_db:
        return []
        
    statuses = data_state.status_db.get_status(dag_name=dag_name if dag_name else "crypto_pipeline")
    
    if task_name:
        statuses = [s for s in statuses if s.get('task_name') == task_name]
        
    return statuses[:limit]

# Background tasks
async def start_background_tasks():
    """Starts periodic sync tasks"""
    # Initial sync
    await data_state.initialize()
    
    while True:
        await asyncio.sleep(60) # Check every minute
        await data_state.sync_data_periodic()
