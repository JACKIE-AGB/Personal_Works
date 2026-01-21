from transformers import pipeline

chatbot = pipeline(
    "text-generation",
    model="distilgpt2"
)

#copiar en navegador: uvicorn app:app --host 0.0.0.0 --port 8000