from transformers import pipeline
import torch

#crear pipeline para la generacion del texto
pipe = pipeline(
    "text-generation",
    model="meta-llama/Llama-3.1-8B-Instruct",
    torch_dtype=torch.float16,
    device_map="auto",
    trust_remote_code=True
)

#crear los mensajes
messages = [
    {"role": "system", "content": "Eres un asistente util en español"},
    {"role": "user", "content": "¿Como puedo aprender a programar?"}
]

#generar la respuesta
outputs = pipe(
    messages,
    max_new_tokens=256,
    temperature=0.7,
    top_p=0.9,
    do_sample=True
)

print(outputs[0]['generated_text'][-1]['content'])