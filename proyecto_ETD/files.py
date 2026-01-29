from transformers import pipeline

text = pipeline(
    "text-generation",
    model="mistralai/Mistral-7B-Instruct-v0.1",
    device=0
)

text(
    "explain what artifical intelligence is in spanish",
    max_new_tokens = 150,
    do_sample=True,
    temperature=0.7,
    top_p=0.9
)