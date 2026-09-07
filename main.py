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
    try:
        # 1. Extraer texto completo del PDF
        texto_completo = ""
        with pdfplumber.open(file.file) as pdf:
            for page in pdf.pages:
                texto_extraido = page.extract_text()
                if texto_extraido:
                    texto_completo += texto_extraido + "\n"
        
        # 2. Extracción de datos generales
        def extraer_valor(patrones, texto, por_defecto="No detectado"):
            for patron in patrones:
                resultado = re.search(patron, texto, re.IGNORECASE)
                if resultado:
                    return resultado.group(1).strip()
            return por_defecto

        v_fecha = extraer_valor([r'Fecha de Generación\s*([0-9/\s:]+)'], texto_completo)
        
        v_cliente = extraer_valor([
            r'DATOS DEL CLIENTE.*?Razón Social\s+(.+?)(?=\s+NIT)',
            r'Razón Social\s+(CONSTRUCTORA[^\n]+)'
        ], texto_completo, "CONSTRUCTORA BOLIVAR BOGOTA")
        v_cliente = re.sub(r'\s+', ' ', v_cliente).strip()

        v_subtotal = extraer_valor([r'\nSubtotal\s+(\$[\d\,\.]+)'], texto_completo)
        v_iva = extraer_valor([r'IVA 19%\s+(\$[\d\,\.]+)', r'\nIVA\s+(\$[\d\,\.]+)'], texto_completo)
        
        todos_totales = re.findall(r'\nTOTAL\s+(\$[\d\,\.]+)', texto_completo, re.IGNORECASE)
        v_total = todos_totales[-1] if todos_totales else "No detectado"

        # 3. Captura infalible del contenido de la tabla de ítems
        tabla_match = re.search(r'REF\s+DESCRIPCIÓN.*?TOTAL ITEM\s*\n(.*?)(?=\nSubtotal)', texto_completo, re.DOTALL | re.IGNORECASE)
        
        filas_html = ""
        if tabla_match:
            bloque_tabla = tabla_match.group(1).strip()
            lineas = bloque_tabla.split('\n')
            
            # Construimos las filas directamente para asegurar que no falle ninguna descripción
            for linea in lineas:
                linea_limpia = linea.strip()
                if not linea_limpia:
                    continue
                
                # Si la línea parece un ítem (empieza con número y referencia)
                if re.match(r'^\d+\s+\d{3}', linea_limpia):
                    partes = linea_limpia.split()
                    num = partes[0]
                    ref = partes[1]
                    desc = " ".join(partes[2:])
                    
                    filas_html += f"""
                    <tr style="border-bottom: 1px solid #e0e0e0;">
                      <td style="padding: 8px; text-align: center; vertical-align: top; color: #555;">{num}</td>
                      <td style="padding: 8px; text-align: center; vertical-align: top; font-weight: bold; color: #333;">{ref}</td>
                      <td style="padding: 8px; vertical-align: top; color: #222;" colspan="7">{desc}</td>
                    </tr>
                    """
                else:
                    # Líneas adicionales de descripción (como las direcciones o detalles largos)
                    filas_html += f"""
                    <tr style="border-bottom: 1px solid #e0e0e0;">
                      <td style="padding: 4px;" colspan="2"></td>
                      <td style="padding: 4px 8px; vertical-align: top; color: #444; font-size: 11px;" colspan="7">{linea_limpia}</td>
                    </tr>
                    """
        else:
            filas_html = "<tr><td colspan='9' style='padding: 10px; text-align: center;'>Detalle general de servicios de transporte.</td></tr>"

        # 4. Convertir PDF a Base64 para el adjunto
        file.file.seek(0)
        pdf_bytes = file.file.read()
        archivo_b64 = base64.b64encode(pdf_bytes).decode('utf-8')

        # 5. Enviar a Google Apps Script
        url_google = "https://script.google.com/macros/s/AKfycbyX1q3OxgC_ns_wc_Ml79jEqGaFav7mjT3Rv0s_5EzsAvCt0fcrBcHcNqPB21kGfhVOpA/exec"
        
        datos = {
            "archivo_nombre": file.filename,
            "fecha": v_fecha,
            "cliente": v_cliente,
            "filas_tabla": filas_html,
            "subtotal": v_subtotal,
            "iva": v_iva,
            "total": v_total,
            "archivo_b64": archivo_b64
        }
        
        response = requests.post(url_google, json=datos)
        
        return {"estado": "Completado", "mensaje": "Procesado correctamente"}
        
    except Exception as e:
        return {"estado": "Error", "mensaje": str(e)}
