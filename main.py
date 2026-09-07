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
    # 1. Extraer texto completo del PDF
    texto_completo = ""
    with pdfplumber.open(file.file) as pdf:
        for page in pdf.pages:
            texto_extraido = page.extract_text()
            if texto_extraido:
                texto_completo += texto_extraido + "\n"
    
    # 2. Funciones de extracción inteligente
    def extraer_valor(patron, texto, por_defecto="No detectado"):
        resultado = re.search(patron, texto, re.IGNORECASE)
        return resultado.group(1).strip() if resultado else por_defecto

    # Extracción de campos clave
    v_fecha = extraer_valor(r'Fecha de Generación\s*([0-9/\s:]+)', texto_completo)
    v_cliente = extraer_valor(r'Razón Social\s+([A-Z\s]+?)\s+NIT', texto_completo)
    v_subtotal = extraer_valor(r'Subtotal\s+(\$[\d\,\.]+)', texto_completo)
    v_iva = extraer_valor(r'IVA 19%\s+(\$[\d\,\.]+)', texto_completo)
    v_total = extraer_valor(r'TOTAL\s+(\$[\d\,\.]+)', texto_completo)
    v_comision = extraer_valor(r'Comisión Administrativa.*?(\$[\d\,\.]+)', texto_completo)
    v_transporte = extraer_valor(r'Servicio Especial: transporte.*?\$\d+[\d\,\.]+\s+(\$[\d\,\.]+)', texto_completo)

    # Capturar la descripción completa del servicio
    desc_match = re.search(r'TOTAL ITEM\s*\n(.*?)(?=\n\d+\s+\d{3}|\nSubtotal)', texto_completo, re.DOTALL | re.IGNORECASE)
    if desc_match:
        v_servicio = desc_match.group(1).replace('\n', ' ').strip()
    else:
        v_servicio = "No se pudo extraer la descripción."

    # 3. Convertir el PDF a formato Base64 para el adjunto
    file.file.seek(0)
    pdf_bytes = file.file.read()
    archivo_b64 = base64.b64encode(pdf_bytes).decode('utf-8')

    # 4. Enviar todos los datos estructurados al puente de Google
    url_google = "https://script.google.com/macros/s/AKfycbyX1q3OxgC_ns_wc_Ml79jEqGaFav7mjT3Rv0s_5EzsAvCt0fcrBcHcNqPB21kGfhVOpA/exec"
    
    datos = {
        "archivo_nombre": file.filename,
        "fecha": v_fecha,
        "cliente": v_cliente,
        "servicio": v_servicio,
        "transporte": v_transporte,
        "comision": v_comision,
        "subtotal": v_subtotal,
        "iva": v_iva,
        "total": v_total,
        "archivo_b64": archivo_b64
    }
    
    requests.post(url_google, json=datos)

    return {"estado": "Completado", "mensaje": "Datos detallados y PDF enviados a Google"}
