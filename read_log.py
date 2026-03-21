
import sys

log_file = r"c:\Users\dhaya\crypto-ml-training-standalone\output_tst.log"
try:
    with open(log_file, "r", encoding="utf-16") as f:
        content = f.read()
except UnicodeError:
     with open(log_file, "r", encoding="utf-8") as f:
        content = f.read()

keywords = ["Saved ONNX model", "Model file not found", "conversion failed", "Registered", "Failed to register"]
found_lines = []

for line in content.splitlines():
    for kw in keywords:
        if kw in line:
            print(line)
            found_lines.append(line)

if not found_lines:
    print("No keywords found.")
