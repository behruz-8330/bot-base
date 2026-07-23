import os
import shutil
import zipfile
import asyncio
import subprocess
from datetime import datetime
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile, WebAppInfo
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

# --- FASTAPI IMPORTLARI ---
from fastapi import FastAPI, HTTPException, Body
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# --- SOZLAMALAR ---
TOKEN = "8746921322:AAESSZswzjovLzDFD6N6CCA29D7qYxh4fPI"
ADMIN_ID = 6926668577  # Sizning Admin ID'ingiz
BACKUP_GROUP_ID = -1004339696809
WEB_APP_URL = "https://SIZNING_DOMEN_YOKI_NGROK.uz"  # Mini App ishlaydigan manzil

BASE_DIR = "/data/bot"
BACKUP_DIR = "/data/backups"
os.makedirs(BASE_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)

bot = Bot(token=TOKEN)
dp = Dispatcher()
running_processes = {}

# --- FSM (Holatlar) ---
class SessionStates(StatesGroup):
    waiting_for_lib = State()
    waiting_for_api_id = State()
    waiting_for_api_hash = State()
    waiting_for_phone = State()
    waiting_for_code = State()
    waiting_for_password = State()

# --- ASOSIY MENYU TUGMALARI ---
def get_main_menu():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛠 Fayl Muharriri (Mini App)", web_app=WebAppInfo(url=WEB_APP_URL))],
        [InlineKeyboardButton(text="🟢 Faol loyihalar", callback_data="list_projects")],
        [InlineKeyboardButton(text="🗑 Loyihani o'chirish (Remove)", callback_data="remove_project_menu")],
        [InlineKeyboardButton(text="🔑 Sessiya yaratish", callback_data="create_session_start")],
        [InlineKeyboardButton(text="📦 Tezkor Backup olish", callback_data="fast_backup")],
        [InlineKeyboardButton(text="📥 Loyiha import qilish (.zip)", callback_data="help_import")],
        [InlineKeyboardButton(text="🔄 Serverni yangilash / Qayta yoqish", callback_data="restart_all")]
    ])
    return keyboard

# --- START BUYRUĞI ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer(
        "🤖 **Railway Bot Manager paneliga xush kelibsiz!**\n\n"
        "Quyidagi tugmalar yordamida barcha loyihalarni boshqarishingiz mumkin:",
        reply_markup=get_main_menu()
    )

# --- 1. FAOL LOYIHALARNI KO'RSATISH ---
@dp.callback_query(F.data == "list_projects")
async def cb_list_projects(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    
    projects = [d for d in os.listdir(BASE_DIR) if os.path.isdir(os.path.join(BASE_DIR, d))]
    if not projects:
        await callback.message.edit_text("ℹ️ Hozirda `/data/bot` papkasida loyihalar yo'q.", reply_markup=get_main_menu())
        return
        
    text = "🟢 **Loyihalar holati:**\n\n"
    for proj in projects:
        status = "🟢 Ishlayapti" if proj in running_processes else "🔴 To'xtagan"
        text += f"• **{proj}** — {status}\n"
        
    await callback.message.edit_text(text, reply_markup=get_main_menu())

# --- LOYIHANI O'CHIRISH (REMOVE) MENYUSI ---
@dp.callback_query(F.data == "remove_project_menu")
async def cb_remove_project_menu(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
        
    projects = [d for d in os.listdir(BASE_DIR) if os.path.isdir(os.path.join(BASE_DIR, d))]
    if not projects:
        await callback.message.edit_text("ℹ️ O'chirish uchun loyihalar topilmadi.", reply_markup=get_main_menu())
        return
        
    buttons = []
    for proj in projects:
        buttons.append([InlineKeyboardButton(text=f"🗑 O'chirish: {proj}", callback_data=f"del_proj_{proj}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Ortga", callback_data="back_to_menu")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text("🗑 **O'chirmoqchi bo'lgan loyihangizni tanlang:**", reply_markup=keyboard)

@dp.callback_query(F.data.startswith("del_proj_"))
async def cb_delete_project_action(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
        
    project_name = callback.data.replace("del_proj_", "")
    proj_path = os.path.join(BASE_DIR, project_name)
    
    if project_name in running_processes:
        try:
            running_processes[project_name].terminate()
            del running_processes[project_name]
        except Exception:
            pass
            
    if os.path.exists(proj_path):
        shutil.rmtree(proj_path)
        await callback.message.edit_text(f"✅ `{project_name}` loyihasi muvaffaqiyatli o'chirib tashlandi!", reply_markup=get_main_menu())
    else:
        await callback.message.edit_text(f"⚠️ `{project_name}` loyihasi topilmadi yoki allaqachon o'chirilgan.", reply_markup=get_main_menu())

# --- 2. SESSIYA YARATISH JARAYONI ---
@dp.callback_query(F.data == "create_session_start")
async def cb_create_session(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Telethon", callback_data="lib_telethon"),
         InlineKeyboardButton(text="Pyrogram", callback_data="lib_pyrogram")],
        [InlineKeyboardButton(text="⬅️ Ortga", callback_data="back_to_menu")]
    ])
    
    await callback.message.edit_text(
        "🔑 **Sessiya yaratish uchun kutubxonani tanlang:**",
        reply_markup=keyboard
    )
    await state.set_state(SessionStates.waiting_for_lib)

@dp.callback_query(SessionStates.waiting_for_lib, F.data.startswith("lib_"))
async def cb_select_lib(callback: types.CallbackQuery, state: FSMContext):
    lib_name = callback.data.split("_")[1]
    await state.update_data(library=lib_name)
    
    await callback.message.edit_text(
        f"✅ Tanlandi: **{lib_name.capitalize()}**\n\n"
        "Iltimos, Telegram ilovasidan olgan **API_ID** raqamingizni yuboring:"
    )
    await state.set_state(SessionStates.waiting_for_api_id)

@dp.message(SessionStates.waiting_for_api_id)
async def process_api_id(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        api_id = int(message.text.strip())
        await state.update_data(api_id=api_id)
        await message.answer("🔑 Endi esa **API_HASH** matnini yuboring:")
        await state.set_state(SessionStates.waiting_for_api_hash)
    except ValueError:
        await message.answer("❌ API_ID faqat raqamlardan iborat bo'lishi kerak. Qaytadan yuboring:")

@dp.message(SessionStates.waiting_for_api_hash)
async def process_api_hash(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.update_data(api_hash=message.text.strip())
    await message.answer("📞 Telefon raqamingizni xalqaro formatda yuboring (Masalan: `+998901234567`):")
    await state.set_state(SessionStates.waiting_for_phone)

@dp.message(SessionStates.waiting_for_phone)
async def process_phone(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    phone = message.text.strip()
    await state.update_data(phone=phone)
    data = await state.get_data()
    
    lib = data["library"]
    api_id = data["api_id"]
    api_hash = data["api_hash"]
    
    status_msg = await message.answer(f"⏳ Telegramdan tasdiqlash kodi yuborilmoqda ({lib})...")
    
    try:
        if lib == "telethon":
            from telethon import TelegramClient
            from telethon.sessions import StringSession
            
            client = TelegramClient(StringSession(), api_id, api_hash)
            await client.connect()
            sent = await client.send_code_request(phone)
            await state.update_data(client=client, phone_code_hash=sent.phone_code_hash)
            
            await status_msg.edit_text(
                "📥 Telegram ilovangizga kod keldi.\n"
                "Iltimos, kodni raqamlar orasiga bo'sh joy qo'yib yuboring (Masalan: `1 2 3 4 5`):"
            )
            await state.set_state(SessionStates.waiting_for_code)
            
        elif lib == "pyrogram":
            from pyrogram import Client
            
            client = Client("temp_session", api_id=api_id, api_hash=api_hash, in_memory=True)
            await client.connect()
            sent = await client.send_code(phone)
            await state.update_data(client=client, phone_code_hash=sent.phone_code_hash)
            
            await status_msg.edit_text(
                "📥 Telegram ilovangizga Pyrogram uchun kod keldi.\n"
                "Iltimos, kodni raqamlar orasiga bo'sh joy qo'yib yuboring (Masalan: `1 2 3 4 5`):"
            )
            await state.set_state(SessionStates.waiting_for_code)
            
    except Exception as e:
        await status_msg.edit_text(f"❌ Xatolik yuz berdi: {e}\n\nQaytadan boshlash uchun /start bosing.")
        await state.clear()

@dp.message(SessionStates.waiting_for_code)
async def process_code(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
        
    code = message.text.strip().replace(" ", "")
    data = await state.get_data()
    lib = data["library"]
    client = data["client"]
    phone = data["phone"]
    phone_code_hash = data["phone_code_hash"]
    
    try:
        if lib == "telethon":
            from telethon.errors import SessionPasswordNeededError
            try:
                await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
            except SessionPasswordNeededError:
                await message.answer("🔒 Akkauntingizda ikki bosqichli autentifikatsiya (Password) yoqilgan ekan. Iltimos, parolingizni yuboring:")
                await state.set_state(SessionStates.waiting_for_password)
                return
                
            string_session = client.session.save()
            await client.disconnect()
            
            await message.answer(
                f"🎉 **Telethon Session muvaffaqiyatli yaratildi!**\n\n"
                f"Quyidagi string-sessiyani nusxalab oling:\n\n`{string_session}`",
                reply_markup=get_main_menu()
            )
            await state.clear()
            
        elif lib == "pyrogram":
            from pyrogram.errors import SessionPasswordNeededError
            try:
                await client.sign_in(phone, phone_code_hash, code)
            except SessionPasswordNeededError:
                await message.answer("🔒 Akkauntingizda ikki bosqichli autentifikatsiya (Password) yoqilgan ekan. Iltimos, parolingizni yuboring:")
                await state.set_state(SessionStates.waiting_for_password)
                return
                
            string_session = await client.export_session_string()
            await client.disconnect()
            
            await message.answer(
                f"🎉 **Pyrogram Session muvaffaqiyatli yaratildi!**\n\n"
                f"Quyidagi string-sessiyani nusxalab oling:\n\n`{string_session}`",
                reply_markup=get_main_menu()
            )
            await state.clear()
            
    except Exception as e:
        await message.answer(f"❌ Kodni tasdiqlashda xatolik: {e}\n\nQaytadan urinish uchun /start bosing.")
        await state.clear()

@dp.message(SessionStates.waiting_for_password)
async def process_password(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
        
    password = message.text.strip()
    data = await state.get_data()
    lib = data["library"]
    client = data["client"]
    
    try:
        if lib == "telethon":
            await client.sign_in(password=password)
            string_session = client.session.save()
            await client.disconnect()
            
            await message.answer(
                f"🎉 **Telethon Session muvaffaqiyatli yaratildi!**\n\n`{string_session}`",
                reply_markup=get_main_menu()
            )
        elif lib == "pyrogram":
            await client.check_password(password)
            string_session = await client.export_session_string()
            await client.disconnect()
            
            await message.answer(
                f"🎉 **Pyrogram Session muvaffaqiyatli yaratildi!**\n\n`{string_session}`",
                reply_markup=get_main_menu()
            )
        await state.clear()
    except Exception as e:
        await message.answer(f"❌ Parolni tekshirishda xatolik: {e}\n\nQaytadan /start bosing.")
        await state.clear()

@dp.callback_query(F.data == "back_to_menu")
async def cb_back(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await state.clear()
    await callback.message.edit_text(
        "🤖 **Railway Bot Manager paneliga xush kelibsiz!**",
        reply_markup=get_main_menu()
    )

# --- 3. TEZKOR BACKUP OLISH ---
@dp.callback_query(F.data == "fast_backup")
async def cb_fast_backup(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
        
    await callback.message.edit_text("⏳ Tezkor backup tayyorlanmoqda, iltimos kuting...")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    zip_filename = os.path.join(BACKUP_DIR, f"bot_backup_{timestamp}.zip")
    
    try:
        shutil.make_archive(zip_filename.replace('.zip', ''), 'zip', BASE_DIR)
        
        with open(zip_filename, "rb") as f:
            file_bytes = f.read()
            
        input_file = BufferedInputFile(file_bytes, filename=f"backup_{timestamp}.zip")
        
        await bot.send_document(
            chat_id=callback.from_user.id,
            document=input_file,
            caption=f"📦 **Tezkor Volume Backup**\n🕒 Vaqt: `{timestamp}`\n📁 Ichki baza va fayllar to'liq jamlandi."
        )
        os.remove(zip_filename)
        await callback.message.edit_text("✅ Tezkor backup muvaffaqiyatli yuborildi!", reply_markup=get_main_menu())
    except Exception as e:
        await callback.message.edit_text(f"❌ Xatolik yuz berdi: {e}", reply_markup=get_main_menu())

# --- 4. IMPORT QILISH YO'RIQNOMASI ---
@dp.callback_query(F.data == "help_import")
async def cb_help_import(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    await callback.message.edit_text(
        "📥 **Loyiha import qilish tartibi:**\n\n"
        "1. Yangi loyihangizni `.zip` formatida chatga yuboring.\n"
        "2. O'sha yuborgan ZIP faylingizga **reply** qilib quyidagi buyruqni yozing:\n"
        "`/import <loyiha_nomi>`\n\n"
        "Masalan: `/import scheduler-bot`",
        reply_markup=get_main_menu()
    )

# --- ZIP ORQALI IMPORT QILISH ---
@dp.message(Command("import"))
async def cmd_import(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
        
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("❌ Iltimos, loyiha nomini yozing. Masalan: `/import scheduler-bot`")
        return
        
    project_name = parts[1].strip()
    reply = message.reply_to_message
    
    if not reply or not reply.document or not reply.document.file_name.endswith('.zip'):
        await message.answer("❌ Iltimos, `.zip` formatidagi faylga reply qilib ushbu buyruqni yozing!")
        return

    status_msg = await message.answer(f"⏳ `{project_name}` yuklab olinmoqda va o'rnatilmoqda...")
    
    proj_path = os.path.join(BASE_DIR, project_name)
    if os.path.exists(proj_path):
        if project_name in running_processes:
            running_processes[project_name].terminate()
            del running_processes[project_name]
        shutil.rmtree(proj_path)
        
    os.makedirs(proj_path, exist_ok=True)
    
    file_info = await bot.get_file(reply.document.file_id)
    zip_path = os.path.join(BACKUP_DIR, f"{project_name}.zip")
    await bot.download_file(file_info.file_path, destination=zip_path)
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(proj_path)
        os.remove(zip_path)
        
        req_file = os.path.join(proj_path, "requirements.txt")
        if os.path.exists(req_file):
            await status_msg.edit_text(f"📦 Kutubxonalar o'rnatilmoqda (`pip install`)...\nIltimos kuting ⏱")
            subprocess.run(["python", "-m", "pip", "install", "-r", req_file], cwd=proj_path, check=True)

        main_file = os.path.join(proj_path, "main.py")
        if os.path.exists(main_file):
            process = subprocess.Popen(
                ["python", main_file],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=proj_path
            )
            running_processes[project_name] = process
            asyncio.create_task(monitor_project(project_name, process))
            await status_msg.edit_text(f"✅ `{project_name}` muvaffaqiyatli import qilindi va 24/7 rejimda ishga tushdi!", reply_markup=get_main_menu())
        else:
            await status_msg.edit_text(f"⚠️ Loyiha joylandi, lekin ichida `main.py` topilmadi!", reply_markup=get_main_menu())
    except Exception as e:
        await status_msg.edit_text(f"❌ Xatolik yuz berdi: {e}", reply_markup=get_main_menu())

# --- 5. SERVERNI QAYTA YOQISH ---
@dp.callback_query(F.data == "restart_all")
async def cb_restart(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
        
    for proj, proc in list(running_processes.items()):
        proc.terminate()
    running_processes.clear()
    
    start_all_projects_auto()
    await callback.message.edit_text("🔄 Barcha loyihalar qaytadan toza holatda ishga tushirildi!", reply_markup=get_main_menu())

# --- CRASH MONITORING ---
async def monitor_project(project_name, process):
    while True:
        retcode = process.poll()
        if retcode is not None:
            stderr_output = process.stderr.read() if process.stderr else "Noma'lum"
            error_msg = (
                f"🚨 **Crash xabarnomasi!**\n\n"
                f"📁 Loyiha: `{project_name}`\n"
                f"⚠️ **Xato tafsiloti:**\n`{stderr_output[-800:]}`"
            )
            try:
                await bot.send_message(ADMIN_ID, error_msg)
            except:
                pass
            if project_name in running_processes:
                del running_processes[project_name]
            break
        await asyncio.sleep(5)

def start_all_projects_auto():
    if not os.path.exists(BASE_DIR):
        return
    projects = [d for d in os.listdir(BASE_DIR) if os.path.isdir(os.path.join(BASE_DIR, d))]
    for proj in projects:
        proj_path = os.path.join(BASE_DIR, proj)
        main_file = os.path.join(proj_path, "main.py")
        
        req_file = os.path.join(proj_path, "requirements.txt")
        if os.path.exists(req_file):
            try:
                subprocess.run(["python", "-m", "pip", "install", "-r", req_file], cwd=proj_path, check=True)
            except Exception as e:
                print(f"Kutubxonalarni o'rnatishda xato ({proj}): {e}")

        if os.path.exists(main_file) and proj not in running_processes:
            try:
                process = subprocess.Popen(
                    ["python", main_file],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    cwd=proj_path
                )
                running_processes[proj] = process
                asyncio.create_task(monitor_project(proj, process))
            except Exception as e:
                print(f"Xato ({proj}): {e}")

# --- 12 SOATLIK AVTO-BACKUP ---
async def scheduled_backup_task():
    while True:
        await asyncio.sleep(12 * 60 * 60)
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
            zip_filename = os.path.join(BACKUP_DIR, f"auto_backup_{timestamp}.zip")
            
            shutil.make_archive(zip_filename.replace('.zip', ''), 'zip', BASE_DIR)
            
            with open(zip_filename, "rb") as f:
                file_bytes = f.read()
            input_file = BufferedInputFile(file_bytes, filename=f"auto_backup_{timestamp}.zip")
            
            await bot.send_document(
                chat_id=BACKUP_GROUP_ID,
                document=input_file,
                caption=f"🔄 **Avtomatik 12 soatlik Volume Backup**\n📅 Sana: `{timestamp}`"
            )
            os.remove(zip_filename)
        except Exception as e:
            print(f"Avtomatik backup xatosi: {e}")


# --- FASTAPI SERVERI VA FAYL MUHARRIRI API'LARI ---
app = FastAPI()

class FileSaveRequest(BaseModel):
    path: str
    content: str

@app.get("/api/files")
def list_files(path: str = ""):
    current_path = os.path.normpath(os.path.join(BASE_DIR, path))
    if not current_path.startswith(BASE_DIR):
        raise HTTPException(status_code=400, detail="Noto'g'ri yo'l")
    
    if not os.path.exists(current_path):
        raise HTTPException(status_code=404, detail="Papka topilmadi")
        
    items = []
    for entry in os.scandir(current_path):
        items.append({
            "name": entry.name,
            "is_dir": entry.is_dir(),
            "path": os.path.relpath(entry.path, BASE_DIR)
        })
    return items

@app.get("/api/read")
def read_file(path: str):
    file_path = os.path.normpath(os.path.join(BASE_DIR, path))
    if not file_path.startswith(BASE_DIR) or not os.path.isfile(file_path):
        raise HTTPException(status_code=400, detail="Fayl topilmadi")
        
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    return {"content": content}

@app.post("/api/save")
def save_file(data: FileSaveRequest):
    file_path = os.path.normpath(os.path.join(BASE_DIR, data.path))
    if not file_path.startswith(BASE_DIR):
        raise HTTPException(status_code=400, detail="Noto'g'ri yo'l")
        
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(data.content)
    return {"status": "success"}

# Static fayllarni ulash (Mini App interfeysi uchun)
app.mount("/", StaticFiles(directory="static", html=True), name="static")


# --- ASOSIY ISHGA TUSHIRISH (BOT + FASTAPI SERVER) ---
async def main():
    print("Railway Bot Manager va File Editor ishga tushmoqda...")
    start_all_projects_auto()
    asyncio.create_task(scheduled_backup_task())
    
    # Bot polling
    asyncio.create_task(dp.start_polling(bot))
    
    # FastAPI uvicorn serveri
    import uvicorn
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    asyncio.run(main())
