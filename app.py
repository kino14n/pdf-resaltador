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

def procesar_pdf_y_resaltar_codigos(ruta_pdf_entrada, directorio_salida, specific_codes_list=None):
    """
    Procesa un archivo PDF, busca códigos (ya sea por regex o por lista específica),
    y crea un nuevo PDF con esos códigos resaltados.

    Args:
        ruta_pdf_entrada (str): La ruta completa al archivo PDF que se va a procesar.
        directorio_salida (str): La ruta del directorio donde se guardará el PDF resaltado.
        specific_codes_list (list, optional): Una lista de códigos específicos a resaltar.
                                              Si se proporciona, se ignorará la regex.
                                              Defaults to None.

    Returns:
        str: La ruta completa del archivo PDF resaltado si el procesamiento fue exitoso,
             o None si hubo un error.
    """
    
    nombre_pdf_original = os.path.basename(ruta_pdf_entrada)
    # Generar un nombre de archivo único para el PDF de salida para evitar colisiones
    nombre_pdf_salida = f"resaltado_{uuid.uuid4().hex}_{nombre_pdf_original}"
    ruta_pdf_salida = os.path.join(directorio_salida, nombre_pdf_salida)

    print(f"DEBUG: Intentando procesar PDF. Entrada: '{ruta_pdf_entrada}', Salida esperada: '{ruta_pdf_salida}'")
    if specific_codes_list:
        print(f"DEBUG: Modo de resaltado: Códigos específicos. Lista: {specific_codes_list}")
    else:
        print("DEBUG: Modo de resaltado: Regex.")

    try:
        doc = fitz.open(ruta_pdf_entrada)
        
        found_any_code = False # Bandera para verificar si se encontró y resaltó algún código

        for numero_pagina in range(doc.page_count):
            pagina = doc[numero_pagina]
            texto_pagina = pagina.get_text("text")
            
            # Depuración: Verificar si el texto de la página se extrajo
            print(f"DEBUG: Texto extraído de la página {numero_pagina + 1} (longitud: {len(texto_pagina)}). Primeros 100 caracteres: '{texto_pagina[:100].replace('\n', '\\n')}'")


            if specific_codes_list:
                # Resaltado por lista de códigos específicos (búsqueda de cadena exacta)
                for code_to_find in specific_codes_list:
                    # Normalizar el código para la búsqueda (eliminar espacios extra al inicio/final)
                    normalized_code = code_to_find.strip()
                    if not normalized_code: # Saltar si el código está vacío después de normalizar
                        continue

                    # Volvemos a usar search_for directamente con el código normalizado.
                    # Esto buscará la cadena exacta en cualquier parte de la página.
                    # Nota: Si el código está partido por un salto de línea en el PDF (ej. "MF06\n10G"),
                    # y buscas "MF0610G", search_for NO lo encontrará.
                    print(f"DEBUG: Buscando código específico (coincidencia exacta con search_for): '{normalized_code.replace('\n', '\\n')}' en página {numero_pagina + 1}.")
                    rects_codigo = pagina.search_for(normalized_code)
                    
                    if rects_codigo:
                        for rect_codigo in rects_codigo:
                            pagina.add_highlight_annot(rect_codigo) 
                            found_any_code = True
                            print(f"DEBUG: Código específico '{normalized_code.replace('\n', '\\n')}' resaltado en página {numero_pagina + 1} en coordenadas: {rect_codigo}.")
                    else:
                        print(f"DEBUG: NO se encontró el código específico '{normalized_code.replace('\n', '\\n')}' para resaltar en página {numero_pagina + 1}.")
            else:
                # Resaltado por expresión regular (comportamiento original si no se dan códigos específicos)
                # Esta regex se mantiene para la detección automática de códigos "Ref: ... /"
                regex_patron = r"Ref:\s*([a-zA-Z0-9.:\-\s]+?)/+"
                coincidencias = re.finditer(regex_patron, texto_pagina)

                for coincidencia in coincidencias:
                    texto_a_resaltar = coincidencia.group(1) 
                    
                    print(f"DEBUG: Coincidencia de Regex completa (auto): '{coincidencia.group(0).replace('\n', '\\n')}'")
                    print(f"DEBUG: Texto capturado para resaltar (grupo 1, sin strip, auto): '{texto_a_resaltar.replace('\n', '\\n')}' en página {numero_pagina + 1}.")
                    
                    rects_codigo = pagina.search_for(texto_a_resaltar)
                    
                    if rects_codigo:
                        for rect_codigo in rects_codigo:
                            pagina.add_highlight_annot(rect_codigo) 
                            found_any_code = True
                            print(f"DEBUG: Código '{texto_a_resaltar.replace('\n', '\\n')}' resaltado en página {numero_pagina + 1}.")
                    else:
                        print(f"DEBUG: NO se encontró el texto '{texto_a_resaltar.replace('\n', '\\n')}' para resaltar en página {numero_pagina + 1} (posiblemente por diferencias exactas en el texto o el layout del PDF).")


        doc.save(ruta_pdf_salida)
        doc.close()
        
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
        return redirect(url_for('index'))
    
    file = request.files['pdf_file']
    
    if file.filename == '':
        flash('No se seleccionó ningún archivo.')
        return redirect(url_for('index'))
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        unique_filename_uploaded = f"{uuid.uuid4().hex}_{filename}"
        filepath_uploaded = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename_uploaded)
        file.save(filepath_uploaded)
        
        print(f"DEBUG: Archivo subido guardado temporalmente en: '{filepath_uploaded}'")
        flash(f'Archivo "{filename}" subido exitosamente. Procesando...')
        
        # Obtener los códigos específicos del formulario
        specific_codes_input = request.form.get('specific_codes', '').strip()
        specific_codes_list = []
        if specific_codes_input:
            specific_codes_list = [code.strip() for code in specific_codes_input.split(',') if code.strip()]
            print(f"DEBUG: Códigos específicos recibidos del formulario: {specific_codes_list}")

        # Pasar la lista de códigos específicos a la función de procesamiento
        ruta_pdf_resaltado = procesar_pdf_y_resaltar_codigos(filepath_uploaded, app.config['PROCESSED_FOLDER'], specific_codes_list)
        
        # Eliminar el archivo subido original después de procesar
        try:
            os.remove(filepath_uploaded)
            print(f"DEBUG: Archivo subido original eliminado: '{filepath_uploaded}'")
        except Exception as e:
            print(f"ERROR: No se pudo eliminar el archivo subido original '{filepath_uploaded}': {e}")

        if ruta_pdf_resaltado:
            if os.path.exists(ruta_pdf_resaltado):
                print(f"DEBUG: Preparando para enviar el archivo procesado: '{ruta_pdf_resaltado}'")
                flash('PDF procesado con éxito. Mostrando vista previa.')
                # CAMBIO CLAVE: Mostrar el PDF en el navegador en lugar de forzar la descarga
                return send_file(ruta_pdf_resaltado, mimetype='application/pdf')
            else:
                print(f"ERROR: ruta_pdf_resaltado es válida, pero el archivo no existe: '{ruta_pdf_resaltado}'")
                flash('Error al procesar el PDF: El archivo de salida no se encontró.')
                return redirect(url_for('index'))
        else:
            flash('Error al procesar el PDF. Por favor, inténtalo de nuevo.')
            return redirect(url_for('index'))
    else:
        flash('Tipo de archivo no permitido. Por favor, sube un archivo PDF.')
        return redirect(url_for('index'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)

