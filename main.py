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
    ], texto_completo, "CONSTRUCTORA BOLIVAR BOGOTA SA")
    v_cliente = re.sub(r'\s+', ' ', v_cliente).strip()

    v_subtotal = extraer_valor([r'\nSubtotal\s+(\$[\d\,\.]+)'], texto_completo)
    v_iva = extraer_valor([r'IVA 19%\s+(\$[\d\,\.]+)', r'\nIVA\s+(\$[\d\,\.]+)'], texto_completo)
    
    todos_totales = re.findall(r'\nTOTAL\s+(\$[\d\,\.]+)', texto_completo, re.IGNORECASE)
    v_total = todos_totales[-1] if todos_totales else "No detectado"

    # 3. Extracción estructurada de los ítems de la tabla para convertirlos en filas HTML reales
    tabla_match = re.search(r'REF\s+DESCRIPCIÓN.*?TOTAL ITEM\s*\n(.*?)(?=\nSubtotal)', texto_completo, re.DOTALL | re.IGNORECASE)
    
    filas_html = ""
    if tabla_match:
        contenido_tabla = tabla_match.group(1).strip()
        # Separar los ítems basándonos en el número de fila inicial (ej. "1 004", "2 002", "3 003")
        items_brutos = re.split(r'\n(?=\d+\s+\d{3})', contenido_tabla)
        
        for item in items_brutos:
            lineas = [l.strip() for l in item.split('\n') if l.strip()]
            if not lineas:
                continue
            
            primera_linea = lineas[0]
            partes_cabeza = primera_linea.split()
            
            if len(partes_cabeza) >= 3:
                num_item = partes_cabeza[0]
                ref_item = partes_cabeza[1]
                # El resto de la primera línea y las líneas siguientes forman la descripción y precios
                resto_texto = " ".join(partes_cabeza[2:])
                if len(lineas) > 1:
                    resto_texto += " " + " ".join(lineas[1:])
                
                # Intentamos extraer cantidades, precios y totales del texto del ítem mediante expresiones regulares
                cant_match = re.search(r'\b(1|2|3|4|5|6|7|8|9|10)\s+(EA|94|UND)\b', resto_texto, re.IGNORECASE)
                cant = cant_match.group(1) if cant_match else "1"
                um = cant_match.group(2) if cant_match else "EA"
                
                precios = re.findall(r'\$[\d\,\.]+', resto_texto)
                precio_unit = precios[0] if len(precios) > 0 else ""
                subtotal_item = precios[1] if len(precios) > 1 else (precios[0] if len(precios) == 1 else "")
                total_item = precios[2] if len(precios) > 2 else subtotal_item
                
                imp = "IVA 19%" if "IVA" in resto_texto.upper() else ""
                
                # Limpiar la descripción quitando los precios para que no se dupliquen visualmente
                descripcion_limpia = resto_texto
                for p in precios:
                    descripcion_limpia = descripcion_limpia.replace(p, "")
                descripcion_limpia = re.sub(r'\b(1|2|3|4|5|6|7|8|9|10)\s+(EA|94|UND)\b', '', descripcion_limpia, flags=re.IGNORECASE)
                descripcion_limpia = re.sub(r'IVA\s*19%', '', descripcion_limpia, flags=re.IGNORECASE)
                descripcion_limpia = re.sub(r'\s+', ' ', descripcion_limpia).strip()

                # Construir la fila real de la tabla HTML
                filas_html += f"""
                <tr style="border-bottom: 1px solid #e0e0e0;">
                  <td style="padding: 10px; text-align: center; vertical-align: top; color: #555;">{num_item}</td>
                  <td style="padding: 10px; text-align: center; vertical-align: top; font-weight: bold; color: #333;">{ref_item}</td>
                  <td style="padding: 10px; vertical-align: top; color: #222; font-size: 12px;">{descripcion_limpia}</td>
                  <td style="padding: 10px; text-align: center; vertical-align: top;">{cant}</td>
                  <td style="padding: 10px; text-align: center; vertical-align: top;">{um}</td>
                  <td style="padding: 10px; text-align: right; vertical-align: top; white-space: nowrap;">{precio_unit}</td>
                  <td style="padding: 10px; text-align: center; vertical-align: top; color: #c62828; font-size: 11px;">{imp}</td>
                  <td style="padding: 10px; text-align: right; vertical-align: top; white-space: nowrap;">{subtotal_item}</td>
                  <td style="padding: 10px; text-align: right; vertical-align: top; font-weight: bold; white-space: nowrap; color: #111;">{total_item}</td>
                </tr>
                """

    if not filas_html:
        filas_html = "<tr><td colspan='9' style='padding: 15px; text-align: center;'>No se pudieron parsear los ítems de la tabla.</td></tr>"

    # 4. Convertir PDF a Base64 para adjunto
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
    
    requests.post(url_google, json=datos)

    return {"estado": "Completado", "mensaje": "Tabla estructurada enviada con éxito"}
