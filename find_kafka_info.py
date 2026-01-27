import requests
import re
import sys

def get_cluster_id():
    try:
        # Control Center usually redirects to the cluster page or has it in the initial HTML
        # But it's often a Single Page App (SPA).
        # Let's check the API endpoint for clusters
        # Common endpoint: /2.0/clusters
        
        # Try metadata endpoint (internal API used by UI)
        # Note: Port 9021 is Control Center
        
        # Method 1: Check if we can get it from the main page HTML
        response = requests.get("http://localhost:9021", timeout=5)
        content = response.text
        
        # Look for cluster ID pattern in bootstrapped data
        # dynamic-resources/clusters/<ID>
        # or "clusterId":"<ID>"
        
        match = re.search(r'"clusterId":"([a-zA-Z0-9_-]+)"', content)
        if match:
            return match.group(1)
            
        print("Could not parse Cluster ID from HTML, trying API...")
        
        # API method might be hidden/internal, but let's try REST Proxy status on 8082
        # The REST Proxy often reveals the cluster ID of the Kafka cluster it's connected to.
        try:
            resp_rest = requests.get("http://localhost:8082/v3/clusters", timeout=5)
            if resp_rest.ok:
                data = resp_rest.json()
                if data and 'data' in data and len(data['data']) > 0:
                    return data['data'][0]['cluster_id']
        except Exception as e:
            print(f"REST Proxy check failed: {e}")
            
        return None

    except Exception as e:
        print(f"Error fetching Cluster ID: {e}")
        return None

def get_topics():
    try:
        response = requests.get("http://localhost:8082/topics", timeout=5)
        if response.ok:
            return response.json()
        else:
            print(f"Failed to fetch topics: {response.status_code}")
            return []
    except Exception as e:
        print(f"Error fetching topics: {e}")
        return []

if __name__ == "__main__":
    print("Checking Kafka status...")
    
    topics = get_topics()
    print(f"Available Topics: {topics}")
    
    cluster_id = get_cluster_id()
    if cluster_id:
        print(f"Cluster ID: {cluster_id}")
        print(f"Direct Link: http://localhost:9021/clusters/{cluster_id}/management/topics/BTCUSDT/message-viewer")
    else:
        print("Cluster ID could not be determined automatically.")
