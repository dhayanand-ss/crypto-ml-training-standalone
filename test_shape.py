import pandas as pd
import sys
sys.path.append(r'c:\Users\dhaya\crypto-ml-training-standalone')
from utils.producer_consumer.consumer import preprocess_data
df = pd.read_csv('data/btcusdt.csv', nrows=100)
X = preprocess_data(df)
print('Shape:', X.shape)
