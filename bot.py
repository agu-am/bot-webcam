import asyncio
from telegram.error import BadRequest
import time
import logging
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
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

# --- Configuración de Estados para la Conversación ---
PEDIR_TEXTO_1 = 1
PEDIR_TEXTO_2 = 2
PEDIR_TEXTO_3 = 3
PEDIR_FOTO = 4 # Este estado ahora permite el envío de múltiples fotos

# --- Importar Configuraciones (asegúrate de tener un archivo config.py) ---
# Ejemplo de config.py:
# TOKEN_BOT = "TU_TOKEN_DE_BOT"
# ID_ADMIN = TU_ID_DE_USUARIO_ADMIN # Debe ser un número entero
# ID_CANAL_FOTOS = TU_ID_DE_CANAL_DE_FOTOS # Debe ser un número entero (ej. -1001234567890)
from config import TOKEN_BOT, ID_ADMIN, ID_CANAL_FOTOS

# --- Configuración de Logging ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Variables Globales ---
ARCHIVO_ESTAFADORES = "estafadores.json"
estafadores = []

# Diccionario para almacenar temporalmente los datos de reportes pendientes.
# La clave es el message_id del mensaje enviado al canal.
pending_reports = {}

# --- Funciones de Utilidad para Cargar/Guardar Estafadores ---
def cargar_estafadores():
    """Carga la lista de estafadores desde el archivo JSON."""
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
    """Guarda la lista de estafadores en el archivo JSON."""
    with open(ARCHIVO_ESTAFADORES, "w", encoding="utf-8") as f:
        json.dump(estafadores, f, ensure_ascii=False, indent=4)
    logger.info("Estafadores guardados.")

# --- Comandos del Bot ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envía un mensaje de bienvenida."""
    await update.message.reply_text(
        "¡Hola! Soy un bot para reportar estafadores. Usa /enviar_reporte para comenzar."
    )

async def agregar_estafador(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Agrega un estafador a la lista. Requiere permisos de administrador.
    Formato: /agregar_estafador [Nombre Completo]; [Usuario CAM4]; [Usuario Telegram]
    """
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
    """Lista todos los estafadores registrados, ordenados alfabéticamente."""
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

    query = " ".join(context.args).strip().lower() 
    
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

# --- Flujo de Conversación para Reportes ---
async def iniciar_reporte(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia la conversación para un nuevo reporte de estafador."""
    await update.message.reply_text(
        "¡Perfecto! Para tu reporte, necesito algunos detalles. Por favor, envía el **usuario de CAM4 o link del perfil**:"
    )
    context.user_data['report_data'] = {'photos': []} # Inicializa una lista vacía para las fotos
    return PEDIR_TEXTO_1

async def user_cam4_reporte(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Guarda el usuario de CAM4 y pide el usuario de Telegram."""
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
    """Guarda el usuario de Telegram y pide el nombre completo de la modelo/estafadora."""
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
    """Guarda el nombre completo y pide las fotos."""
    if not update.message.text:
        await update.message.reply_text("Por favor, envía un **texto** para el nombre completo. Intenta de nuevo.")
        return PEDIR_TEXTO_3

    texto_3 = update.message.text
    context.user_data['report_data']['nombre_estafador'] = texto_3
    await update.message.reply_text(
        "¡Excelente! Ahora, por favor, envía las **FOTOS** como prueba de tu reporte (puedes enviar varias). Recordá que se tiene que ver la transferencia en el chat y ocultar tus datos para más privacidad.\n\n"
        "Cuando hayas terminado de enviar todas las fotos, usa el comando /finalizar_fotos"
    )
    return PEDIR_FOTO

async def manejar_foto_reporte(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Maneja cada foto enviada, almacenando su file_id."""
    if not update.message.photo:
        await update.message.reply_text("Por favor, envía una **FOTO** válida. Intenta de nuevo.")
        return PEDIR_FOTO

    photo_file_id = update.message.photo[-1].file_id # Obtiene la mejor calidad de la foto
    context.user_data['report_data']['photos'].append(photo_file_id) # Agrega el ID de la foto a la lista

    await update.message.reply_text(
        "Foto recibida. Puedes enviar más fotos o usar el comando /finalizar_fotos para terminar el reporte."
    )
    return PEDIR_FOTO # Se mantiene en el mismo estado para permitir más fotos

async def finalizar_fotos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Finaliza el proceso de envío de fotos. Envía la primera foto con descripción y botones.
    Las fotos subsiguientes se envían individualmente como respuestas a la primera.
    """
    user = update.effective_user
    report_data = context.user_data.get('report_data', {})

    cam4_user_reporte = report_data.get('cam4_user', 'No proporcionado')
    telegram_user_reporte = report_data.get('telegram_user', 'No proporcionado')
    nombre_estafador_reporte = report_data.get('nombre_estafador', 'No proporcionado')
    photos_file_ids = report_data.get('photos', [])

    # Verificar si se han enviado fotos
    if not photos_file_ids:
        await update.message.reply_text(
            "No has enviado ninguna foto. Por favor, envía al menos una antes de finalizar el reporte."
        )
        return PEDIR_FOTO # Mantener en el estado de pedir foto

    # Construir la descripción del reporte para el caption de la primera foto
    descripcion = f"🚨 **NUEVO REPORTE DE ESTAFA** 🚨\n\n"
    descripcion += f"**Usuario CAM4:** {cam4_user_reporte}\n"
    descripcion += f"**Usuario Telegram (reportado):** {telegram_user_reporte}\n"
    descripcion += f"**Nombre (reportado):** {nombre_estafador_reporte}\n\n"
    descripcion += f"--- Información del Remitente ---\n"
    descripcion += f"Usuario Telegram: @{user.username or 'No disponible'}\n"
    descripcion += f"Nombre Completo: {user.full_name}\n"
    descripcion += f"ID de Usuario: {user.id}"

    # Preparar los botones inline. El 'callback_data' del botón "Agregar a Estafadores"
    # se actualizará después de enviar la primera foto para incluir su Message ID.
    callback_data_delete = "delete_report_message" 

    keyboard = [
        [
            # Placeholder temporal para callback_data; se reemplazará con el message_id real
            InlineKeyboardButton("✅ Agregar a Estafadores", callback_data="temp_placeholder"),
            InlineKeyboardButton("🗑️ Eliminar Mensaje", callback_data=callback_data_delete)
        ]
    ]
    reply_markup_initial = InlineKeyboardMarkup(keyboard)

    try:
        # 1. Enviar la PRIMERA foto con su descripción y CON LA BOTONERA directamente.
        # Al usar 'send_photo', los botones se adjuntan en la misma llamada.
        sent_message = await context.bot.send_photo(
            chat_id=ID_CANAL_FOTOS,
            photo=photos_file_ids[0],
            caption=descripcion,
            parse_mode='Markdown',
            reply_markup=reply_markup_initial # Aquí se adjunta la botonera
        )

        # Usamos el message_id de la primera foto como el ID único para este reporte.
        report_id = str(sent_message.message_id) 

        # Actualizar el callback_data para el botón "Agregar a Estafadores"
        # con el 'report_id' real (el message_id de la primera foto).
        updated_keyboard = [
            [
                InlineKeyboardButton("✅ Agregar a Estafadores", callback_data=f"add_scammer_{report_id}"),
                InlineKeyboardButton("🗑️ Eliminar Mensaje", callback_data=callback_data_delete)
            ]
        ]
        updated_reply_markup = InlineKeyboardMarkup(updated_keyboard)

        # Intentar editar el mensaje para actualizar el callback_data.
        # Esto también sirve como una "confirmación" de que la botonera está en su lugar.
        try:
            await sent_message.edit_reply_markup(reply_markup=updated_reply_markup)
            logger.info(f"Botonera principal del reporte {report_id} confirmada/actualizada con ID real.")
        except BadRequest as e:
            # Si el error es "Message is not modified", significa que los botones ya estaban correctamente.
            if "Message is not modified" in str(e):
                logger.info(f"Botonera para reporte {report_id} ya estaba en su lugar. No se necesitó edición del callback_data.")
            else:
                # Si es otro tipo de error de BadRequest, lo logueamos y lo propagamos.
                logger.error(f"Error inesperado al intentar actualizar botonera principal de reporte {report_id}: {e}")
                raise e 

        # Almacenar los datos del reporte completo en `pending_reports` usando el report_id.
        pending_reports[report_id] = {
            "nombre": nombre_estafador_reporte,
            "cam4": cam4_user_reporte,
            "telegram": telegram_user_reporte
        }
        logger.info(f"Reporte con ID {report_id} almacenado temporalmente (primera foto con botones).")

        # 2. Enviar las fotos subsiguientes (si las hay) como respuestas a la primera foto.
        # Esto las "agrupa" visualmente en el chat.
        if len(photos_file_ids) > 1:
            for photo_id in photos_file_ids[1:]:
                await context.bot.send_photo(
                    chat_id=ID_CANAL_FOTOS,
                    photo=photo_id,
                    reply_to_message_id=sent_message.message_id # Hace que la foto responda a la primera
                    # Estas fotos no llevan caption ni botones
                )
                await asyncio.sleep(0.1) # Pequeña pausa para evitar límites de tasa de Telegram

        # Informar al usuario que el reporte ha sido enviado.
        await update.message.reply_text(
            "¡Gracias! Tu reporte ha sido enviado al canal para revisión y se han añadido botones para gestionarlo."
        )

    except Exception as e:
        # Captura cualquier error general durante el proceso de envío de fotos.
        logger.error(f"Error general al enviar las fotos del reporte: {e}")
        await update.message.reply_text(
            "Hubo un error al enviar tu reporte. Por favor, inténtalo de nuevo más tarde."
        )

    # Limpiar los datos del usuario después de que el reporte ha sido gestionado.
    if 'report_data' in context.user_data:
        del context.user_data['report_data']
        
    # Finalizar la conversación.
    return ConversationHandler.END

# --- Manejo de Callbacks de Botones Inline ---
async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer() # Siempre responde a la callback query

    user_id = query.from_user.id
    if user_id != ID_ADMIN:
        await query.edit_message_text("¡No tienes permiso para realizar esta acción!")
        return

    callback_data = query.data
    message_id_str = str(query.message.message_id) 

    if callback_data == "delete_report_message":
        try:
            await query.message.delete() 
            if message_id_str in pending_reports:
                del pending_reports[message_id_str]
                logger.info(f"Reporte con ID {message_id_str} eliminado de pending_reports.")
            logger.info(f"Mensaje de reporte eliminado por el admin {user_id}.")
        except Exception as e:
            logger.error(f"Error al intentar eliminar el mensaje: {e}")
            await query.edit_message_text("No se pudo eliminar el mensaje.")
        return

    if callback_data.startswith("add_scammer_"):
        report_id = callback_data.replace("add_scammer_", "")
        
        if report_id not in pending_reports:
            # Si los datos no se encuentran, puede que el bot se reiniciara o ya se procesó.
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
        
        # *** CAMBIO CLAVE AQUÍ: Añadir un sufijo único (timestamp) ***
        unique_suffix = f" (Actualizado: {int(time.time())})" 
        
        await query.edit_message_caption(
            caption=f"{original_caption}\n\n✔️ {response_text}{unique_suffix}", # Se agrega el sufijo único
            parse_mode='Markdown',
            reply_markup=None # Quitar la botonera después de la acción para evitar reprocesar
        )
        logger.info(f"Reporte de estafador procesado: {nombre_completo_nuevo}.")

    else:
        logger.warning(f"Callback data desconocida: {callback_data}")
        await query.edit_message_text("Acción de botón desconocida.")
# --- Manejo de Errores y Cancelación ---
async def cancelar_reporte(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancela la conversación de reporte."""
    if 'report_data' in context.user_data:
        del context.user_data['report_data']
    await update.message.reply_text(
        "Reporte cancelado. Puedes iniciar uno nuevo con /enviar_reporte."
    )
    return ConversationHandler.END

async def manejar_error(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja los errores del bot."""
    logger.warning(f"La actualización {update} causó el error {context.error}")
    if update.message:
        await update.message.reply_text(
            "¡Ups! Ha ocurrido un error. Por favor, inténtalo de nuevo más tarde."
        )

# --- Función Principal del Bot ---
def main() -> None:
    """Configura y ejecuta el bot."""
    cargar_estafadores() # Carga la lista de estafadores al iniciar el bot

    application = Application.builder().token(TOKEN_BOT).build()

    # Comandos generales
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("agregar_estafador", agregar_estafador))
    application.add_handler(CommandHandler("listar_estafadores", listar_estafadores))
    application.add_handler(CommandHandler("buscar_estafador", buscar_estafador))

    # Conversación para enviar reportes
    conv_handler_reporte = ConversationHandler(
        entry_points=[CommandHandler("enviar_reporte", iniciar_reporte)],
        states={
            PEDIR_TEXTO_1: [MessageHandler(filters.TEXT & ~filters.COMMAND, user_cam4_reporte)],
            PEDIR_TEXTO_2: [MessageHandler(filters.TEXT & ~filters.COMMAND, user_telegram_reporte)],
            PEDIR_TEXTO_3: [MessageHandler(filters.TEXT & ~filters.COMMAND, nombre_completo_reporte)],
            PEDIR_FOTO: [
                MessageHandler(filters.PHOTO, manejar_foto_reporte), # Permite enviar múltiples fotos
                CommandHandler("finalizar_fotos", finalizar_fotos), # Comando para terminar el envío de fotos
                CommandHandler("cancelar", cancelar_reporte) # Permitir cancelar en este estado también
            ],
        },
        fallbacks=[CommandHandler("cancelar", cancelar_reporte)], # Comando de fallback global para la conversación
    )
    application.add_handler(conv_handler_reporte)

    # Manejador de callbacks para los botones inline
    application.add_handler(CallbackQueryHandler(button_callback_handler))

    # Manejador de errores
    application.add_error_handler(manejar_error)

    # Inicia el polling del bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()