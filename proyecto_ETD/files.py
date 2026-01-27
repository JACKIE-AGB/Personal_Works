import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

model_id = "Qwen/Qwen3-Coder-30B-A3B-Instruct"

bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_compute_dtype=torch.bfloat16,
    bnb_4bit_quant_type="nf4"
)

tokenizer = AutoTokenizer.from_pretrained(model_id)
model = AutoModelForCausalLM.from_pretrained(
    model_id,
    quantization_config=bnb_config,
    device_map="auto",
    trust_remote_code=True
)

messages = [
    {"role": "system", "content": "Eres un experto programador senior que escribio un codigo limpio y eficiente"},
    {"role": "user", "content": "¿Como puedo implementear un middleware de autenticacion JWT en Node.js?"}
]

text = tokenizer.apply_chat_template(messages, tokenizer=False, add_generation_prompt=True)
model_inputs = tokenizer([text], return_tensors="pt").to(model.device)

generated_ids = model.generate(model_inputs.inputs_ids, max_new_tokens=1024)
response = tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0]

print(response)