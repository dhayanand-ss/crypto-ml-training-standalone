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

    def train_grpo(self, news_df, crypto_df, epochs=2, batch_size=8, lr=1e-5, window_hours=12, threshold=0.005, **kwargs):
        """
        Implementation of training loop (SFT backed) to replace placeholder.
        Performs:
        1. Annotation of news based on crypto price changes.
        2. Supervised Fine-Tuning (SFT) of the FinBERT LoRA model.
        """
        import numpy as np
        from torch.utils.data import DataLoader, TensorDataset
        from torch.optim import AdamW
        from trainer.train_utils import annotate_news
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import accuracy_score

        print("[FinBERT] Annotating news data...")
        # 1. Annotate Data
        try:
            labeled_df = annotate_news(crypto_df, news_df, window_hours=window_hours, threshold=threshold)
            print(f"[FinBERT] Annotation complete. Used {len(labeled_df)} labeled samples.")
        except Exception as e:
            print(f"[FinBERT] Annotation failed: {e}. Returning empty history.")
            return {'train_loss': [], 'val_accuracy': [], 'train_surrogate': [], 'train_kl': []}

        texts = labeled_df['text'].tolist()
        labels = labeled_df['label'].tolist()

        # 2. Tokenize
        print(f"[FinBERT] Tokenizing {len(texts)} samples...")
        encodings = self.tokenizer(texts, truncation=True, padding=True, max_length=128, return_tensors='pt')
        
        input_ids = encodings['input_ids']
        attention_mask = encodings['attention_mask']
        labels_tensor = torch.tensor(labels)

        # 3. Create Dataset and Split
        dataset = TensorDataset(input_ids, attention_mask, labels_tensor)
        train_size = int(0.8 * len(dataset))
        val_size = len(dataset) - train_size
        if train_size == 0:
            print("[FinBERT] Dataset too small. Skipping training.")
            return {'train_loss': [], 'val_accuracy': [], 'train_surrogate': [], 'train_kl': []}

        train_dataset, val_dataset = torch.utils.data.random_split(dataset, [train_size, val_size])
        
        train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
        val_loader = DataLoader(val_dataset, batch_size=batch_size)

        optimizer = AdamW(self.model.parameters(), lr=lr)
        criterion = nn.CrossEntropyLoss()

        history = {
            'train_loss': [],
            'train_surrogate': [], # Dummy for GRPO compatibility
            'train_kl': [],       # Dummy
            'val_accuracy': []
        }

        # 4. Training Loop
        print(f"[FinBERT] Starting training for {epochs} epochs...")
        self.model.train()
        
        for epoch in range(epochs):
            total_loss = 0
            steps = 0
            
            for batch in train_loader:
                b_input_ids, b_attn_mask, b_labels = [b.to(self.device) for b in batch]
                
                self.model.zero_grad()
                
                outputs = self.model(input_ids=b_input_ids, attention_mask=b_attn_mask, labels=b_labels)
                loss = outputs.loss
                
                loss.backward()
                optimizer.step()
                
                total_loss += loss.item()
                steps += 1
            
            avg_train_loss = total_loss / steps if steps > 0 else 0
            history['train_loss'].append(avg_train_loss)
            history['train_surrogate'].append(0.0) # Placeholder
            history['train_kl'].append(0.0)        # Placeholder
            
            # Validation
            self.model.eval()
            val_preds = []
            val_true = []
            with torch.no_grad():
                for batch in val_loader:
                    b_input_ids, b_attn_mask, b_labels = [b.to(self.device) for b in batch]
                    outputs = self.model(input_ids=b_input_ids, attention_mask=b_attn_mask)
                    logits = outputs.logits
                    preds = torch.argmax(logits, dim=1).cpu().numpy()
                    val_preds.extend(preds)
                    val_true.extend(b_labels.cpu().numpy())
            
            val_acc = accuracy_score(val_true, val_preds) if val_true else 0.0
            history['val_accuracy'].append(val_acc)
            
            print(f"Epoch {epoch+1}/{epochs} | Loss: {avg_train_loss:.4f} | Val Acc: {val_acc:.4f}")
            self.model.train()
            
        return history
