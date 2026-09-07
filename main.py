from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
import pdfplumber
import requests
import re
import base64

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_methods=["POST"],
)

@app.post("/procesar-factura/")
async def procesar_factura(file: UploadFile = File(...)):
    # 1. Extraer texto del PDF
    texto_completo = ""
    with pdfplumber.open(file.file) as pdf:
        for page in pdf.pages:
            texto_extraido = page.extract_text()
            if texto_extraido:
                texto_completo += texto_extraido + "\n"
    
    # 2. Buscar "Total" y "Descripción del servicio"
    def extraer_valor(patron, texto):
        resultado = re.search(patron, texto, re.IGNORECASE)
        return resultado.group(1) if resultado else "No detectado"

    v_total = extraer_valor(r'\nTOTAL\s+(\$[\d\,\.]+)', texto_completo)
    
    # Atrapa todo el texto de la descripción del servicio
    desc_match = re.search(r'TOTAL ITEM\s*\n(.*?)(?=\n\d+\s+\d{3}|\nSubtotal)', texto_completo, re.DOTALL | re.IGNORECASE)
    if desc_match:
        v_servicio = desc_match.group(1).replace('\n', ' ').strip()
    else:
        v_servicio = "No se pudo extraer la descripción."

    # 3. Convertir el PDF a formato Base64 para adjuntarlo en el correo
    file.file.seek(0)
    pdf_bytes = file.file.read()
    archivo_b64 = base64.b64encode(pdf_bytes).decode('utf-8')

    # 4. Enviar todo al puente de Google (Tu URL fija)
    url_google = "https://script.google.com/macros/s/AKfycbyX1q3OxgC_ns_wc_Ml79jEqGaFav7mjT3Rv0s_5EzsAvCt0fcrBcHcNqPB21kGfhVOpA/exec"
    
    datos = {
        "archivo_nombre": file.filename,
        "servicio": v_servicio,
        "total": v_total,
        "archivo_b64": archivo_b64
    }
    
    requests.post(url_google, json=datos)

    return {"estado": "Completado", "mensaje": "Datos y PDF enviados a Google"}
