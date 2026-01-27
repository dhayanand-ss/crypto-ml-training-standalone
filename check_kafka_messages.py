
import sys
import os
import json
import time

# Add parent directory to path to find utils if needed, though we might not need it for this simple script
sys.path.append(os.getcwd())

try:
    from quixstreams import Application
except ImportError:
    print("quixstreams not found. Please ensure it is installed.")
    sys.exit(1)

def main():
    broker_address = "localhost:9092"
    topic_name = "BTCUSDT"
    
    print(f"Connecting to Kafka at {broker_address}...")
    
    try:
        app = Application(
            broker_address=broker_address,
            consumer_group="debug-printer-v1",
            auto_offset_reset="earliest"
        )
        
        topic = app.topic(topic_name)
        
        print(f"Subscribed to topic: {topic_name}")
        print("Waiting for messages... (Press Ctrl+C to stop)")
        
        with app.get_consumer() as consumer:
            consumer.subscribe([topic.name])
            
            while True:
                msg = consumer.poll(1.0)
                
                if msg is None:
                    # No message available within timeout
                    # print("No message received...", end='\r')
                    continue
                    
                if msg.error():
                    print(f"Consumer error: {msg.error()}")
                    continue
                
                try:
                    value = msg.value()
                    # value is bytes, decode it
                    if isinstance(value, bytes):
                        value_str = value.decode('utf-8')
                        data = json.loads(value_str)
                        print(f"Received message: {data}")
                    else:
                        print(f"Received raw message: {value}")
                        
                except Exception as e:
                    print(f"Error processing message: {e}")
                    
    except KeyboardInterrupt:
        print("\nStopping consumer...")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
