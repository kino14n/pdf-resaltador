import fitz  # Importa PyMuPDF
import re    # Importa el módulo de expresiones regulares
import os    # Importa el módulo para operaciones del sistema de archivos
from flask import Flask, request, render_template, send_file, redirect, url_for, flash
from werkzeug.utils import secure_filename
import uuid # Para generar nombres de archivo únicos
import traceback # Para obtener trazas de error completas

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

# Crear los directorios si no existen al inicio de la aplicación
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
    
    nombre_pdf_original = os.path.basename(ruta_pdf_entrada)
    # Generar un nombre de archivo único para el PDF de salida para evitar colisiones
    nombre_pdf_salida = f"resaltado_{uuid.uuid4().hex}_{nombre_pdf_original}"
    ruta_pdf_salida = os.path.join(directorio_salida, nombre_pdf_salida)

    print(f"DEBUG: Intentando procesar PDF. Entrada: '{ruta_pdf_entrada}', Salida esperada: '{ruta_pdf_salida}'")

    try:
        doc = fitz.open(ruta_pdf_entrada)
        
        # Definir la expresión regular para el patrón especificado
        regex_patron = r"Ref:\s*([a-zA-Z0-9.:\-\s]+?)/"

        found_any_code = False # Bandera para verificar si se encontró y resaltó algún código

        for numero_pagina in range(doc.page_count):
            pagina = doc[numero_pagina]
            texto_pagina = pagina.get_text("text")

            coincidencias = re.finditer(regex_patron, texto_pagina)

            for coincidencia in coincidencias:
                codigo_extraido = coincidencia.group(1).strip()
                # Buscar las coordenadas del texto del código extraído para resaltarlo
                rects_codigo = pagina.search_for(codigo_extraido)
                if rects_codigo: # Verifica si search_for realmente encontró algo
                    for rect_codigo in rects_codigo:
                        pagina.add_highlight_annot(rect_codigo)
                        found_any_code = True
                        print(f"DEBUG: Código '{codigo_extraido}' resaltado en página {numero_pagina + 1}.")
                        break # Resaltar solo la primera ocurrencia encontrada por search_for para este código específico

        doc.save(ruta_pdf_salida)
        doc.close()
        
        # Verificar si el archivo realmente existe después de guardarlo
        if os.path.exists(ruta_pdf_salida):
            print(f"✅ PDF procesado y resaltado guardado exitosamente en: '{ruta_pdf_salida}'")
            return ruta_pdf_salida
        else:
            print(f"❌ ERROR: El archivo de salida no existe después de guardar: '{ruta_pdf_salida}'")
            return None

    except FileNotFoundError:
        print(f"❌ Error: El archivo PDF de entrada no se encontró en la ruta: '{ruta_pdf_entrada}'")
        return None
    except Exception as e:
        print(f"❌ Ocurrió un error al procesar '{ruta_pdf_entrada}': {e}")
        # Imprimir la traza de la pila completa para una mejor depuración
        traceback.print_exc()
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
        # Generar un nombre de archivo único para el archivo subido
        unique_filename_uploaded = f"{uuid.uuid4().hex}_{filename}"
        filepath_uploaded = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename_uploaded)
        file.save(filepath_uploaded)
        
        print(f"DEBUG: Archivo subido guardado temporalmente en: '{filepath_uploaded}'")
        flash(f'Archivo "{filename}" subido exitosamente. Procesando...')
        
        ruta_pdf_resaltado = procesar_pdf_y_resaltar_codigos(filepath_uploaded, app.config['PROCESSED_FOLDER'])
        
        # Eliminar el archivo subido original después de procesar
        try:
            os.remove(filepath_uploaded)
            print(f"DEBUG: Archivo subido original eliminado: '{filepath_uploaded}'")
        except Exception as e:
            print(f"ERROR: No se pudo eliminar el archivo subido original '{filepath_uploaded}': {e}")

        if ruta_pdf_resaltado:
            # Verificar si el archivo procesado existe antes de enviarlo
            if os.path.exists(ruta_pdf_resaltado):
                print(f"DEBUG: Preparando para enviar el archivo procesado: '{ruta_pdf_resaltado}'")
                flash('PDF procesado con éxito. Descarga tu archivo resaltado.')
                # Usar un bloque try-except alrededor de send_file también para robustez
                try:
                    return send_file(ruta_pdf_resaltado, as_attachment=True, download_name=f"resaltado_{filename}")
                except Exception as e:
                    print(f"ERROR: Fallo al enviar el archivo '{ruta_pdf_resaltado}': {e}")
                    flash('Error al descargar el PDF procesado. Por favor, inténtalo de nuevo.')
                    return redirect(url_for('index'))
            else:
                print(f"ERROR: ruta_pdf_resaltado es válida, pero el archivo no existe: '{ruta_pdf_resaltado}'")
                flash('Error al procesar el PDF: El archivo de salida no se encontró.')
                return redirect(url_for('index'))
        else:
            flash('Error al procesar el PDF. Por favor, inténtalo de nuevo.')
            return redirect(url_for('index'))
    else:
        flash('Tipo de archivo no permitido. Por favor, sube un archivo PDF.')
        return redirect(request.url)

if __name__ == '__main__':
    # Para despliegue en Railway, Gunicorn será el servidor.
    # Para pruebas locales, puedes usar app.run().
    # En Railway, el puerto será proporcionado por la variable de entorno PORT.
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)