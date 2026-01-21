from fastapi import FastAPI
from pydantic import BaseModel
from model import chatbot

app = FastAPI(title="Mini IA Conversacional")

class Message(BaseModel):
    text: str

@app.post("/chat")
def chat(message: Message):
    prompt = f"Usuario: {message.text}\nIA:"
    
    result = chatbot(
        prompt,
        max_length=50,
        do_sample=True,
        temperature=0.8
    )

    respuesta = result[0]["generated_text"].split("IA:")[-1].strip()

    return {
        "respuesta": respuesta
    }
