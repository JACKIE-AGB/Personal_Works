from transformers import pipeline

model = pipeline("summarization", model="facebook/bart-large-cnn")

text_to_summarize = """
En un pequeño pueblo costero, donde el mar parecía hablar con quienes se atrevían a escucharlo, se alzaba un faro antiguo que 
llevaba décadas sin encenderse. Los habitantes decían que ya no era necesario, pues los barcos modernos contaban con tecnología 
suficiente para navegar sin ayuda. Sin embargo, Mateo, un joven curioso que vivía cerca del acantilado, sentía que el faro
escondía algo más que polvo y telarañas.

Cada tarde, después de la escuela, Mateo subía la colina para observar el faro. Le intrigaba que, a pesar de estar abandonado, 
siempre se mantuviera intacto, como si alguien cuidara de él en secreto. Un día decidió entrar. La puerta chirrió al abrirse y 
el interior olía a sal y madera vieja. Mientras exploraba, encontró un cuaderno cubierto de arena. Al abrirlo, descubrió que 
pertenecía al último farero del pueblo.
"""

#respuesta
response = model(text_to_summarize)

#imprimir
print(response)

#TOMAR ESTE EJEMPLO COMO PLANTILLA