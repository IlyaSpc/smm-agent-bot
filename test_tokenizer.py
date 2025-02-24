from transformers import AutoTokenizer

model_name = "THUDM/chatglm3-6b"
cache_dir = "C:/cache/huggingface/"

print("Загрузка токенизатора...")
tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True, cache_dir=cache_dir)
print("Токенизатор загружен!")