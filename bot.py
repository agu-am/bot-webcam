import logging
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
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

# Nuevo diccionario para almacenar reportes pendientes con sus datos completos
# La clave será el message_id del mensaje enviado al canal
pending_reports = {}


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

    nombres_unicos = sorted(list(set(e.get("nombre", "Nombre Desconocido") for e in estafadores if e.get("nombre"))))
    cam4_unicos = sorted(list(set(user for e in estafadores for user in e.get("cam4_users", []))))
    telegram_unicos = sorted(list(set(user for e in estafadores for user in e.get("telegram_users", []))))

    response_text = "--- Lista de Estafadores ---\n\n"

    if nombres_unicos:
        response_text += "**Nombres Completos:**\n"
        for i, nombre in enumerate(nombres_unicos, 1):
            response_text += f"{i}. {nombre}\n"
        response_text += "\n"
    else:
        response_text += "**Nombres Completos:** (Ninguno registrado)\n\n"

    if cam4_unicos:
        response_text += "**Usuarios CAM4:**\n"
        for i, user in enumerate(cam4_unicos, 1):
            response_text += f"{i}. {user}\n"
        response_text += "\n"
    else:
        response_text += "**Usuarios CAM4:** (Ninguno registrado)\n\n"

    if telegram_unicos:
        response_text += "**Usuarios Telegram:**\n"
        for i, user in enumerate(telegram_unicos, 1):
            response_text += f"{i}. {user}\n"
        response_text += "\n"
    else:
        response_text += "**Usuarios Telegram:** (Ninguno registrado)\n\n"

    await update.message.reply_text(response_text, parse_mode='Markdown')

async def buscar_estafador(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Busca un estafador por nombre, usuario de CAM4 o Telegram, con coincidencia aproximada, priorizando palabras."""
    if not context.args:
        await update.message.reply_text(
            "Por favor, proporciona el nombre, usuario de CAM4 o usuario de Telegram para buscar. Ejemplo: `/buscar_estafador Juanita`"
        )
        return

    query = " ".join(context.args).strip().lower() # La cadena de búsqueda del usuario
    
    # Si la consulta es muy corta, es probable que no sea precisa
    if len(query) < 3:
        await update.message.reply_text(
            "Por favor, introduce al menos **3 caracteres** para una búsqueda más precisa."
        )
        return

    scorer_method = fuzz.token_sort_ratio 
    threshold = 60 
    limit_results = 20

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
            response_text += f"  **CAM4:** {cam4_users}\n"
            response_text += f"  **Telegram:** {telegram_users}\n\n"
    else:
        response_text = f"No se encontraron estafadores que coincidan con '{query}' con un umbral de similitud de {threshold}% o más."
        response_text += "\n\nIntenta con una palabra clave diferente o un umbral más bajo si no obtienes resultados."

    await update.message.reply_text(response_text, parse_mode='Markdown')

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

## Modificación en `manejar_foto_reporte`

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
        sent_message = await context.bot.send_photo(
            chat_id=ID_CANAL_FOTOS,
            photo=photo_file_id,
            caption=descripcion,
            parse_mode='Markdown'
        )
        
        # Almacena los datos del reporte usando el message_id del mensaje enviado al canal
        report_id = str(sent_message.message_id) # Convertir a string para usar como clave
        pending_reports[report_id] = {
            "nombre": nombre_estafador_reporte,
            "cam4": cam4_user_reporte,
            "telegram": telegram_user_reporte
        }
        logger.info(f"Reporte almacenado temporalmente con ID: {report_id}")

        # Prepara los callback_data con el ID del reporte
        callback_data_add = f"add_scammer_{report_id}" # Formato: acción_id_del_reporte
        callback_data_delete = "delete_report_message" # No necesita ID, solo eliminar el mensaje

        # Define la botonera
        keyboard = [
            [
                InlineKeyboardButton("✅ Agregar a Estafadores", callback_data=callback_data_add),
                InlineKeyboardButton("🗑️ Eliminar Mensaje", callback_data=callback_data_delete)
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Edita el mensaje para añadir la botonera
        await sent_message.edit_reply_markup(reply_markup=reply_markup)

        await update.message.reply_text(
            "¡Gracias! Tu reporte ha sido enviado al canal para revisión y se han añadido botones para gestionarlo."
        )
    except Exception as e:
        logger.error(f"Error al enviar la foto al canal o añadir botonera: {e}")
        await update.message.reply_text(
            "Hubo un error al enviar tu reporte al canal o al añadir los botones. Por favor, inténtalo de nuevo más tarde."
        )

    if 'report_data' in context.user_data:
        del context.user_data['report_data']
    return ConversationHandler.END

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer() # Siempre responde a la callback query

    user_id = query.from_user.id
    if user_id != ID_ADMIN:
        await query.edit_message_text("¡No tienes permiso para realizar esta acción!")
        return

    callback_data = query.data
    message_id_str = str(query.message.message_id) # Obtener el message_id del mensaje donde se presionó el botón

    if callback_data == "delete_report_message":
        try:
            await query.message.delete()
            # Opcional: limpiar de pending_reports si se elimina sin agregar
            if message_id_str in pending_reports:
                del pending_reports[message_id_str]
                logger.info(f"Reporte con ID {message_id_str} eliminado de pending_reports.")
            logger.info(f"Mensaje de reporte eliminado por el admin {user_id}.")
        except Exception as e:
            logger.error(f"Error al intentar eliminar el mensaje: {e}")
            await query.edit_message_text("No se pudo eliminar el mensaje.")
        return

    # Si el callback_data empieza con "add_scammer_", procesar
    if callback_data.startswith("add_scammer_"):
        report_id = callback_data.replace("add_scammer_", "")
        
        if report_id not in pending_reports:
            await query.edit_message_caption(
                caption=f"{query.message.caption}\n\n⚠️ **Error:** Datos del reporte no encontrados. El reporte puede haber sido procesado o el bot se reinició.",
                parse_mode='Markdown',
                reply_markup=None
            )
            logger.warning(f"Intento de añadir estafador con ID {report_id} pero no se encontró en pending_reports.")
            return

        report_data = pending_reports[report_id]
        nombre_completo_nuevo = report_data.get("nombre", "")
        user_cam4_nuevo = report_data.get("cam4", "")
        user_telegram_nuevo = report_data.get("telegram", "")

        estafador_existente = None
        for estafador in estafadores:
            if estafador.get("nombre", "").lower() == nombre_completo_nuevo.lower():
                estafador_existente = estafador
                break

        response_text = ""
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
                response_text = f"Estafador **'{nombre_completo_nuevo}'** ya existía. Se añadió:\n- " + "\n- ".join(added_info)
            else:
                response_text = f"El estafador **'{nombre_completo_nuevo}'** ya existe y los usuarios proporcionados ya estaban registrados."
        else:
            nuevo_estafador = {
                "nombre": nombre_completo_nuevo,
                "cam4_users": [user_cam4_nuevo] if user_cam4_nuevo else [],
                "telegram_users": [user_telegram_nuevo] if user_telegram_nuevo else []
            }
            estafadores.append(nuevo_estafador)
            guardar_estafadores()
            response_text = f"Nuevo estafador **'{nombre_completo_nuevo}'** agregado a la lista con CAM4: {user_cam4_nuevo}, Telegram: {user_telegram_nuevo}."
        
        # Eliminar el reporte de la lista temporal después de procesarlo
        if report_id in pending_reports:
            del pending_reports[report_id]
            logger.info(f"Reporte con ID {report_id} procesado y eliminado de pending_reports.")

        # Edita el mensaje original para indicar que se añadió a la lista
        original_caption = query.message.caption if query.message.caption else ""
        await query.edit_message_caption(
            caption=f"{original_caption}\n\n✔️ {response_text}",
            parse_mode='Markdown',
            reply_markup=None # Quitar la botonera después de la acción para evitar reprocesar
        )
        logger.info(f"Reporte de estafador procesado: {nombre_completo_nuevo}.")

    else:
        logger.warning(f"Callback data desconocida: {callback_data}")
        await query.edit_message_text("Acción de botón desconocida.")
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

    # Añade este manejador para los botones inline
    application.add_handler(CallbackQueryHandler(button_callback_handler))

    application.add_error_handler(manejar_error)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()