try:
    with open("fastapi_8018_log.txt", "r", encoding="utf-16") as f:
        print(f.read())
except Exception as e:
    print(f"Error reading file: {e}")
