from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
import pdfplumber
import smtplib
from email.mime.text import MIMEText

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
            
    mensaje = MIMEText(f"Datos extraídos de la factura:\n\n{texto}")
    mensaje['Subject'] = f"Desglose automatizado: {file.filename}"
    mensaje['From'] = "redesolatur@gmail.com"
    mensaje['To'] = "redesolatur@gmail.com"

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        # Aquí ya está tu contraseña sin espacios
        server.login("redesolatur@gmail.com", "eshjjlzofibibewv")
        server.send_message(mensaje)

    return {"estado": "Completado", "mensaje": "Datos enviados al correo"}