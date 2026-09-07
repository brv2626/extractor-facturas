from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
import pdfplumber
import requests
import re

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
            texto_extraido = page.extract_text()
            if texto_extraido:
                texto_completo += texto_extraido + "\n"
                
    # Extracción inteligente de valores
    def extraer_valor(patron, texto):
        resultado = re.search(patron, texto, re.IGNORECASE)
        return resultado.group(1) if resultado else "No detectado"

    v_subtotal = extraer_valor(r'\nSubtotal\s+(\$[\d\,\.]+)', texto_completo)
    v_iva = extraer_valor(r'\nIVA 19%\s+(\$[\d\,\.]+)', texto_completo)
    v_total = extraer_valor(r'\nTOTAL\s+(\$[\d\,\.]+)', texto_completo)
    v_comision = extraer_valor(r'Comisi.n.*?(\$[\d\,\.]+)\s+IVA', texto_completo)
    
    # Plantilla ejecutiva para el correo
    mensaje_limpio = f"""Hola,

Se ha procesado automáticamente una nueva factura de Olatur.
Documento original: {file.filename}

=========================================
RESUMEN FINANCIERO DEL SERVICIO
=========================================

▶ Comisión Admin:        {v_comision}
-----------------------------------------
▶ SUBTOTAL:              {v_subtotal}
▶ IVA (19%):             {v_iva}
▶ TOTAL A PAGAR:         {v_total}

=========================================
(Valores extraídos de la representación gráfica del software Dataico).
"""

    url_google = "https://script.google.com/macros/s/AKfycbyX1q3OxgC_ns_wc_Ml79jEqGaFav7mjT3Rv0s_5EzsAvCt0fcrBcHcNqPB21kGfhVOpA/exec"
    datos = {
        "asunto": f"Factura Procesada: {file.filename}",
        "mensaje": mensaje_limpio
    }
    requests.post(url_google, json=datos)

    return {"estado": "Completado", "mensaje": "Datos estructurados enviados"}
