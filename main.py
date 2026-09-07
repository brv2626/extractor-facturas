from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
import pdfplumber
import requests

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_methods=["POST"],
)

@app.post("/procesar-factura/")
async def procesar_factura(file: UploadFile = File(...)):
    with pdfplumber.open(file.file) as pdf:
        texto = ""
        for page in pdf.pages:
            tablas = page.extract_tables()
            texto += f"Tablas encontradas: {tablas}\n"
            
    # Envío de datos al puente de Google
    url_google = "https://script.google.com/macros/s/AKfycbyX1q3OxgC_ns_wc_Ml79jEqGaFav7mjT3Rv0s_5EzsAvCt0fcrBcHcNqPB21kGfhVOpA/exec"
    datos = {
        "asunto": f"Desglose automatizado: {file.filename}",
        "mensaje": f"Datos extraídos de la factura:\n\n{texto}"
    }
    requests.post(url_google, json=datos)

    return {"estado": "Completado", "mensaje": "Datos enviados por Google"}
