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
        texto_completo = ""
        for page in pdf.pages:
            # Extrae absolutamente todo el texto visible, sin importar el formato
            texto_extraido = page.extract_text()
            if texto_extraido:
                texto_completo += texto_extraido + "\n"
            
    # Envío de datos al puente de Google
    url_google = "https://script.google.com/macros/s/AKfycbyX1q3OxgC_ns_wc_Ml79jEqGaFav7mjT3Rv0s_5EzsAvCt0fcrBcHcNqPB21kGfhVOpA/exec"
    datos = {
        "asunto": f"Desglose automatizado: {file.filename}",
        "mensaje": f"Datos extraídos de la factura:\n\n{texto_completo}"
    }
    requests.post(url_google, json=datos)

    return {"estado": "Completado", "mensaje": "Datos enviados por Google"}
