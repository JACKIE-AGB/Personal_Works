from transformers import pipeline

pipe = pipeline(
    "text-generation",
    model="google/functiongemma-270m-it",
    device_map="auto"
)

prompt = """###instruction:
Resume el siguiente texto.

### Input:
Los modelos de lenguaje natural se entrenan con grandes cantidades de datos

###Response:
"""

result = pipe(
    prompt,
    max_new_tokens=100,
    temperature=0.6
)

print(result[0]["generated-text"])