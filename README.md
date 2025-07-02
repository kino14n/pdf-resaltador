# PDF Resaltador

Este es un proyecto de aplicación web sencilla construida con Flask y PyMuPDF que permite a los usuarios subir archivos PDF. La aplicación procesa estos PDFs para encontrar y resaltar códigos específicos que se encuentran entre la expresión "Ref:" y el primer carácter de barra (`/`). Los códigos pueden contener letras, números, puntos, dos puntos, guiones y espacios. Una vez procesado, el PDF resultante con los resaltados se ofrece para descarga.

## Características

* **Subida de PDF:** Interfaz web intuitiva para seleccionar y subir archivos PDF.

* **Extracción de Patrones:** Utiliza expresiones regulares para identificar códigos específicos.

* **Resaltado Visual:** Resalta automáticamente los códigos encontrados directamente en el PDF.

* **Descarga de PDF Procesado:** Permite descargar el PDF con los códigos resaltados.

* **Despliegue Sencillo:** Configurado para un despliegue fácil en plataformas como Railway.

## Requisitos

Para ejecutar esta aplicación localmente, necesitarás tener instalado:

* Python 3.x

* `pip` (gestor de paquetes de Python)

## Configuración y Ejecución Local

Sigue estos pasos para configurar y ejecutar la aplicación en tu máquina local:

1. **Clona el Repositorio:**
   Si aún no lo has hecho, clona este repositorio a tu máquina local usando Git Bash (o tu terminal preferida):