from fastapi import FastAPI, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
import pdfplumber
import requests
import json
import re
import base64

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/procesar-factura/")
async def procesar_factura(file: UploadFile = File(...), tipo_registro: str = Form("Nueva Cotización")):
    try:
        texto_completo = ""
        with pdfplumber.open(file.file) as pdf:
            for page in pdf.pages:
                texto_extraido = page.extract_text()
                if texto_extraido:
                    texto_completo += texto_extraido + "\n"
        
        def extraer_valor(patrones, texto, por_defecto="No detectado"):
            for patron in patrones:
                resultado = re.search(patron, texto, re.IGNORECASE)
                if resultado:
                    return resultado.group(1).strip()
            return por_defecto

        v_fecha = extraer_valor([r'Fecha de Generación\s*([0-9/\s:]+)'], texto_completo)
        
        v_num_cotizacion = extraer_valor([r'\n(Q\d+)\s*\n', r'Cotización.*?(Q\d+)'], texto_completo, "Cotización")
        if not v_num_cotizacion.startswith("Q"):
            match_nombre = re.search(r'(Q\d+)', file.filename, re.IGNORECASE)
            v_num_cotizacion = match_nombre.group(1).upper() if match_nombre else "Cotización"

        # --- NUEVA EXTRACCIÓN DINÁMICA DE CLIENTE Y NIT ---
        match_cliente = re.search(r'DATOS DEL CLIENTE[\s\S]*?Razón Social\s+([^\n]+)', texto_completo, re.IGNORECASE)
        if not match_cliente:
            # Respaldo si el PDF se lee de forma horizontal
            match_cliente = re.search(r'Razón Social.*?Razón Social\s+([^\n]+)', texto_completo, re.IGNORECASE)
            
        v_cliente_nombre = match_cliente.group(1).strip() if match_cliente else "Cliente No Detectado"
        v_cliente_nombre = re.sub(r'\s+NIT.*$', '', v_cliente_nombre, flags=re.IGNORECASE).strip()

        match_nit = re.search(r'DATOS DEL CLIENTE[\s\S]*?NIT\s+([0-9\-]+)', texto_completo, re.IGNORECASE)
        if not match_nit:
            # Respaldo si el PDF se lee de forma horizontal
            match_nit = re.search(r'NIT.*?NIT\s+([0-9\-]+)', texto_completo, re.IGNORECASE)
            
        v_nit = match_nit.group(1).strip() if match_nit else "No Detectado"
        
        # Combinar ambos valores
        v_cliente = f"{v_cliente_nombre} (NIT: {v_nit})"
        # --------------------------------------------------

        v_subtotal = extraer_valor([r'\nSubtotal\s+(\$[\d\,\.]+)'], texto_completo)
        
        todos_ivas = re.findall(r'IVA\s*(?:19%)?\s+(\$[\d\,\.]+)', texto_completo, re.IGNORECASE)
        v_iva = todos_ivas[-1] if todos_ivas else "$0.00"
        
        todos_totales = re.findall(r'\nTOTAL\s+(\$[\d\,\.]+)', texto_completo, re.IGNORECASE)
        v_total = todos_totales[-1] if todos_totales else "No detectado"

        tabla_match = re.search(r'REF\s+DESCRIPCIÓN.*?TOTAL ITEM\s*\n(.*?)(?=\nSubtotal)', texto_completo, re.DOTALL | re.IGNORECASE)
        
        filas_html = ""
        if tabla_match:
            bloque_tabla = tabla_match.group(1).strip()
            items_crudos = re.split(r'\n(?=\d+\s+\d{3})', bloque_tabla)
            
            for item in items_crudos:
                lineas = [l.strip() for l in item.split('\n') if l.strip()]
                if not lineas:
                    continue
                
                texto_item_unido = " ".join(lineas)
                match_cabeza = re.match(r'^(\d+)\s+(\d{3})\s+(.*)', texto_item_unido)
                if match_cabeza:
                    num = match_cabeza.group(1)
                    ref = match_cabeza.group(2)
                    resto = match_cabeza.group(3)
                    
                    precios = re.findall(r'\$[\d\,\.]+', resto)
                    cant_um_match = re.search(r'\b(\d+)\s+(EA|94|UND)\b', resto, re.IGNORECASE)
                    cant = cant_um_match.group(1) if cant_um_match else "1"
                    um = cant_um_match.group(2) if cant_um_match else "EA"
                    
                    imp = "IVA 19%" if "IVA 19%" in resto.upper() else ""
                    
                    descripcion = resto
                    if cant_um_match:
                        descripcion = descripcion.replace(cant_um_match.group(0), "")
                    descripcion = re.sub(r'IVA\s*19%', '', descripcion, flags=re.IGNORECASE)
                    for p in precios:
                        descripcion = descripcion.replace(p, "")
                    descripcion = re.sub(r'\s+', ' ', descripcion).strip()
                    
                    precio_unit = precios[0] if len(precios) > 0 else ""
                    subtotal_val = precios[1] if len(precios) > 1 else precio_unit
                    total_val = precios[2] if len(precios) > 2 else subtotal_val
                    
                    filas_html += f"""
                    <tr style="border-bottom: 1px solid #e0e0e0;">
                      <td style="padding: 8px; text-align: center; vertical-align: top; color: #555;">{num}</td>
                      <td style="padding: 8px; text-align: center; vertical-align: top; font-weight: bold; color: #333;">{ref}</td>
                      <td style="padding: 8px; vertical-align: top; color: #222; font-size: 11px; line-height: 1.4;">{descripcion}</td>
                      <td style="padding: 8px; text-align: center; vertical-align: top;">{cant}</td>
                      <td style="padding: 8px; text-align: center; vertical-align: top;">{um}</td>
                      <td style="padding: 8px; text-align: right; vertical-align: top; white-space: nowrap;">{precio_unit}</td>
                      <td style="padding: 8px; text-align: center; vertical-align: top; color: #c62828; font-size: 10px;">{imp}</td>
                      <td style="padding: 8px; text-align: right; vertical-align: top; white-space: nowrap;">{subtotal_val}</td>
                      <td style="padding: 8px; text-align: right; vertical-align: top; font-weight: bold; white-space: nowrap; color: #111;">{total_val}</td>
                    </tr>
                    """
        else:
            filas_html = "<tr><td colspan='9' style='padding: 10px; text-align: center;'>No se pudieron procesar los ítems.</td></tr>"

        file.file.seek(0)
        pdf_bytes = file.file.read()
        archivo_b64 = base64.b64encode(pdf_bytes).decode('utf-8')

        url_google = "https://script.google.com/macros/s/AKfycbx2F6AsT4f6ZVxHiIyULRJ2D72F-gvIAcwI1UbvBkhrlmgwcc6y9t-rGn7NBBH-W-X1/exec"
        
        datos = {
            "archivo_nombre": file.filename,
            "cotizacion_id": v_num_cotizacion,
            "tipo_registro": tipo_registro,
            "fecha": v_fecha,
            "cliente": v_cliente,
            "filas_tabla": filas_html,
            "subtotal": v_subtotal,
            "iva": v_iva,
            "total": v_total,
            "archivo_b64": archivo_b64
        }
        
        resp_google = requests.post(url_google, json=datos)
        resultado_script = resp_google.json() if resp_google.text.startswith("{") else {"estado": "Completado", "mensaje": "Procesado correctamente"}
        
        return resultado_script
        
    except Exception as e:
        return {"estado": "Error", "mensaje": str(e)}
