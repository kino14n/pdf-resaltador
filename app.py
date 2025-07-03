import fitz  # Importa PyMuPDF
import re    # Importa el módulo de expresiones regulares
import os    # Importa el módulo para operaciones del sistema de archivos
from flask import Flask, request, render_template, send_file, redirect, url_for, flash
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
    Procesa un archivo PDF para encontrar y resaltar códigos, incluyendo aquellos
    que están partidos por saltos de línea.
    """
    nombre_pdf_original = os.path.basename(ruta_pdf_entrada)
    nombre_pdf_salida = f"resaltado_{uuid.uuid4().hex}_{nombre_pdf_original}"
    ruta_pdf_salida = os.path.join(directorio_salida, nombre_pdf_salida)

    print(f"DEBUG: Intentando procesar PDF. Entrada: '{ruta_pdf_entrada}', Salida esperada: '{ruta_pdf_salida}'")
    if specific_codes_list:
        print(f"DEBUG: Modo de resaltado: Códigos específicos. Lista: {specific_codes_list}")
    else:
        print("DEBUG: Modo de resaltado: Regex.")

    try:
        doc = fitz.open(ruta_pdf_entrada)
        found_any_code = False

        # Prepara la lista de códigos a buscar una sola vez (si son específicos)
        # En modo automático, se construirán por página.
        codes_to_find_global = []
        if specific_codes_list:
            codes_to_find_global = [code.strip() for code in specific_codes_list if code.strip()]
        
        if not specific_codes_list and not codes_to_find_global:
            print("INFO: No se proporcionaron códigos específicos y el modo automático está activo.")
            # Si no hay códigos específicos, la lógica de auto-detección se ejecutará por página.

        for numero_pagina, pagina in enumerate(doc):
            print(f"DEBUG: Procesando página {numero_pagina + 1}/{doc.page_count}")
            
            # 1. Extraer palabras con sus coordenadas
            words = pagina.get_text("words")
            if not words:
                print(f"DEBUG: Página {numero_pagina + 1} no contiene palabras.")
                continue

            # Determinar códigos a buscar para ESTA página (ya sea específicos o auto-detectados)
            codes_to_find_on_current_page = []
            if specific_codes_list:
                codes_to_find_on_current_page = codes_to_find_global # Usar la lista global si son específicos
            else:
                # Si es modo automático, encontrar los códigos con regex para esta página
                texto_pagina_completo = pagina.get_text("text")
                regex_patron = r"Ref:\s*([\w.:-]+(?:[\s-]*[\w.:-]+)*)" # Regex más flexible
                for match in re.finditer(regex_patron, texto_pagina_completo):
                    # Normalizar el código encontrado por la regex (quitar espacios y convertir a plano)
                    codigo_normalizado_regex = re.sub(r'\s+', '', match.group(1)).lower()
                    if codigo_normalizado_regex:
                        codes_to_find_on_current_page.append(codigo_normalizado_regex)
            
            if not codes_to_find_on_current_page:
                continue

            # 2. Iterar sobre los códigos a buscar en la página actual
            for code_original_input in codes_to_find_on_current_page:
                # Normalizamos el código objetivo para una comparación robusta (sin espacios y en minúsculas)
                flat_target_code = re.sub(r'\s+', '', code_original_input).lower()
                if not flat_target_code:
                    continue
                
                print(f"DEBUG: Buscando código (target plano): '{flat_target_code}' (original: '{code_original_input}') en página {numero_pagina + 1}.")

                # 3. Buscar secuencias de palabras que coincidan con el código
                # 'i' es el índice de inicio para una posible coincidencia en la lista 'words'
                i = 0
                while i < len(words):
                    current_sequence_words_data = [] # Almacena (word_text, word_rect) para la secuencia actual
                    flat_current_sequence = ""       # Almacena el texto aplanado de la secuencia actual

                    # 'j' extiende la secuencia desde 'i'
                    for j in range(i, len(words)):
                        word_text = words[j][4]
                        word_rect = fitz.Rect(words[j][:4])
                        
                        flat_word_text = re.sub(r'\s+', '', word_text).lower()

                        # Construir la secuencia aplanada
                        flat_current_sequence += flat_word_text
                        current_sequence_words_data.append((word_text, word_rect)) # Almacenar datos originales de la palabra

                        # DEBUG:
                        # print(f"SEC_DEBUG: P{numero_pagina+1} W{i}-{j}: Flat seq: '{flat_current_sequence}' (Target: '{flat_target_code}')")

                        # Comprobar si la secuencia aplanada actual es un prefijo del código objetivo
                        # Y si no es más larga que el código objetivo
                        if flat_target_code.startswith(flat_current_sequence) and \
                           len(flat_current_sequence) <= len(flat_target_code):
                            
                            # Si la secuencia aplanada coincide EXACTAMENTE con el código objetivo
                            if flat_current_sequence == flat_target_code:
                                # ¡Coincidencia encontrada! Combinar rectángulos y resaltar
                                combined_rect = fitz.Rect()
                                for _, rect in current_sequence_words_data: # Usar rectángulos originales almacenados
                                    combined_rect |= rect
                                
                                pagina.add_highlight_annot(combined_rect)
                                found_any_code = True
                                print(f"✅ CÓDIGO ENCONTRADO Y RESALTADO: '{code_original_input}' en página {numero_pagina + 1} en coordenadas: {combined_rect}.")
                                
                                # Mover el índice de inicio 'i' más allá de la coincidencia actual
                                # para buscar ocurrencias subsiguientes sin superposición.
                                i = j + 1 
                                break # Salir del bucle interno 'j' para iniciar una nueva búsqueda desde 'i'
                        else:
                            # Si la secuencia actual ya no es un prefijo del objetivo,
                            # o si es más larga, entonces este camino no llevará a una coincidencia.
                            break # Salir del bucle interno 'j' y probar con la siguiente palabra inicial 'i'
                    else: # Este 'else' pertenece al bucle 'for j', se ejecuta si el bucle 'j' termina sin 'break'
                        # Si el bucle 'j' terminó sin encontrar una coincidencia completa para la 'i' actual,
                        # entonces avanzamos 'i' para probar la siguiente palabra como inicio.
                        i += 1
                        continue # Continuar el bucle 'while i'
                    
                    # Si se encontró una coincidencia y se ejecutó 'break' en el bucle 'j',
                    # el índice 'i' ya fue actualizado. Necesitamos asegurar que el bucle 'while i'
                    # continúe desde el nuevo 'i'.
                    # Si el 'break' del bucle 'j' se ejecutó, el 'i' ya fue ajustado,
                    # así que no necesitamos 'i += 1' aquí.
                    # Si el 'break' no se ejecutó (y el 'else' del 'for j' sí), 'i' ya fue incrementado.
                    # Por lo tanto, no necesitamos un 'i += 1' explícito aquí.
                    pass # El control de 'i' se maneja dentro del bucle 'j' o en su 'else'

        if found_any_code:
            print("INFO: Guardando PDF con códigos resaltados...")
            doc.save(ruta_pdf_salida, garbage=4, deflate=True) # Mantenemos garbage=4 y deflate=True para limpieza
        else:
            print("INFO: No se encontraron códigos. Guardando el PDF original sin cambios.")
            doc.save(ruta_pdf_salida) # Guardar original si no hay cambios, o puedes optar por no guardar nada

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
