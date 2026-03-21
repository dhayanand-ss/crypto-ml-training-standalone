import sys
sys.path.append(r'c:\Users\dhaya\crypto-ml-training-standalone')
import pandas as pd
from utils.producer_consumer.consumer import preprocess_data

df = pd.read_csv('data/btcusdt.csv', nrows=100)
X = preprocess_data(df)
print('Shape:', X.shape)
