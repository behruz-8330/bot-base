import os
import shutil
import zipfile
import asyncio
import subprocess
import uvicorn
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
ADMIN_ID = 6926668577  
BACKUP_GROUP_ID = -1004339696809
WEB_APP_URL = "https://bot-base-production-9d4a.up.railway.app"  # Mini App manzili

BASE_DIR = "/data/bot"
BACKUP_DIR = "/data/backups"
os.makedirs(BASE_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)

bot = Bot(token=TOKEN)
dp = Dispatcher()
running_processes = {}

class SessionStates(StatesGroup):
    waiting_for_lib = State()
    waiting_for_api_id = State()
    waiting_for_api_hash = State()
    waiting_for_phone = State()
    waiting_for_code = State()
    waiting_for_password = State()

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

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer(
        "🤖 **Railway Bot Manager paneliga xush kelibsiz!**\n\n"
        "Quyidagi tugmalar yordamida barcha loyihalarni boshqarishingiz mumkin:",
        reply_markup=get_main_menu()
    )

@dp.callback_query(F.data == "list_projects")
async def cb_list_projects(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    projects = [d for d in os.listdir(BASE_DIR) if os.path.isdir(os.path.join(BASE_DIR, d))]
    if not projects:
        await callback.message.edit_text("ℹ️ Hozirda loyihalar yo'q.", reply_markup=get_main_menu())
        return
    text = "🟢 **Loyihalar holati:**\n\n"
    for proj in projects:
        status = "🟢 Ishlayapti" if proj in running_processes else "🔴 To'xtagan"
        text += f"• **{proj}** — {status}\n"
    await callback.message.edit_text(text, reply_markup=get_main_menu())

@dp.callback_query(F.data == "remove_project_menu")
async def cb_remove_project_menu(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    projects = [d for d in os.listdir(BASE_DIR) if os.path.isdir(os.path.join(BASE_DIR, d))]
    if not projects:
        await callback.message.edit_text("ℹ️ O'chirish uchun loyihalar topilmadi.", reply_markup=get_main_menu())
        return
    buttons = [[InlineKeyboardButton(text=f"🗑 O'chirish: {proj}", callback_data=f"del_proj_{proj}")] for proj in projects]
    buttons.append([InlineKeyboardButton(text="⬅️ Ortga", callback_data="back_to_menu")])
    await callback.message.edit_text("🗑 **O'chirmoqchi bo'lgan loyihangizni tanlang:**", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

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
        except: pass
    if os.path.exists(proj_path):
        shutil.rmtree(proj_path)
        await callback.message.edit_text(f"✅ `{project_name}` o'chirildi!", reply_markup=get_main_menu())
    else:
        await callback.message.edit_text(f"⚠️ Topilmadi.", reply_markup=get_main_menu())

@dp.callback_query(F.data == "create_session_start")
async def cb_create_session(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID: return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Telethon", callback_data="lib_telethon"),
         InlineKeyboardButton(text="Pyrogram", callback_data="lib_pyrogram")],
        [InlineKeyboardButton(text="⬅️ Ortga", callback_data="back_to_menu")]
    ])
    await callback.message.edit_text("🔑 **Kutubxonani tanlang:**", reply_markup=keyboard)
    await state.set_state(SessionStates.waiting_for_lib)

@dp.callback_query(SessionStates.waiting_for_lib, F.data.startswith("lib_"))
async def cb_select_lib(callback: types.CallbackQuery, state: FSMContext):
    lib_name = callback.data.split("_")[1]
    await state.update_data(library=lib_name)
    await callback.message.edit_text(f"✅ Tanlandi: **{lib_name.capitalize()}**\n\n**API_ID** raqamini yuboring:")
    await state.set_state(SessionStates.waiting_for_api_id)

@dp.message(SessionStates.waiting_for_api_id)
async def process_api_id(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    try:
        await state.update_data(api_id=int(message.text.strip()))
        await message.answer("🔑 **API_HASH** matnini yuboring:")
        await state.set_state(SessionStates.waiting_for_api_hash)
    except ValueError:
        await message.answer("❌ Faqat raqam bo'lishi kerak:")

@dp.message(SessionStates.waiting_for_api_hash)
async def process_api_hash(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.update_data(api_hash=message.text.strip())
    await message.answer("📞 Telefon raqamingizni yuboring (Masalan: `+998901234567`):")
    await state.set_state(SessionStates.waiting_for_phone)

@dp.message(SessionStates.waiting_for_phone)
async def process_phone(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    phone = message.text.strip()
    await state.update_data(phone=phone)
    data = await state.get_data()
    status_msg = await message.answer(f"⏳ Kod yuborilmoqda...")
    try:
        if data["library"] == "telethon":
            from telethon import TelegramClient
            from telethon.sessions import StringSession
            client = TelegramClient(StringSession(), data["api_id"], data["api_hash"])
            await client.connect()
            sent = await client.send_code_request(phone)
            await state.update_data(client=client, phone_code_hash=sent.phone_code_hash)
        else:
            from pyrogram import Client
            client = Client("temp_session", api_id=data["api_id"], api_hash=data["api_hash"], in_memory=True)
            await client.connect()
            sent = await client.send_code(phone)
            await state.update_data(client=client, phone_code_hash=sent.phone_code_hash)
        await status_msg.edit_text("📥 Kod keldi. Uni bo'sh joy bilan yuboring (Masalan: `1 2 3 4 5`):")
        await state.set_state(SessionStates.waiting_for_code)
    except Exception as e:
        await status_msg.edit_text(f"❌ Xatolik: {e}")
        await state.clear()

@dp.message(SessionStates.waiting_for_code)
async def process_code(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    code = message.text.strip().replace(" ", "")
    data = await state.get_data()
    try:
        if data["library"] == "telethon":
            from telethon.errors import SessionPasswordNeededError
            try:
                await data["client"].sign_in(data["phone"], code, phone_code_hash=data["phone_code_hash"])
            except SessionPasswordNeededError:
                await message.answer("🔒 Ikki bosqichli parol kiritilsin:")
                await state.set_state(SessionStates.waiting_for_password)
                return
            s_session = data["client"].session.save()
            await data["client"].disconnect()
            await message.answer(f"🎉 **Telethon Session:**\n\n`{s_session}`", reply_markup=get_main_menu())
        else:
            from pyrogram.errors import SessionPasswordNeededError
            try:
                await data["client"].sign_in(data["phone"], data["phone_code_hash"], code)
            except SessionPasswordNeededError:
                await message.answer("🔒 Ikki bosqichli parol kiritilsin:")
                await state.set_state(SessionStates.waiting_for_password)
                return
            s_session = await data["client"].export_session_string()
            await data["client"].disconnect()
            await message.answer(f"🎉 **Pyrogram Session:**\n\n`{s_session}`", reply_markup=get_main_menu())
        await state.clear()
    except Exception as e:
        await message.answer(f"❌ Xatolik: {e}")
        await state.clear()

@dp.message(SessionStates.waiting_for_password)
async def process_password(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    data = await state.get_data()
    try:
        if data["library"] == "telethon":
            await data["client"].sign_in(password=message.text.strip())
            s_session = data["client"].session.save()
            await data["client"].disconnect()
        else:
            await data["client"].check_password(message.text.strip())
            s_session = await data["client"].export_session_string()
            await data["client"].disconnect()
        await message.answer(f"🎉 **Session:**\n\n`{s_session}`", reply_markup=get_main_menu())
        await state.clear()
    except Exception as e:
        await message.answer(f"❌ Parol xato: {e}")
        await state.clear()

@dp.callback_query(F.data == "back_to_menu")
async def cb_back(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID: return
    await state.clear()
    await callback.message.edit_text("🤖 **Panel:**", reply_markup=get_main_menu())

@dp.callback_query(F.data == "fast_backup")
async def cb_fast_backup(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID: return
    await callback.message.edit_text("⏳ Backup tayyorlanmoqda...")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    zip_filename = os.path.join(BACKUP_DIR, f"bot_backup_{timestamp}.zip")
    try:
        shutil.make_archive(zip_filename.replace('.zip', ''), 'zip', BASE_DIR)
        with open(zip_filename, "rb") as f:
            file_bytes = f.read()
        await bot.send_document(callback.from_user.id, BufferedInputFile(file_bytes, filename=f"backup_{timestamp}.zip"))
        os.remove(zip_filename)
        await callback.message.edit_text("✅ Yuborildi!", reply_markup=get_main_menu())
    except Exception as e:
        await callback.message.edit_text(f"❌ Xato: {e}", reply_markup=get_main_menu())

@dp.callback_query(F.data == "help_import")
async def cb_help_import(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID: return
    await callback.message.edit_text("📥 `.zip` faylga reply qilib `/import <loyiha_nomi>` yozing.", reply_markup=get_main_menu())

@dp.message(Command("import"))
async def cmd_import(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("❌ Loyiha nomini yozing: `/import name`")
        return
    project_name = parts[1].strip()
    reply = message.reply_to_message
    if not reply or not reply.document or not reply.document.file_name.endswith('.zip'):
        await message.answer("❌ .zip faylga reply qiling!")
        return
    status_msg = await message.answer(f"⏳ O'rnatilmoqda...")
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
            subprocess.run(["python", "-m", "pip", "install", "-r", req_file], cwd=proj_path, check=True)
        main_file = os.path.join(proj_path, "main.py")
        if os.path.exists(main_file):
            process = subprocess.Popen(["python", main_file], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=proj_path)
            running_processes[project_name] = process
            asyncio.create_task(monitor_project(project_name, process))
            await status_msg.edit_text(f"✅ `{project_name}` ishga tushdi!", reply_markup=get_main_menu())
        else:
            await status_msg.edit_text(f"⚠️ `main.py` topilmadi!", reply_markup=get_main_menu())
    except Exception as e:
        await status_msg.edit_text(f"❌ Xato: {e}", reply_markup=get_main_menu())

@dp.callback_query(F.data == "restart_all")
async def cb_restart(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID: return
    for proj, proc in list(running_processes.items()):
        proc.terminate()
    running_processes.clear()
    start_all_projects_auto()
    await callback.message.edit_text("🔄 Qayta yoqildi!", reply_markup=get_main_menu())

async def monitor_project(project_name, process):
    while True:
        retcode = process.poll()
        if retcode is not None:
            stderr_output = process.stderr.read() if process.stderr else "Noma'lum"
            try:
                await bot.send_message(ADMIN_ID, f"🚨 **Crash:** `{project_name}`\n`{stderr_output[-800:]}`")
            except: pass
            if project_name in running_processes:
                del running_processes[project_name]
            break
        await asyncio.sleep(5)

def start_all_projects_auto():
    if not os.path.exists(BASE_DIR): return
    for proj in os.listdir(BASE_DIR):
        proj_path = os.path.join(BASE_DIR, proj)
        if os.path.isdir(proj_path):
            main_file = os.path.join(proj_path, "main.py")
            req_file = os.path.join(proj_path, "requirements.txt")
            if os.path.exists(req_file):
                try: subprocess.run(["python", "-m", "pip", "install", "-r", req_file], cwd=proj_path, check=True)
                except: pass
            if os.path.exists(main_file) and proj not in running_processes:
                try:
                    process = subprocess.Popen(["python", main_file], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=proj_path)
                    running_processes[proj] = process
                    asyncio.create_task(monitor_project(proj, process))
                except: pass

async def scheduled_backup_task():
    while True:
        await asyncio.sleep(12 * 60 * 60)
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
            zip_filename = os.path.join(BACKUP_DIR, f"auto_backup_{timestamp}.zip")
            shutil.make_archive(zip_filename.replace('.zip', ''), 'zip', BASE_DIR)
            with open(zip_filename, "rb") as f:
                await bot.send_document(BACKUP_GROUP_ID, BufferedInputFile(f.read(), filename=f"auto_backup_{timestamp}.zip"))
            os.remove(zip_filename)
        except: pass


# --- FASTAPI API BACKEND ---
app = FastAPI()

class FileSaveRequest(BaseModel):
    path: str
    content: str

@app.get("/api/files")
def list_files(path: str = ""):
    current_path = os.path.normpath(os.path.join(BASE_DIR, path))
    if not current_path.startswith(BASE_DIR): raise HTTPException(status_code=400)
    items = []
    if os.path.exists(current_path):
        for entry in os.scandir(current_path):
            items.append({"name": entry.name, "is_dir": entry.is_dir(), "path": os.path.relpath(entry.path, BASE_DIR)})
    return items

@app.get("/api/read")
def read_file(path: str):
    file_path = os.path.normpath(os.path.join(BASE_DIR, path))
    if not file_path.startswith(BASE_DIR) or not os.path.isfile(file_path): raise HTTPException(status_code=400)
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    return {"content": content}

@app.post("/api/save")
def save_file(data: FileSaveRequest):
    file_path = os.path.normpath(os.path.join(BASE_DIR, data.path))
    if not file_path.startswith(BASE_DIR): raise HTTPException(status_code=400)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(data.content)
    return {"status": "success"}

app.mount("/", StaticFiles(directory="static", html=True), name="static")

background_tasks = set()

def _create_bg_task(coro):
    task = asyncio.create_task(coro)
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)
    return task

async def main():
    start_all_projects_auto()
    _create_bg_task(scheduled_backup_task())
    _create_bg_task(dp.start_polling(bot))
    port = int(os.environ.get("PORT", 8000))
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    asyncio.run(main())
