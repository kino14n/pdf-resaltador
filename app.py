import fitz  # Importa PyMuPDF
import re    # Importa el módulo de expresiones regulares
import os    # Importa el módulo para operaciones del sistema de archivos
from flask import Flask, request, render_template, send_file, redirect, url_for, flash, jsonify # Añadida importación de jsonify
from werkzeug.utils import secure_filename
import uuid # Para generar nombres de archivo únicos
import traceback # Para obtener trazas de error completas
import tempfile # Importar el módulo tempfile

app = Flask(__name__)
# Una clave secreta es necesaria para usar flash messages (mensajes temporales)
# ¡IMPORTANTE! Para producción, usa una variable de entorno para esta clave.
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'super_secret_key_por_defecto_local') 

# Directorios para guardar archivos subidos y procesados
# En Railway, /tmp es el directorio recomendado para archivos temporales y escribibles.
# Usamos tempfile.gettempdir() para obtener la ruta del directorio temporal del sistema.
UPLOAD_FOLDER = os.path.join(tempfile.gettempdir(), 'uploads')
PROCESSED_FOLDER = os.path.join(tempfile.gettempdir(), 'processed')
# Extensiones de archivo permitidas
ALLOWED_EXTENSIONS = {'pdf'}

# Crear los directorios si no existen.
# Esto se ejecutará al inicio de la aplicación, y ahora los directorios estarán en /tmp, que es escribible.
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
    Versión Híbrida Avanzada: Encuentra códigos (incluso partidos), los resalta
    y genera un nuevo PDF solo con las páginas que contienen resaltados.
    """
    nombre_pdf_original = os.path.basename(ruta_pdf_entrada)
    nombre_pdf_salida = f"resaltado_{uuid.uuid4().hex}_{nombre_pdf_original}"
    ruta_pdf_salida = os.path.join(directorio_salida, nombre_pdf_salida)

    if not specific_codes_list:
        print("INFO: No se proporcionaron códigos específicos para buscar.")
        # Si no hay códigos específicos, puedes decidir si quieres que se ejecute la auto-detección
        # o simplemente salir. Por ahora, salimos si no hay específicos.
        # Si quieres auto-detección, esta parte de la lógica debería estar aquí
        # y poblar `codes_to_find` para que el resto del código la use.
        return None

    try:
        doc = fitz.open(ruta_pdf_entrada)
        highlighted_pages = set() # Usamos un set para registrar las páginas con resaltados
        
        # Normalizar y limpiar los códigos a buscar una sola vez
        codes_to_find = list(set([re.sub(r'[\s-]+', '', code.strip()).lower() for code in specific_codes_list if code.strip()]))
        
        if not codes_to_find:
            print("INFO: Después de la normalización, no hay códigos válidos para buscar.")
            doc.close()
            return None

        # Lista para anotar los códigos que se encuentren rápidamente (normalizados)
        found_codes_fast = set() 

        # --- FASE 1: BÚSQUEDA RÁPIDA (search_for) ---
        print("DEBUG: Iniciando Fase 1 - Búsqueda Rápida.")
        for numero_pagina, pagina in enumerate(doc):
            # Para search_for, necesitamos la cadena original, no la normalizada.
            # Sin embargo, search_for no maneja saltos de línea.
            # Iteramos sobre los códigos originales para buscar.
            
            # Recuperar los códigos originales para esta página si estamos en modo específico.
            # Si fuera auto-detección, la lógica sería diferente aquí.
            codes_original_for_fast_search = [c.strip() for c in specific_codes_list if c.strip()]

            for code_original in codes_original_for_fast_search:
                # search_for encuentra todas las ocurrencias del texto y devuelve sus rectángulos
                rects_encontrados = pagina.search_for(code_original)
                
                if rects_encontrados:
                    found_any_code = True
                    highlighted_pages.add(pagina.number) # Anotamos el número de página
                    for rect in rects_encontrados:
                        highlight = pagina.add_highlight_annot(rect)
                        # Nota: set_colors y update pueden causar errores en versiones antiguas de PyMuPDF.
                        # Si esto falla, comenta estas dos líneas para usar el color predeterminado.
                        highlight.set_colors(stroke=(0, 0.6, 0), fill=(0, 0.6, 0)) # Verde oscuro para borde y relleno
                        highlight.update()
                    
                    # Normaliza el código original para añadirlo al set de encontrados rápidamente
                    normalized_found_code = re.sub(r'[\s-]+', '', code_original).lower()
                    found_codes_fast.add(normalized_found_code) 
                    print(f"DEBUG: Fase 1: Código '{code_original}' (normalizado: '{normalized_found_code}') encontrado y resaltado en página {pagina.number + 1}.")
        
        # --- FASE 2: BÚSQUEDA PROFUNDA (get_text("words")) ---
        # Identifica los códigos que NO se encontraron en la Fase 1 (usando la lista normalizada)
        unfound_codes_normalized = [code for code in codes_to_find if code not in found_codes_fast]

        if unfound_codes_normalized:
            print(f"DEBUG: Iniciando Fase 2 - Búsqueda Profunda para códigos: {unfound_codes_normalized}")
            # Recorre páginas de nuevo para la búsqueda profunda
            for numero_pagina, pagina in enumerate(doc):
                words = pagina.get_text("words")
                if not words:
                    continue
                
                n_words = len(words)
                
                for code_to_find_deep_normalized in unfound_codes_normalized:
                    flat_target_code_deep = code_to_find_deep_normalized # Ya está normalizado

                    i = 0
                    while i < n_words:
                        current_sequence_text = ""
                        rects_to_highlight = []
                        
                        for j in range(i, n_words):
                            word_text = words[j][4]
                            rect = fitz.Rect(words[j][:4])
                            
                            current_sequence_text += word_text
                            rects_to_highlight.append(rect)
                            
                            flat_sequence = re.sub(r'[\s-]+', '', current_sequence_text).lower()

                            # Poda: Si la secuencia actual ya no es un prefijo del objetivo, romper
                            if not flat_target_code_deep.startswith(flat_sequence):
                                break

                            # Si la secuencia plana construida coincide exactamente con el código objetivo
                            if flat_sequence == flat_target_code_deep:
                                print(f"✅ CÓDIGO PARTIDO ENCONTRADO (Fase 2): '{code_to_find_deep_normalized}' en página {pagina.number + 1}.")
                                
                                highlighted_pages.add(pagina.number) # Anotamos la página
                                combined_rect = fitz.Rect()
                                for r in rects_to_highlight:
                                    combined_rect.include_rect(r)
                                
                                highlight = pagina.add_highlight_annot(combined_rect)
                                # Nota: set_colors y update pueden causar errores en versiones antiguas de PyMuPDF.
                                # Si esto falla, comenta estas dos líneas para usar el color predeterminado.
                                highlight.set_colors(stroke=(0, 0.6, 0), fill=(0, 0.6, 0)) # Verde oscuro
                                highlight.update()
                                
                                i = j # Avanza 'i' para no re-procesar
                                found_any_code = True # Asegurarse de que found_any_code se actualice
                                break # Salir del bucle 'j'
                        
                        i += 1 # Avanzar 'i' para la siguiente posible secuencia

        # --- PASO FINAL: CREAR EL NUEVO PDF FILTRADO ---
        if highlighted_pages:
            print(f"INFO: Se encontraron códigos. Creando PDF de salida con las páginas: {sorted(list(highlighted_pages))}")
            
            # 1. Crear un nuevo documento en blanco
            new_doc = fitz.open()
            
            # 2. Copiar solo las páginas resaltadas del documento original al nuevo
            for page_num in sorted(list(highlighted_pages)):
                new_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)
            
            # 3. Guardar el nuevo documento filtrado
            new_doc.save(ruta_pdf_salida, garbage=4, deflate=True)
            new_doc.close()
        else:
            print("INFO: No se encontró ningún código. No se generará PDF de salida.")
            ruta_pdf_salida = None # Indicamos que no se creó ningún archivo

        doc.close()
        return ruta_pdf_salida

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
