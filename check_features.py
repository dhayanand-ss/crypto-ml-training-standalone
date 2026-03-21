import pandas as pd
import sys
sys.path.append(r'c:\Users\dhaya\crypto-ml-training-standalone')
from trainer.train_utils import preprocess_crypto

df = pd.DataFrame({
    'open_time': pd.date_range('2023-01-01', periods=100, freq='1min'),
    'open': [1.0]*100,
    'high': [1.2]*100,
    'low': [0.8]*100,
    'close': [1.1]*100,
    'volume': [100.0]*100
})
df['taker_base'] = 10.0
df['taker_quote'] = 10.0
X, y = preprocess_crypto(df)
print(f'Length='+str(len(X.columns)))
print(list(X.columns))
