from flask import Flask, request, send_file
from flask_cors import CORS
import pandas as pd
import io
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

app = Flask(__name__)
CORS(app)

def limpiar_moneda(x):
    if pd.isna(x): return 0.0
    if isinstance(x, str):
        x = x.replace('.', '').replace(',', '.')
    return float(x)

@app.route('/procesar-almaviva', methods=['POST'])
def procesar_archivo():
    if 'file' not in request.files:
        return "No se envió ningún archivo", 400
    
    file = request.files['file']
    df = pd.read_csv(file, quotechar='"')
    
    # Limpiamos las columnas de dinero
    df['Precio'] = df['Precio'].apply(limpiar_moneda)
    df['Costo'] = df['Costo'].apply(limpiar_moneda)
    df['Vehículo'] = df['Vehículo'].astype(str).str.strip()

    # Escribimos inicialmente los datos crudos en la memoria
    output = io.BytesIO()
    
    # Renombramos las columnas para que coincidan con la exportación final
    df_base = df[['ID de reserva', 'Hora de Pickup (Local)', 'Recoger', 'Destino', 'Nombre', 'Precio', 'Costo', 'Vehículo', 'Programa de viaje']].copy()
    
    programas = df['Programa de viaje'].dropna().unique()
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        for prog in programas:
            nombre_pestana = str(prog).split(' - ')[0][:30]
            df_prog = df_base[df_base['Programa de viaje'] == prog].copy()
            # Exportamos sin la tabla de resumen aún
            df_prog.to_excel(writer, sheet_name=nombre_pestana, index=False)

    # Ahora reabrimos el archivo en memoria con openpyxl para inyectar las fórmulas de Excel
    output.seek(0)
    wb = load_workbook(output)
    
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        max_row = ws.max_row
        
        # En nuestra estructura, Costo está en la G (columna 7), Vehículo en la H (columna 8), Precio en la F (columna 6)
        # Vamos a inyectar el bloque de resumen justo debajo de los datos
        
        fila_inicio = max_row + 2
        
        # dst: =SUMAR.SI(H2:H[max], "8979", F2:F[max])
        ws[f'E{fila_inicio}'] = 'dst'
        ws[f'F{fila_inicio}'] = f'=SUMAR.SI(H2:H{max_row}, "8979", F2:F{max_row})'
        
        # trc: =SUMAR.SI(H2:H[max], "<>8979", G2:G[max])
        ws[f'E{fila_inicio+1}'] = 'trc'
        ws[f'F{fila_inicio+1}'] = f'=SUMAR.SI(H2:H{max_row}, "<>8979", G2:G{max_row})'
        
        # ing: =SUMAR.SI(H2:H[max], "<>8979", F2:F[max]) - F[fila_inicio+1]  (que es la celda de trc)
        ws[f'E{fila_inicio+2}'] = 'ing'
        ws[f'F{fila_inicio+2}'] = f'=SUMAR.SI(H2:H{max_row}, "<>8979", F2:F{max_row}) - F{fila_inicio+1}'
        
        # subtotal: =F[dst] + F[trc] + F[ing]
        ws[f'E{fila_inicio+3}'] = 'subtotal'
        ws[f'F{fila_inicio+3}'] = f'=F{fila_inicio} + F{fila_inicio+1} + F{fila_inicio+2}'
        
        # comision 5%: =subtotal * 0.05
        ws[f'E{fila_inicio+4}'] = 'comision 5%'
        ws[f'F{fila_inicio+4}'] = f'=F{fila_inicio+3} * 0.05'
        
        # iva 19%: =comision * 0.19
        ws[f'E{fila_inicio+5}'] = 'iva 19%'
        ws[f'F{fila_inicio+5}'] = f'=F{fila_inicio+4} * 0.19'
        
        # total: =subtotal + comision + iva
        ws[f'E{fila_inicio+6}'] = 'total'
        ws[f'F{fila_inicio+6}'] = f'=F{fila_inicio+3} + F{fila_inicio+4} + F{fila_inicio+5}'

    # Guardamos los cambios de vuelta en la memoria RAM
    final_output = io.BytesIO()
    wb.save(final_output)
    final_output.seek(0)
    
    return send_file(
        final_output, 
        as_attachment=True, 
        download_name="Reporte_Almaviva_Organizado.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
