from transformers import pipeline

model = pipeline("summarization", model="facebook/bart-large-cnn")

text_to_summarize = "La abuela tejía atardeceres con su aguja de plata en el viejo balcón. Cada puntada era un pájaro que volaba de la lana escarlata y dorada, un rayo de sol " \
"que se quedaba atrapado en la madeja para iluminar las tardes grises del barrio. La gente levantaba la vista y sonreía al ver cómo el horizonte se vestía de nubes rosadas y de " \
"destelos anaranjados."

response = model(text_to_summarize)

print(response)