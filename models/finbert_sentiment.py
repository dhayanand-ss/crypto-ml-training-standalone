import torch
import torch.nn as nn
from transformers import AutoModelForSequenceClassification, AutoTokenizer
from peft import get_peft_model, LoraConfig, TaskType

class FinBERTSentimentAnalyzer(nn.Module):
    """
    FinBERT Sentiment Analyzer with LoRA support
    """
    def __init__(self, model_name="ProsusAI/finbert", lora_rank=4, device=None):
        super().__init__()
        self.device = device if device else ("cuda" if torch.cuda.is_available() else "cpu")
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        
        # Load base model
        base_model = AutoModelForSequenceClassification.from_pretrained(model_name, num_labels=3)
        
        # Apply LoRA if rank > 0
        if lora_rank > 0:
            peft_config = LoraConfig(
                task_type=TaskType.SEQ_CLS,
                inference_mode=False,
                r=lora_rank,
                lora_alpha=16,
                lora_dropout=0.1,
                target_modules=["query", "value"]  # FinBERT specific modules
            )
            self.model = get_peft_model(base_model, peft_config)
            self.model.print_trainable_parameters()
        else:
            self.model = base_model
            
        self.model.to(self.device)

    def forward(self, input_ids, attention_mask=None, labels=None):
        return self.model(input_ids=input_ids, attention_mask=attention_mask, labels=labels)

    def save_model(self, path, tokenizer_path=None):
        """Save model state dict and tokenizer"""
        torch.save(self.model.state_dict(), path)
        if tokenizer_path:
            self.tokenizer.save_pretrained(tokenizer_path)

    def train_grpo(self, news_df, crypto_df, **kwargs):
        """
        Placeholder for GRPO training logic
        Pass-through to allow external training scripts to wrap this class
        """
        # In the real codebase, this would contain the PPO/GRPO logic
        # For restoration purposes, we keep the class structure intact
        # The TRL training script (trl_train.py) usually imports this class
        # expecting specific methods
        
        # Simple history placeholder to return expected structure
        history = {
            'train_loss': [],
            'train_surrogate': [], 
            'train_kl': [],
            'val_accuracy': []
        }
        return history
