import os
import tempfile
import threading
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from fit_parser import parse_fit_file_safe
from database import insert_parsed_activity

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 ¡Hola! Envíame o comparte cualquier archivo .FIT desde tu reloj y lo guardaré en ggrun automáticamente.")

async def handle_fit_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Detectar archivo adjunto o documento genérico
    document = update.message.document or update.message.effective_attachment
    
    if not document:
        return

    file_name = getattr(document, 'file_name', '') or 'actividad.fit'
    
    # Validar extensión .fit
    if not file_name.lower().endswith('.fit'):
        await update.message.reply_text("⚠️ El archivo recibido no tiene extensión .FIT")
        return

    await update.message.reply_text("📥 Recibido. Procesando entrenamiento...")
    
    temp_path = None
    try:
        tg_file = await context.bot.get_file(document.file_id)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".fit") as temp_file:
            temp_path = temp_file.name
            await tg_file.download_to_drive(temp_path)

        session, laps, debug_info = parse_fit_file_safe(temp_path)
        success, msg = insert_parsed_activity("Gonzalo", file_name, session, laps)

        if success:
            response = (
                f"✅ *¡Entrenamiento Guardado!*\n\n"
                f"🏃 *Deporte:* {session['sport'].capitalize()}\n"
                f"📏 *Distancia:* {session['total_distance_km']} km\n"
                f"⏱️ *Tiempo:* {session['total_duration_min']} min\n"
                f"⚡ *Ritmo medio:* {session['avg_pace']} min/km\n"
                f"❤️ *FC Media:* {session['avg_hr']} ppm"
            )
        else:
            response = f"❌ Error guardando en base de datos: {msg}"
    except Exception as e:
        response = f"❌ Error al procesar el archivo: {str(e)}"
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

    await update.message.reply_text(response, parse_mode="Markdown")

def run_async_bot():
    """Gestiona el event loop de asyncio en el hilo secundario"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def main():
        application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
        application.add_handler(CommandHandler("start", start))
        # Captura cualquier documento o archivo adjunto recibido
        application.add_handler(MessageHandler(filters.ATTACHMENT | filters.Document.ALL, handle_fit_file))
        
        await application.initialize()
        await application.start()
        await application.updater.start_polling(drop_pending_updates=True)
        
        while True:
            await asyncio.sleep(3600)

    try:
        loop.run_until_complete(main())
    except Exception as e:
        print(f"❌ Error en el bot de Telegram: {e}")

def launch_telegram_bot():
    if not TELEGRAM_BOT_TOKEN:
        print("⚠️ TELEGRAM_BOT_TOKEN no configurado en las variables de entorno.")
        return
    bot_thread = threading.Thread(target=run_async_bot, daemon=True)
    bot_thread.start()
    print("🤖 Bot de Telegram iniciado correctamente en segundo plano.")