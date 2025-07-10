# PDF Resaltador de Códigos

**PDF Resaltador** es una aplicación web avanzada y fácil de usar que permite buscar y resaltar códigos dentro de archivos PDF de dos formas:

- **Extracción automática:** Encuentra y resalta todos los códigos que aparecen entre la expresión "Ref:" y el primer carácter de barra `/`.
- **Búsqueda personalizada:** Permite ingresar o subir una lista de códigos personalizados para resaltar, incluso si aparecen partidos por saltos de línea, guiones o espacios.

El PDF resultado solo muestra las páginas que contienen coincidencias resaltadas, para que el usuario ahorre tiempo revisando información.

---

## Características principales

- **Sube un PDF** desde la interfaz web.
- **Modo automático:** Detecta y resalta todos los códigos que cumplen el patrón `"Ref:" ... "/"`.
- **Modo personalizado:** Ingresa o sube una lista de códigos para buscar y resaltar (soporta fragmentación).
- **Descarga el PDF** resaltado, mostrando solo las páginas relevantes.
- Manejo eficiente de archivos temporales (preparado para Railway, Heroku, etc.).
- 100% Python + Flask + PyMuPDF (fitz), fácil de desplegar y mantener.

---

## ¿Cómo funciona?

1. El usuario accede a la web y sube su PDF.
2. Elige el modo:
    - **Automático:** La app detecta y resalta todos los códigos que cumplen el patrón `"Ref:" ... "/"`.
    - **Personalizado:** El usuario ingresa o sube la lista de códigos que desea buscar y resaltar.
3. El backend procesa el PDF, resalta las coincidencias y genera un nuevo PDF solo con las páginas relevantes.
4. El usuario descarga el PDF resultado.

---

## Despliegue rápido (Railway/Heroku/servidor propio)

### 1. Clona el repositorio:

```bash
git clone TU_REPO_GIT_URL
cd pdf-resaltador
