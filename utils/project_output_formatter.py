"""
Project Output Formatter
Formats predictions to match the exact project output format:
- /prices/{coin} endpoint format
- /trl endpoint format
No ensemble, action, confidence, or summary fields
"""

import numpy as np
from typing import Dict, List, Optional, Any
import pandas as pd


class ProjectOutputFormatter:
    """
    Formats predictions to match project output specification.
    Returns ONLY the prediction arrays, no derived fields.
    """
    
    @staticmethod
    def format_prices_output(crypto_df: pd.DataFrame, 
                            lgb_versions: Optional[Dict[str, np.ndarray]] = None,
                            tst_versions: Optional[Dict[str, np.ndarray]] = None) -> List[Dict]:
        """
        Format predictions for /prices/{coin} endpoint.
        
        Args:
            crypto_df: DataFrame with price data (open_time, open, high, low, close, volume)
            lgb_versions: Dict with 'v1', 'v2', 'v3' keys containing LightGBM predictions
            tst_versions: Dict with 'v1', 'v2', 'v3' keys containing TST predictions
        
        Returns:
            List of dicts matching /prices/{coin} format:
            [
                {
                    "open_time": "2024-01-01T12:00:00Z",
                    "open": 50000.0,
                    "high": 51000.0,
                    "low": 49000.0,
                    "close": 50500.0,
                    "volume": 1000.0,
                    "tst_1": [0.2, 0.3, 0.5],
                    "tst_2": [0.15, 0.35, 0.5],
                    "tst_3": [0.1, 0.4, 0.5],
                    "lightgbm_1": [0.3, 0.2, 0.5],
                    "lightgbm_2": [0.25, 0.25, 0.5],
                    "lightgbm_3": [0.2, 0.3, 0.5]
                }
            ]
        """
        results = []
        
        # Determine minimum length
        min_len = len(crypto_df)
        if lgb_versions:
            for v in lgb_versions.values():
                if v is not None:
                    min_len = min(min_len, len(v))
        if tst_versions:
            for v in tst_versions.values():
                if v is not None:
                    min_len = min(min_len, len(v))
        
        # Align data - predictions typically align with end of crypto_df
        start_idx = len(crypto_df) - min_len
        
        for i in range(min_len):
            df_idx = start_idx + i
            if df_idx >= len(crypto_df):
                break
            
            row = crypto_df.iloc[df_idx]
            result = {
                "open_time": pd.Timestamp(row.get('open_time', row.name)).isoformat() + 'Z',
                "open": float(row['open']),
                "high": float(row['high']),
                "low": float(row['low']),
                "close": float(row['close']),
                "volume": float(row['volume'])
            }
            
            # Add TST predictions (v1, v2, v3) - DIFFERENT values per version
            if tst_versions:
                if tst_versions.get('v1') is not None and i < len(tst_versions['v1']):
                    result['tst_1'] = tst_versions['v1'][i].tolist()
                if tst_versions.get('v2') is not None and i < len(tst_versions['v2']):
                    result['tst_2'] = tst_versions['v2'][i].tolist()
                if tst_versions.get('v3') is not None and i < len(tst_versions['v3']):
                    result['tst_3'] = tst_versions['v3'][i].tolist()
            
            # Add LightGBM predictions (v1, v2, v3) - DIFFERENT values per version
            if lgb_versions:
                if lgb_versions.get('v1') is not None and i < len(lgb_versions['v1']):
                    result['lightgbm_1'] = lgb_versions['v1'][i].tolist()
                if lgb_versions.get('v2') is not None and i < len(lgb_versions['v2']):
                    result['lightgbm_2'] = lgb_versions['v2'][i].tolist()
                if lgb_versions.get('v3') is not None and i < len(lgb_versions['v3']):
                    result['lightgbm_3'] = lgb_versions['v3'][i].tolist()
            
            results.append(result)
        
        return results
    
    @staticmethod
    def format_trl_output(news_df: pd.DataFrame,
                         trl_versions: Optional[Dict[str, np.ndarray]] = None) -> List[Dict]:
        """
        Format predictions for /trl endpoint.
        
        Args:
            news_df: DataFrame with news articles (title, link, date)
            trl_versions: Dict with 'v1', 'v2', 'v3' keys containing TRL/FinBERT predictions
        
        Returns:
            List of dicts matching /trl format:
            [
                {
                    "title": "Article title",
                    "link": "https://...",
                    "date": "2024-01-01T12:00:00Z",
                    "trl_1": [0.02, 0.08, 0.90],
                    "trl_2": [0.01, 0.05, 0.94],
                    "trl_3": [0.03, 0.10, 0.87]
                }
            ]
        """
        results = []
        
        # Determine minimum length
        min_len = len(news_df)
        if trl_versions:
            for v in trl_versions.values():
                if v is not None:
                    min_len = min(min_len, len(v))
        
        for i in range(min_len):
            if i >= len(news_df):
                break
            
            row = news_df.iloc[i]
            result = {
                "title": str(row.get('title', '')),
                "link": str(row.get('link', '')),
                "date": pd.Timestamp(row.get('date', row.name)).isoformat() + 'Z'
            }
            
            # Add TRL predictions (v1, v2, v3) - DIFFERENT values per version
            if trl_versions:
                if trl_versions.get('v1') is not None and i < len(trl_versions['v1']):
                    result['trl_1'] = trl_versions['v1'][i].tolist()
                if trl_versions.get('v2') is not None and i < len(trl_versions['v2']):
                    result['trl_2'] = trl_versions['v2'][i].tolist()
                if trl_versions.get('v3') is not None and i < len(trl_versions['v3']):
                    result['trl_3'] = trl_versions['v3'][i].tolist()
            
            results.append(result)
        
        return results


















