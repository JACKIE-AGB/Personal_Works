import io
import torch
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import Response
from PIL import Image

from super_image import EdsrModel, ImageLoader


# =========================
# CARGA DEL MODELO (1 sola vez)
# =========================
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

model = EdsrModel.from_pretrained(
    "Legitking4pf/Real-ESRGAN-Upscaler"
).to(DEVICE)

model.eval()


# =========================
# FASTAPI
# =========================
app = FastAPI(title="Real-ESRGAN Upscaler API")


@app.post("/upscale")
async def upscale_image(file: UploadFile = File(...)):
    # Leer imagen como bytes
    image_bytes = await file.read()

    # Convertir a PIL
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    # PIL → Tensor
    input_tensor = ImageLoader.load_image(image)
    input_tensor = input_tensor.to(DEVICE)

    # Inferencia
    with torch.no_grad():
        preds = model(input_tensor)

    # Tensor → PIL
    output_image = ImageLoader.to_pil(preds)

    # Guardar en buffer
    buf = io.BytesIO()
    output_image.save(buf, format="PNG")
    buf.seek(0)

    return Response(
        content=buf.getvalue(),
        media_type="image/png"
    )