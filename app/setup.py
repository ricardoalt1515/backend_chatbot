import os
from openai import OpenAI
from dotenv import load_dotenv
import time

# Cargar variables de entorno
load_dotenv()

# Configurar cliente de OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def upload_file(file_path):
    """Sube un archivo a OpenAI y devuelve su ID"""
    print(f"Subiendo archivo: {file_path}")

    try:
        with open(file_path, "rb") as file:
            response = client.files.create(
                file=file,
                purpose="assistants",  # Este propósito es necesario para búsqueda de archivos
            )
        print(f"✅ Archivo subido con éxito. ID: {response.id}")
        return response.id
    except Exception as e:
        print(f"❌ Error al subir archivo: {e}")
        raise e


def create_vector_store(name="Hydrous Cuestionario"):
    """Crea un Vector Store y devuelve su ID"""
    print(f"Creando Vector Store con nombre: {name}")

    try:
        response = client.vector_stores.create(name=name)
        print(f"✅ Vector Store creado con éxito. ID: {response.id}")
        return response.id
    except Exception as e:
        print(f"❌ Error al crear Vector Store: {e}")
        raise e


def add_file_to_vector_store(vector_store_id, file_id):
    """Añade un archivo a un Vector Store"""
    print(f"Añadiendo archivo {file_id} al Vector Store {vector_store_id}")

    try:
        response = client.vector_stores.files.create(
            vector_store_id=vector_store_id, file_id=file_id
        )
        print(f"✅ Archivo añadido con éxito al Vector Store")
        return response
    except Exception as e:
        print(f"❌ Error al añadir archivo al Vector Store: {e}")
        raise e


def check_file_status(vector_store_id, file_id):
    """Verifica el estado del archivo en el Vector Store"""
    print("Verificando estado del archivo en el Vector Store...")

    try:
        # Esperar hasta que el archivo esté procesado
        max_retries = 10
        retries = 0

        while retries < max_retries:
            files = client.vector_stores.files.list(vector_store_id=vector_store_id)

            for file in files.data:
                if file.id == file_id:
                    status = file.status

                    if status == "completed":
                        print(f"✅ Archivo procesado completamente")
                        return True
                    elif status == "error":
                        print(f"❌ Error al procesar archivo: {file.error}")
                        return False
                    else:
                        print(f"⏳ Archivo en estado: {status}. Esperando...")
                        break

            retries += 1
            time.sleep(5)  # Esperar 5 segundos antes de verificar de nuevo

        print("⚠️ Tiempo de espera agotado para la verificación del archivo")
        return False
    except Exception as e:
        print(f"❌ Error al verificar estado del archivo: {e}")
        return False


def setup_vector_store(pdf_path):
    """Configura un Vector Store con el cuestionario completo"""
    try:
        # Paso 1: Subir archivo
        file_id = upload_file(pdf_path)

        # Paso 2: Crear Vector Store
        vector_store_id = create_vector_store()

        # Paso 3: Añadir archivo al Vector Store
        add_file_to_vector_store(vector_store_id, file_id)

        # Paso 4: Verificar estado
        check_file_status(vector_store_id, file_id)

        # Generar información para .env
        print("\n" + "=" * 50)
        print("CONFIGURACIÓN COMPLETADA")
        print("=" * 50)
        print("Añade estas líneas a tu archivo .env:")
        print(f"FILE_ID={file_id}")
        print(f"VECTOR_STORE_ID={vector_store_id}")
        print("=" * 50)

        return vector_store_id, file_id
    except Exception as e:
        print(f"Error durante la configuración: {e}")
        return None, None


if __name__ == "__main__":
    # Ruta al archivo del cuestionario
    pdf_path = "cuestionario.pdf"

    # Verificar que el archivo existe
    if not os.path.exists(pdf_path):
        print(
            f"❌ El archivo {pdf_path} no existe. Por favor, asegúrate de que la ruta es correcta."
        )
    else:
        setup_vector_store(pdf_path)
