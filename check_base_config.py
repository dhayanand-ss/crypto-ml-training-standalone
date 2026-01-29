
from transformers import AutoConfig

def check_base_mapping():
    model_name = "ProsusAI/finbert"
    try:
        config = AutoConfig.from_pretrained(model_name)
        print("Base Model Label Mapping:")
        print(config.id2label)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_base_mapping()
