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
    Esta versión está mejorada para encontrar códigos con saltos de línea.
    """
    nombre_pdf_original = os.path.basename(ruta_pdf_entrada)
    nombre_pdf_salida = f"resaltado_{uuid.uuid4().hex}_{nombre_pdf_original}"
    ruta_pdf_salida = os.path.join(directorio_salida, nombre_pdf_salida)

    # Añadidos logs de depuración para ver el flujo
    print(f"DEBUG: Intentando procesar PDF. Entrada: '{ruta_pdf_entrada}', Salida esperada: '{ruta_pdf_salida}'")
    if specific_codes_list:
        print(f"DEBUG: Modo de resaltado: Códigos específicos. Lista: {specific_codes_list}")
    else:
        print("DEBUG: Modo de resaltado: Detección automática por Regex.")

    try:
        doc = fitz.open(ruta_pdf_entrada)
        found_any_code = False

        # Prepara la lista de códigos a buscar y su longitud máxima
        codes_to_find = []
        max_code_length = 0 # Inicializa la longitud máxima

        if specific_codes_list:
            for code in specific_codes_list:
                c = re.sub(r'\s+', '', code.strip()).lower() # Normaliza el código a buscar
                if c:
                    codes_to_find.append(c)
                    max_code_length = max(max_code_length, len(c)) # Actualiza la longitud máxima
        
        # Si no hay códigos específicos, usamos la lógica de regex para auto-detección
        # La regex se aplicará por página para obtener los códigos a buscar en esa página.
        
        # Si no hay códigos para buscar (ni específicos ni por auto-detección inicial),
        # podemos cerrar el documento y salir.
        if not codes_to_find and specific_codes_list: # Solo si se intentó buscar específicos y no se encontró nada
            print("INFO: No se proporcionaron códigos específicos válidos para buscar.")
            doc.close()
            return None # O puedes optar por guardar el PDF original sin cambios si lo prefieres

        # Recorre páginas
        for numero_pagina, pagina in enumerate(doc):
            print(f"DEBUG: Procesando página {numero_pagina + 1}/{doc.page_count}")
            
            words = pagina.get_text("words")
            if not words:
                print(f"DEBUG: Página {numero_pagina + 1} no contiene palabras.")
                continue

            # Si es modo automático (no se dieron specific_codes_list),
            # construimos los codes_to_find para esta página usando la regex.
            current_page_codes_to_find = list(codes_to_find) # Copia la lista global si hay específicos
            current_page_max_code_length = max_code_length # Copia la longitud máxima global

            if not specific_codes_list: # Si estamos en modo de detección automática
                texto_pagina_completo = pagina.get_text("text")
                # Un patrón más flexible que captura el código después de "Ref:"
                regex_patron = r"Ref:\s*([\w.:-]+(?:[\s-]*[\w.:-]+)*)"
                for match in re.finditer(regex_patron, texto_pagina_completo):
                    # Normaliza el código encontrado por la regex
                    c_auto = re.sub(r'\s+', '', match.group(1).strip()).lower()
                    if c_auto and c_auto not in current_page_codes_to_find: # Evitar duplicados
                        current_page_codes_to_find.append(c_auto)
                        current_page_max_code_length = max(current_page_max_code_length, len(c_auto))

            if not current_page_codes_to_find: # Si no hay códigos para buscar en esta página
                continue

            # Solo texto de palabras, para acelerar el acceso
            word_texts = [w[4] for w in words]
            n_words = len(word_texts)

            for i in range(n_words):
                # Construye la secuencia solo hasta el largo máximo
                seq_original = "" # Para almacenar la secuencia de texto original
                rects = [] # Para almacenar los rectángulos de las palabras en la secuencia
                
                # El bucle 'j' avanza para construir la secuencia
                # min(i + current_page_max_code_length + 1, n_words) para asegurar que no excedemos el límite
                # y que cubrimos la longitud máxima del código.
                for j in range(i, min(i + current_page_max_code_length + 5, n_words)): # Añadimos un pequeño margen
                    word_text = word_texts[j]
                    
                    seq_original += word_text
                    rects.append(fitz.Rect(words[j][:4])) # Usar el rectángulo original de la palabra
                    
                    flat_seq = re.sub(r'\s+', '', seq_original).lower() # Normaliza la secuencia construida

                    # DEBUG:
                    # print(f"SEC_DEBUG: P{numero_pagina+1} W{i}-{j}: '{seq_original}' -> Flat: '{flat_seq}'")

                    # Comprobar si la secuencia aplanada construida es un prefijo de algún código objetivo
                    # Esto es para la "poda" de secuencias.
                    is_prefix_of_any_target = False
                    for target in current_page_codes_to_find:
                        if target.startswith(flat_seq):
                            is_prefix_of_any_target = True
                            break
                    
                    if not is_prefix_of_any_target:
                        # Si la secuencia actual ya no es un prefijo de ningún código objetivo,
                        # no tiene sentido seguir construyendo esta secuencia.
                        break # Rompemos el bucle 'j' y pasamos a la siguiente palabra inicial 'i'

                    # Si la secuencia plana construida coincide exactamente con algún código objetivo
                    if flat_seq in current_page_codes_to_find:
                        # ¡Coincidencia encontrada!
                        print(f"✅ CÓDIGO ENCONTRADO Y RESALTADO: '{seq_original}' (plano: '{flat_seq}') en página {numero_pagina + 1}.")
                        
                        # Unimos todos los rectángulos de las palabras que forman el código
                        combined_rect = fitz.Rect()
                        for r in rects:
                            combined_rect |= r # Unir rectángulos
                        
                        pagina.add_highlight_annot(combined_rect)
                        found_any_code = True
                        
                        # Mover el índice principal 'i' más allá de la coincidencia actual
                        # para buscar ocurrencias subsiguientes sin superposición.
                        # Esto es crucial para la eficiencia y para evitar resaltados duplicados.
                        i = j # Ajusta 'i' a la última palabra de la coincidencia
                        break # Salimos del bucle 'j' para buscar la siguiente ocurrencia del código
                
                # Si el bucle 'j' terminó sin encontrar una coincidencia completa para la 'i' actual,
                # o si se encontró una coincidencia y 'i' ya se ajustó, simplemente avanzamos 'i'.
                # Esto se maneja implícitamente por el bucle 'for i' y el ajuste de 'i=j' en el 'break' interno.
                # No necesitamos un 'i += 1' explícito aquí si el 'break' interno ya lo maneja.
                # El 'for i' avanzará automáticamente si no se hizo 'break'.
                pass


        if found_any_code:
            print("INFO: Guardando PDF con códigos resaltados...")
            # Usamos garbage=4 y deflate=True para asegurar una salida limpia y optimizada
            doc.save(ruta_pdf_salida, garbage=4, deflate=True) 
        else:
            print("INFO: No se encontraron códigos. Guardando el PDF original sin cambios.")
            # Si no se encontró nada, guardamos el original (o puedes optar por no guardar nada)
            doc.save(ruta_pdf_salida) 

        doc.close()
        return ruta_pdf_salida

    except Exception as e:
        print(f"❌ Ocurrió un error al procesar '{ruta_pdf_entrada}': {e}")
        traceback.print_exc() # Imprime la traza completa para depuración
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
