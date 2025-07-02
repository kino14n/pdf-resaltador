import fitz  # Importa PyMuPDF
import re    # Importa el módulo de expresiones regulares
import os    # Importa el módulo para operaciones del sistema de archivos
from flask import Flask, request, render_template, send_file, redirect, url_for, flash
from werkzeug.utils import secure_filename
import uuid # Para generar nombres de archivo únicos

app = Flask(__name__)
# Una clave secreta es necesaria para usar flash messages (mensajes temporales)
# ¡IMPORTANTE! Para producción, usa una variable de entorno para esta clave.
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'super_secret_key_por_defecto_local') 

# Directorios para guardar archivos subidos y procesados
# Estos directorios se crearán en el entorno de Railway también
UPLOAD_FOLDER = 'uploads'
PROCESSED_FOLDER = 'processed'
# Extensiones de archivo permitidas
ALLOWED_EXTENSIONS = {'pdf'}

# Crear los directorios si no existen (útil para desarrollo local)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROCESSED_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['PROCESSED_FOLDER'] = PROCESSED_FOLDER

def allowed_file(filename):
    """Verifica si la extensión del archivo es permitida."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def procesar_pdf_y_resaltar_codigos(ruta_pdf_entrada, directorio_salida):
    """
    Procesa un archivo PDF, busca códigos que están entre "Ref:" y el primer "/",
    y crea un nuevo PDF con esos códigos resaltados.

    Args:
        ruta_pdf_entrada (str): La ruta completa al archivo PDF que se va a procesar.
        directorio_salida (str): La ruta del directorio donde se guardará el PDF resaltado.

    Returns:
        str: La ruta completa del archivo PDF resaltado si el procesamiento fue exitoso,
             o None si hubo un error.
    """
    
    # Obtener el nombre base del archivo PDF de entrada para el archivo de salida
    nombre_pdf_original = os.path.basename(ruta_pdf_entrada)
    # Generar un nombre de archivo único para el PDF de salida para evitar colisiones
    nombre_pdf_salida = f"resaltado_{uuid.uuid4().hex}_{nombre_pdf_original}"
    ruta_pdf_salida = os.path.join(directorio_salida, nombre_pdf_salida)

    try:
        doc = fitz.open(ruta_pdf_entrada)
        
        # Definir la expresión regular para el patrón especificado
        regex_patron = r"Ref:\s*([a-zA-Z0-9.:\-\s]+?)/"

        for numero_pagina in range(doc.page_count):
            pagina = doc[numero_pagina]
            texto_pagina = pagina.get_text("text")

            coincidencias = re.finditer(regex_patron, texto_pagina)

            for coincidencia in coincidencias:
                codigo_extraido = coincidencia.group(1).strip()

                # Buscar las coordenadas del texto del código extraído para resaltarlo
                rects_codigo = pagina.search_for(codigo_extraido)
                for rect_codigo in rects_codigo:
                    pagina.add_highlight_annot(rect_codigo)
                    break # Solo resaltamos la primera ocurrencia encontrada por search_for

        doc.save(ruta_pdf_salida)
        doc.close()
        print(f"✅ PDF procesado y resaltado guardado en: {ruta_pdf_salida}")
        return ruta_pdf_salida

    except FileNotFoundError:
        print(f"❌ Error: El archivo PDF no se encontró en la ruta: {ruta_pdf_entrada}")
        return None
    except Exception as e:
        print(f"❌ Ocurrió un error al procesar {ruta_pdf_entrada}: {e}")
        return None

@app.route('/')
def index():
    """Renderiza la página principal con el formulario de subida."""
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    """Maneja la subida del archivo PDF, lo procesa y ofrece la descarga."""
    if 'pdf_file' not in request.files:
        flash('No se seleccionó ningún archivo.')
        return redirect(request.url)
    
    file = request.files['pdf_file']
    
    if file.filename == '':
        flash('No se seleccionó ningún archivo.')
        return redirect(request.url)
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4().hex}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(filepath)
        
        flash(f'Archivo "{filename}" subido exitosamente. Procesando...')
        
        ruta_pdf_resaltado = procesar_pdf_y_resaltar_codigos(filepath, app.config['PROCESSED_FOLDER'])
        
        # Eliminar el archivo subido original para limpiar
        os.remove(filepath)

        if ruta_pdf_resaltado:
            flash('PDF procesado con éxito. Descarga tu archivo resaltado.')
            return send_file(ruta_pdf_resaltado, as_attachment=True, download_name=f"resaltado_{filename}")
        else:
            flash('Error al procesar el PDF. Por favor, inténtalo de nuevo.')
            return redirect(url_for('index'))
    else:
        flash('Tipo de archivo no permitido. Por favor, sube un archivo PDF.')
        return redirect(request.url)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)