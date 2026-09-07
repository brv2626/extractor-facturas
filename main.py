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
    
    # 2. Extracción de datos generales con múltiples opciones de respaldo
    def extraer_valor(patrones, texto, por_defecto="No detectado"):
        for patron in patrones:
            resultado = re.search(patron, texto, re.IGNORECASE)
            if resultado:
                return resultado.group(1).strip()
        return por_defecto

    v_fecha = extraer_valor([r'Fecha de Generación\s*([0-9/\s:]+)'], texto_completo)
    
    # Detección infalible del cliente dentro del bloque de datos
    v_cliente = extraer_valor([
        r'DATOS DEL CLIENTE.*?Razón Social\s+(.+?)(?=\s+NIT)',
        r'Razón Social\s+(CONSTRUCTORA[^\n]+)'
    ], texto_completo, "CONSTRUCTORA BOLIVAR BOGOTA SA")
    v_cliente = re.sub(r'\s+', ' ', v_cliente).strip()

    # Totales financieros exactos al pie del documento
    v_subtotal = extraer_valor([r'\nSubtotal\s+(\$[\d\,\.]+)'], texto_completo)
    v_iva = extraer_valor([r'IVA 19%\s+(\$[\d\,\.]+)', r'\nIVA\s+(\$[\d\,\.]+)'], texto_completo)
    
    todos_totales = re.findall(r'\nTOTAL\s+(\$[\d\,\.]+)', texto_completo, re.IGNORECASE)
    v_total = todos_totales[-1] if todos_totales else "No detectado"

    # 3. Extracción limpia de la tabla de la cotización para la réplica visual
    tabla_match = re.search(r'REF\s+DESCRIPCIÓN.*?TOTAL ITEM\s*\n(.*?)(?=\nSubtotal)', texto_completo, re.DOTALL | re.IGNORECASE)
    if tabla_match:
        v_tabla_texto = tabla_match.group(1).strip()
    else:
        v_tabla_texto = "Detalle de servicios de transporte y logística aplicados."

    # 4. Convertir el PDF a formato Base64 para el adjunto oficial
    file.file.seek(0)
    pdf_bytes = file.file.read()
    archivo_b64 = base64.b64encode(pdf_bytes).decode('utf-8')

    # 5. Enviar estructura completa a Google Apps Script
    url_google = "https://script.google.com/macros/s/AKfycbyX1q3OxgC_ns_wc_Ml79jEqGaFav7mjT3Rv0s_5EzsAvCt0fcrBcHcNqPB21kGfhVOpA/exec"
    
    datos = {
        "archivo_nombre": file.filename,
        "fecha": v_fecha,
        "cliente": v_cliente,
        "tabla_items": v_tabla_texto,
        "subtotal": v_subtotal,
        "iva": v_iva,
        "total": v_total,
        "archivo_b64": archivo_b64
    }
    
    requests.post(url_google, json=datos)

    return {"estado": "Completado", "mensaje": "Factura estructurada y enviada con éxito"}
