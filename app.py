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
    Procesa un archivo PDF, busca códigos (ya sea por regex o por lista específica),
    y crea un nuevo PDF con esos códigos resaltados.
    Esta versión está mejorada para encontrar códigos con saltos de línea.
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

        for numero_pagina in range(doc.page_count):
            pagina = doc[numero_pagina]
            print(f"DEBUG: Procesando página {numero_pagina + 1}/{doc.page_count}")
            
            # 1. Extraer palabras con sus coordenadas
            words = pagina.get_text("words")
            if not words:
                print(f"DEBUG: Página {numero_pagina + 1} no contiene palabras.")
                continue

            # Construir una lista de códigos a buscar para esta página
            codes_to_find = []
            if specific_codes_list:
                codes_to_find = [code.strip() for code in specific_codes_list if code.strip()]
            else:
                # Si es modo automático, primero encontrar los códigos con regex
                texto_pagina_completo = pagina.get_text("text")
                # Mejora sugerida para la regex: más flexible y robusta
                regex_patron = r"Ref:\s*([\w.:-]+(?:[\s-]*[\w.:-]+)*)"
                for match in re.finditer(regex_patron, texto_pagina_completo):
                    # Para la búsqueda automática, usamos el texto capturado por la regex
                    codes_to_find.append(match.group(1).strip())
            
            if not codes_to_find:
                continue

            # 2. Iterar sobre los códigos a buscar en la página actual
            for code in codes_to_find:
                target_code_flat = re.sub(r'\s+', '', code).lower()
                if not target_code_flat:
                    continue
                
                print(f"DEBUG: Buscando código (target plano): '{target_code_flat}' en página {numero_pagina + 1}.")

                # 3. Buscar secuencias de palabras que coincidan con el código
                # Este bucle ahora busca todas las ocurrencias en la página
                for i in range(len(words)):
                    current_sequence_text = "" # Almacena el texto original de la secuencia
                    current_sequence_flat = "" # Almacena el texto normalizado (plano) para la comparación
                    rects_to_highlight = []
                    
                    for j in range(i, len(words)):
                        word_text = words[j][4]
                        rect = fitz.Rect(words[j][:4])
                        
                        current_sequence_text += word_text
                        current_sequence_flat += re.sub(r'\s+', '', word_text).lower() # Normaliza y concatena
                        rects_to_highlight.append(rect)
                        
                        # Comprobar si la secuencia actual (plana) contiene nuestro código objetivo (plano)
                        # Y si la secuencia no es más larga que el código objetivo (para evitar resaltar "de más")
                        if target_code_flat in current_sequence_flat and \
                           len(current_sequence_flat) <= len(target_code_flat) and \
                           target_code_flat.endswith(current_sequence_flat): # Asegura que estamos construyendo desde el inicio del target
                            
                            # Si la secuencia plana construida coincide exactamente con el target plano
                            if current_sequence_flat == target_code_flat:
                                # Combinar los rectángulos de las palabras encontradas
                                combined_rect = fitz.Rect()
                                for r in rects_to_highlight:
                                    combined_rect.include_rect(r)
                                
                                pagina.add_highlight_annot(combined_rect)
                                found_any_code = True
                                print(f"✅ CÓDIGO ENCONTRADO Y RESALTADO: '{code}' en página {numero_pagina + 1} en coordenadas: {combined_rect}.")
                                # Avanzar 'i' para que no procese palabras ya usadas en esta coincidencia
                                i = j # Ajusta el índice del bucle exterior para continuar después de la coincidencia
                                break # Salir del bucle interno 'j' para esta coincidencia
                    # Si el bucle 'j' terminó y no hubo un 'break' (es decir, no se encontró una coincidencia completa)
                    # entonces 'i' avanzará en el bucle exterior 'for i' normalmente.
                    else:
                        continue # Esto hace que el bucle 'for i' continúe con la siguiente iteración si el 'j' no encontró nada.
                    
                    # Si se encontró una coincidencia y se hizo 'break' del bucle 'j',
                    # este 'break' saldrá del bucle 'i' para buscar el siguiente código.
                    # Si quieres resaltar todas las ocurrencias del mismo código en la misma página,
                    # este 'break' (y el anterior) deben ser eliminados.
                    # Para la precisión de "no resaltar de más" y manejar saltos de línea,
                    # es mejor dejar que el bucle 'i' avance por sí mismo con 'i = j'.
                    # Por lo tanto, este 'break' externo se elimina para permitir múltiples coincidencias por código.
                    # break # Eliminado para permitir múltiples resaltados del mismo código en la misma página.


        # CAMBIO CLAVE: Guardar el PDF con garbage=4 para asegurar una salida limpia
        doc.save(ruta_pdf_salida, garbage=4) 
        doc.close()
        
        if os.path.exists(ruta_pdf_salida):
            print(f"✅ PDF procesado y resaltado guardado exitosamente en: '{ruta_pdf_salida}'")
            return ruta_pdf_salida
        else:
            print(f"❌ ERROR: El archivo de salida no existe después de guardar: '{ruta_pdf_salida}'")
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
