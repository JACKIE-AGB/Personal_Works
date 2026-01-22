import gradio as gr
from transformers import pipeline

generator = pipeline("text2text-generation", model="google/flan-t5-large")

def chatbot_response(message, history):
    prompt = "You are a helpful AI assistant. Respond to the following conversation:\n"
    for user_msg, bot_msg in history:
        prompt += f"user: {user_msg}\nAsistant: {bot_msg}\n"
    prompt += f"user: {message}\nAssistant"


    response = generator(prompt, max_length=2048, do_sample=True, temperature=0.95)[0]['generated_text']
    return response.strip()


demo = gr.ChatInterface(
    fn=chatbot_response,
    title="FLAN-T5 Chatbot",
    description="Chat whit an AI powered by google/flan-t5-large. Type your message below: ",
    examples=["Hello, how are you?", "What's the capital of France", "Tell me a joke"],
    cache_examples=False,
    theme="soft"
)

demo.launch()