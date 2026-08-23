import os
import argparse
import torch
from unsloth import FastLanguageModel
from unsloth.chat_templates import get_chat_template
from datasets import load_dataset
from trl import SFTTrainer
from transformers import TrainingArguments

def main():
    parser = argparse.ArgumentParser(description="Fine-tune Qwen 2.5 3B using Unsloth and QLoRA.")
    parser.add_argument("--dataset", type=str, default="train.jsonl", help="Path to the JSONL training dataset")
    parser.add_argument("--steps", type=int, default=8, help="Number of training steps")
    parser.add_argument("--context_length", type=int, default=1024, help="Max sequence length")
    parser.add_argument("--output_name", type=str, default="ats_agent_qwen", help="Name of the output GGUF file")
    args = parser.parse_args()

    if not os.path.exists(args.dataset):
        raise FileNotFoundError(f"❌ Dataset not found: {args.dataset}. Please ensure the file exists.")

    print(f"⚙️ Initializing Unsloth 4-bit QLoRA Training for {args.output_name}...")
    
    # ==========================================
    # 1. MODEL CONFIGURATION
    # ==========================================
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name="unsloth/Qwen2.5-3B-Instruct",
        max_seq_length=args.context_length,
        dtype=None, # Auto-detects based on hardware
        load_in_4bit=True,
    )

    # Apply LoRA Adapters
    model = FastLanguageModel.get_peft_model(
        model,
        r=16,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        lora_alpha=16,
        lora_dropout=0, 
        bias="none",
        use_gradient_checkpointing="unsloth", 
        random_state=3407,
    )

    # ==========================================
    # 2. DATASET PREPARATION (ChatML)
    # ==========================================
    tokenizer = get_chat_template(
        tokenizer,
        chat_template="chatml",
        mapping={"role": "role", "content": "content", "user": "user", "assistant": "assistant"}
    )

    def formatting_prompts_func(examples):
        convos = examples["messages"]
        texts = [tokenizer.apply_chat_template(convo, tokenize=False, add_generation_prompt=False) for convo in convos]
        return {"text": texts}

    print(f"📖 Loading dataset from {args.dataset}...")
    dataset = load_dataset("json", data_files=args.dataset, split="train")
    dataset = dataset.map(formatting_prompts_func, batched=True)

    # ==========================================
    # 3. TRAINING ENGINE
    # ==========================================
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        dataset_text_field="text",
        max_seq_length=args.context_length,
        dataset_num_proc=2,
        packing=False,
        args=TrainingArguments(
            per_device_train_batch_size=2,
            gradient_accumulation_steps=4,
            warmup_steps=2,
            max_steps=args.steps,
            learning_rate=2e-4,
            fp16=not torch.cuda.is_bf16_supported(),
            bf16=torch.cuda.is_bf16_supported(),
            logging_steps=1,
            optim="adamw_8bit",
            weight_decay=0.01,
            lr_scheduler_type="linear",
            seed=3407,
            output_dir="training_outputs",
        ),
    )

    print(f"🚀 Starting training for {args.steps} steps...")
    trainer.train()
    print("✅ Training Complete!")

    # ==========================================
    # 4. EXPORT TO GGUF
    # ==========================================
    print(f"📦 Exporting model to {args.output_name} (Q4_K_M GGUF format)...")
    model.save_pretrained_gguf(args.output_name, tokenizer, quantization_method="q4_k_m")
    print(f"🎉 Success! You can now load {args.output_name}-unsloth.Q4_K_M.gguf into Ollama.")

if __name__ == "__main__":
    main()
