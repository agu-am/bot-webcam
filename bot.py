import logging
import json
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)
from fuzzywuzzy import fuzz
from fuzzywuzzy import process

# Estados para la conversación de envío de fotos
PEDIR_TEXTO_1 = 1
PEDIR_TEXTO_2 = 2
PEDIR_TEXTO_3 = 3
PEDIR_FOTO = 4

# Importa las configuraciones
from config import TOKEN_BOT, ID_ADMIN, ID_CANAL_FOTOS

# Habilita el registro de eventos
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

ARCHIVO_ESTAFADORES = "estafadores.json"
estafadores = []


def cargar_estafadores():
    global estafadores
    try:
        with open(ARCHIVO_ESTAFADORES, "r", encoding="utf-8") as f:
            estafadores = json.load(f)
    except FileNotFoundError:
        estafadores = []
    except json.JSONDecodeError:
        logger.warning(f"Error al decodificar JSON de {ARCHIVO_ESTAFADORES}. Inicializando lista vacía.")
        estafadores = []
    logger.info(f"Cargados {len(estafadores)} estafadores.")


def guardar_estafadores():
    with open(ARCHIVO_ESTAFADORES, "w", encoding="utf-8") as f:
        json.dump(estafadores, f, ensure_ascii=False, indent=4)
    logger.info("Estafadores guardados.")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "¡Hola! Soy un bot para reportar estafadores. Usa /enviar_reporte para comenzar."
    )


async def agregar_estafador(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ID_ADMIN:
        await update.message.reply_text("¡No tienes permiso para usar este comando!")
        return

    if not context.args:
        await update.message.reply_text(
            "Formato incorrecto. Usa: /agregar_estafador [Nombre Completo]; [Usuario CAM4]; [Usuario Telegram]"
        )
        return

    try:
        full_args = " ".join(context.args)
        parts = [p.strip() for p in full_args.split(';') if p.strip()]

        if len(parts) < 3:
            await update.message.reply_text(
                "Faltan datos. Asegúrate de incluir Nombre Completo, Usuario CAM4 y Usuario Telegram separados por '; '."
            )
            return

        nombre_completo_nuevo = parts[0].strip()
        user_cam4_nuevo = parts[1].strip()
        user_telegram_nuevo = parts[2].strip()

    except IndexError:
        await update.message.reply_text(
            "Error al procesar los datos. Usa: /agregar_estafador [Nombre Completo]; [Usuario CAM4]; [Usuario Telegram]"
        )
        return

    estafador_existente = None
    for estafador in estafadores:
        if estafador.get("nombre", "").lower() == nombre_completo_nuevo.lower():
            estafador_existente = estafador
            break

    if estafador_existente:
        added_info = []
        if "cam4_users" not in estafador_existente:
            estafador_existente["cam4_users"] = []
        if "telegram_users" not in estafador_existente:
            estafador_existente["telegram_users"] = []

        if user_cam4_nuevo and user_cam4_nuevo not in estafador_existente["cam4_users"]:
            estafador_existente["cam4_users"].append(user_cam4_nuevo)
            added_info.append(f"CAM4: {user_cam4_nuevo}")
        if user_telegram_nuevo and user_telegram_nuevo not in estafador_existente["telegram_users"]:
            estafador_existente["telegram_users"].append(user_telegram_nuevo)
            added_info.append(f"Telegram: {user_telegram_nuevo}")

        if added_info:
            guardar_estafadores()
            await update.message.reply_text(
                f"Estafador '{nombre_completo_nuevo}' ya existía. Se añadió:\n- " + "\n- ".join(added_info)
            )
        else:
            await update.message.reply_text(
                f"El estafador '{nombre_completo_nuevo}' ya existe y los usuarios proporcionados ya estaban registrados."
            )
    else:
        nuevo_estafador = {
            "nombre": nombre_completo_nuevo,
            "cam4_users": [user_cam4_nuevo] if user_cam4_nuevo else [],
            "telegram_users": [user_telegram_nuevo] if user_telegram_nuevo else []
        }
        estafadores.append(nuevo_estafador)
        guardar_estafadores()
        await update.message.reply_text(
            f"Nuevo estafador '{nombre_completo_nuevo}' agregado a la lista con CAM4: {user_cam4_nuevo}, Telegram: {user_telegram_nuevo}."
        )


async def listar_estafadores(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not estafadores:
        await update.message.reply_text("La lista de estafadores está vacía.")
        return

    texto_lista_estafadores = "Lista de Estafadores:\n\n"
    for i, estafador in enumerate(estafadores, 1):
        nombre = estafador.get("nombre", "Nombre Desconocido")
        cam4_users = ", ".join(estafador.get("cam4_users", [])) if estafador.get("cam4_users") else "N/A"
        telegram_users = ", ".join(estafador.get("telegram_users", [])) if estafador.get("telegram_users") else "N/A"

        texto_lista_estafadores += f"{i}. **Nombre:** {nombre}\n"
        texto_lista_estafadores += f"   **CAM4:** {cam4_users}\n"
        texto_lista_estafadores += f"   **Telegram:** {telegram_users}\n\n"

    await update.message.reply_text(texto_lista_estafadores, parse_mode='Markdown')

# ... (todo el código anterior, sin cambios hasta la función buscar_estafador) ...

# --- FUNCIÓN buscar_estafador CON BÚSQUEDA MÁS PRECISA POR PALABRAS ---
async def buscar_estafador(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Busca un estafador por nombre, usuario de CAM4 o Telegram, con coincidencia aproximada, priorizando palabras."""
    if not context.args:
        await update.message.reply_text(
            "Por favor, proporciona el nombre, usuario de CAM4 o usuario de Telegram para buscar. Ejemplo: `/buscar_estafador Juanita`"
        )
        return

    query = " ".join(context.args).strip().lower() # La cadena de búsqueda del usuario
    
    # --- AJUSTES DE SIMILITUD PARA MEJOR COINCIDENCIA POR PALABRA/TOKEN ---
    # Opción 1: fuzz.token_sort_ratio (recomendado para este caso)
    # Compara la cadena de búsqueda y las opciones después de ordenar alfabéticamente sus palabras (tokens).
    # Es bueno para cuando el orden de las palabras no importa, y es menos permisivo que partial_ratio.
    scorer_method = fuzz.token_sort_ratio 

    # Opción 2: fuzz.partial_ratio con un umbral más alto (si la anterior no es suficiente)
    # Este sigue siendo bueno para substrings, pero un umbral más alto lo hace más estricto.
    # scorer_method = fuzz.partial_ratio

    # Opción 3: fuzz.ratio (más estricto, ideal para coincidencias casi exactas)
    # scorer_method = fuzz.ratio

    # Umbral de similitud.
    # Ajusta este valor (entre 0 y 100) hasta encontrar el balance deseado.
    # Para 3 caracteres en una palabra, 40-60 podría ser un buen punto de partida.
    # Si "jua" en "juanita" (6-7 letras) es un 50% de match, un 40-50 puede ser bueno.
    threshold = 50 # Ajusta según prueba y error.

    # Límite de resultados a procesar de fuzzywuzzy
    limit_results = 15 # Aumentado por si hay varias coincidencias relevantes

    all_searchable_strings = []
    estafador_by_string_index = [] 

    for estafador_data in estafadores:
        nombre = estafador_data.get("nombre", "")
        cam4_users = estafador_data.get("cam4_users", [])
        telegram_users = estafador_data.get("telegram_users", [])

        if nombre:
            all_searchable_strings.append(nombre.lower())
            estafador_by_string_index.append(estafador_data)
        for cam4_user in cam4_users:
            all_searchable_strings.append(cam4_user.lower())
            estafador_by_string_index.append(estafador_data)
        for telegram_user in telegram_users:
            all_searchable_strings.append(telegram_user.lower())
            estafador_by_string_index.append(estafador_data)
            
    if not all_searchable_strings:
        await update.message.reply_text("La lista de estafadores está vacía, no hay nada que buscar.")
        return

    try:
        results = process.extract(query, all_searchable_strings, scorer=scorer_method, limit=limit_results)
        
        logger.info(f"Consulta de búsqueda: {query}")
        logger.info(f"Umbral de similitud: {threshold}")
        logger.info(f"Método de comparación: {scorer_method.__name__}")
        logger.info(f"Cadenas disponibles para buscar: {all_searchable_strings}")
        logger.info(f"Resultados brutos de process.extract: {results}")

    except Exception as e:
        logger.error(f"Error al llamar a process.extract: {e}")
        await update.message.reply_text(
            "Hubo un error interno al intentar buscar estafadores. Por favor, inténtalo de nuevo más tarde."
        )
        return

    unique_matches = {} 

    for item in results:
        matched_string = None
        score = None
        index_in_choices_only = None

        if len(item) == 3:
            matched_string, score, index_in_choices_only = item
        elif len(item) == 2:
            matched_string, score = item
            try:
                index_in_choices_only = all_searchable_strings.index(matched_string)
                logger.info(f"Índice encontrado manualmente para '{matched_string}': {index_in_choices_only}")
            except ValueError:
                logger.warning(f"No se pudo encontrar el índice para '{matched_string}'. Este resultado será omitido.")
                continue
        else:
            logger.warning(f"Se encontró un resultado con un número inesperado de valores (ni 2 ni 3): {item}. Este item será omitido.")
            continue

        if matched_string and score is not None and index_in_choices_only is not None:
            if score >= threshold:
                original_estafador_data = estafador_by_string_index[index_in_choices_only]
                
                estafador_id = original_estafador_data.get("nombre", f"obj_{id(original_estafador_data)}")
                
                if estafador_id not in unique_matches:
                    unique_matches[estafador_id] = original_estafador_data
    
    if unique_matches:
        response_text = "Resultados de la búsqueda (coincidencia aproximada):\n\n"
        for estafador_info in unique_matches.values():
            nombre = estafador_info.get("nombre", "Nombre Desconocido")
            cam4_users = ", ".join(estafador_info.get("cam4_users", [])) if estafador_info.get("cam4_users") else "N/A"
            telegram_users = ", ".join(estafador_info.get("telegram_users", [])) if estafador_info.get("telegram_users") else "N/A"

            response_text += f"**Nombre:** {nombre}\n"
            response_text += f"   **CAM4:** {cam4_users}\n"
            response_text += f"   **Telegram:** {telegram_users}\n\n"
            # comentario
    else:
        response_text = f"No se encontraron estafadores que coincidan con '{query}' con un umbral de similitud de {threshold}% o más."
        response_text += "\n\nIntenta con una palabra clave diferente o un umbral más bajo si no obtienes resultados."

    await update.message.reply_text(response_text, parse_mode='Markdown')

# ... (resto del código del bot sin cambios) ...

async def iniciar_reporte(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "¡Perfecto! Para tu reporte, necesito algunos detalles. Por favor, envía el **usuario de CAM4 o link del perfil**:"
    )
    context.user_data['report_data'] = {}
    return PEDIR_TEXTO_1

async def user_cam4_reporte(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message.text:
        await update.message.reply_text("Por favor, envía un **texto** para el usuario de CAM4. Intenta de nuevo.")
        return PEDIR_TEXTO_1

    texto_1 = update.message.text
    context.user_data['report_data']['cam4_user'] = texto_1
    await update.message.reply_text(
        "Gracias. Ahora, por favor, envía el **usuario de Telegram** (ej. @pepito):"
    )
    return PEDIR_TEXTO_2

async def user_telegram_reporte(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message.text:
        await update.message.reply_text("Por favor, envía un **texto** para el usuario de Telegram. Intenta de nuevo.")
        return PEDIR_TEXTO_2

    texto_2 = update.message.text
    context.user_data['report_data']['telegram_user'] = texto_2
    await update.message.reply_text(
        "Casi listo. Por favor, envía el **nombre completo de la modelo/estafadora** (ej. Juana Pérez):"
    )
    return PEDIR_TEXTO_3

async def nombre_completo_reporte(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message.text:
        await update.message.reply_text("Por favor, envía un **texto** para el nombre completo. Intenta de nuevo.")
        return PEDIR_TEXTO_3

    texto_3 = update.message.text
    context.user_data['report_data']['nombre_estafador'] = texto_3
    await update.message.reply_text(
        "¡Excelente! Ahora, por favor, envía la **FOTO** como prueba de tu reporte. Recordá que se tiene que ver la transferencia en el chat y ocultar tus datos para más privacidad."
    )
    return PEDIR_FOTO

async def manejar_foto_reporte(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    report_data = context.user_data.get('report_data', {})

    cam4_user_reporte = report_data.get('cam4_user', 'No proporcionado')
    telegram_user_reporte = report_data.get('telegram_user', 'No proporcionado')
    nombre_estafador_reporte = report_data.get('nombre_estafador', 'No proporcionado')

    if not update.message.photo:
        await update.message.reply_text("Por favor, envía una **FOTO** válida. Intenta de nuevo.")
        return PEDIR_FOTO

    photo_file_id = update.message.photo[-1].file_id

    descripcion = f"🚨 **NUEVO REPORTE DE ESTAFA** 🚨\n\n"
    descripcion += f"**Usuario CAM4:** {cam4_user_reporte}\n"
    descripcion += f"**Usuario Telegram (reportado):** {telegram_user_reporte}\n"
    descripcion += f"**Nombre (reportado):** {nombre_estafador_reporte}\n\n"
    descripcion += f"--- Información del Remitente ---\n"
    descripcion += f"Usuario Telegram: @{user.username or 'No disponible'}\n"
    descripcion += f"Nombre Completo: {user.full_name}\n"
    descripcion += f"ID de Usuario: {user.id}"

    try:
        await context.bot.send_photo(
            chat_id=ID_CANAL_FOTOS,
            photo=photo_file_id,
            caption=descripcion,
            parse_mode='Markdown'
        )
        await update.message.reply_text(
            "¡Gracias! Tu reporte ha sido enviado al canal para revisión."
        )
    except Exception as e:
        logger.error(f"Error al enviar la foto al canal: {e}")
        await update.message.reply_text(
            "Hubo un error al enviar tu reporte al canal. Por favor, inténtalo de nuevo más tarde."
        )

    if 'report_data' in context.user_data:
        del context.user_data['report_data']
    return ConversationHandler.END


async def cancelar_reporte(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if 'report_data' in context.user_data:
        del context.user_data['report_data']
    await update.message.reply_text(
        "Reporte cancelado. Puedes iniciar uno nuevo con /enviar_reporte."
    )
    return ConversationHandler.END


async def manejar_error(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.warning(f"La actualización {update} causó el error {context.error}")
    if update.message:
        await update.message.reply_text(
            "¡Ups! Ha ocurrido un error. Por favor, inténtalo de nuevo más tarde."
        )


def main() -> None:
    cargar_estafadores()
    application = Application.builder().token(TOKEN_BOT).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("agregar_estafador", agregar_estafador))
    application.add_handler(CommandHandler("listar_estafadores", listar_estafadores))
    application.add_handler(CommandHandler("buscar_estafador", buscar_estafador))

    conv_handler_reporte = ConversationHandler(
        entry_points=[CommandHandler("enviar_reporte", iniciar_reporte)],
        states={
            PEDIR_TEXTO_1: [MessageHandler(filters.TEXT & ~filters.COMMAND, user_cam4_reporte)],
            PEDIR_TEXTO_2: [MessageHandler(filters.TEXT & ~filters.COMMAND, user_telegram_reporte)],
            PEDIR_TEXTO_3: [MessageHandler(filters.TEXT & ~filters.COMMAND, nombre_completo_reporte)],
            PEDIR_FOTO: [MessageHandler(filters.PHOTO, manejar_foto_reporte)],
        },
        fallbacks=[CommandHandler("cancelar", cancelar_reporte)],
    )
    application.add_handler(conv_handler_reporte)

    application.add_error_handler(manejar_error)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()