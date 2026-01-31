import torch
import fitz
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline, BitsAndBytesConfig

model_id = "microsoft/Phi-3-mini-4k-instruct"

quantization_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_use_double_quant=True,
    bnb_4bit_compute_dtype=torch.bfloat16 # Usa torch.float16 si tu GPU es antigua
)

tokenizer = AutoTokenizer.from_pretrained("microsoft/Phi-3-mini-4k-instruct")

model = AutoModelForCausalLM.from_pretrained(
    model_id,
    device_map="auto",
    torch_dtype="auto",
    load_in_4bit=True,
    trust_remote_code=True,
    quantization_config=quantization_config
)

phi3_pipe = pipeline("text-generation", model=model, tokenizer=tokenizer)

def extraer_texto_pdf(ruta_pdf):
    texto=""
    with fitz.opn(ruta_pdf) as doc:
        for pagina in doc:
            texto += pagina.get_text()
    return texto

ruta_del_archivo = "EMPRESA DE INTERÉS.pdf"

try:
  contexto_archivo = extraer_texto_pdf(ruta_del_archivo)
  print("PDF cargado correctamente.\n")

  pregunta = "¿Cual es la matricula del alumno?"

  prompt = f"<|user|>\nBasado en este texto: {contexto_archivo}\nPregunta: {pregunta}<|end|>\n<|assistant|>"

  outputs = phi3_pipe(prompt, max_new_tokens=200, do_sample=True, temperature=0.1)

  print("---Respuesta del modelo ---")
  print(outputs[0]['generated_text'].split("<|assistant|>")[-1].strip())

except Exception as e:
  print(f"Error al cargar el PDF: {e}")