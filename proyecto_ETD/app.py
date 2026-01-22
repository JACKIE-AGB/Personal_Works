from fastapi import FastAPI, File, UploadFile

app = FastAPI()

@app.post("/predict")
async def predict(file: UploadFile = File(...)):
    ...