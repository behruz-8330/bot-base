import os
import shutil
import zipfile
import asyncio
import subprocess
from datetime import datetime
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, BufferedInputFile
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

# --- SOZLAMALAR ---
TOKEN = "8746921322:AAG9islan9MRD5dA9q7uyhFGHPNKWxGO4cw"
ADMIN_ID = 6926668577  # Sizning Admin ID'ingiz
BACKUP_GROUP_ID = -1004339696809

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

class ProjectEditStates(StatesGroup):
    waiting_for_file_content = State()
    waiting_for_edit_content = State()

# --- REPLY MENYU TUGMALARI ---
def get_main_menu():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🟢 Faol loyihalar"), KeyboardButton(text="🗑 Loyihani o'chirish")],
            [KeyboardButton(text="📁 Fayllarni boshqarish"), KeyboardButton(text="🔑 Sessiya yaratish")],
            [KeyboardButton(text="📦 Tezkor Backup olish"), KeyboardButton(text="📥 Loyiha import (.zip)")],
            [KeyboardButton(text="🔄 Serverni qayta yoqish")]
        ],
        resize_keyboard=True
    )
    return keyboard

# --- START BUYRUĞI ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.clear()
    await message.answer(
        "🤖 **Railway Bot Manager paneliga xush kelibsiz!**\n\n"
        "Quyidagi menyu tugmalari yordamida loyihalarni boshqarishingiz mumkin:",
        reply_markup=get_main_menu()
    )

@dp.message(F.text == "⬅️ Ortga menyuga")
async def back_to_main(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.clear()
    await message.answer("Asosiy menyu:", reply_markup=get_main_menu())

# --- 1. FAOL LOYIHALAR ---
@dp.message(F.text == "🟢 Faol loyihalar")
async def msg_list_projects(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    projects = [d for d in os.listdir(BASE_DIR) if os.path.isdir(os.path.join(BASE_DIR, d))]
    if not projects:
        await message.answer("ℹ️ Hozirda `/data/bot` papkasida loyihalar yo'q.", reply_markup=get_main_menu())
        return
        
    text = "🟢 **Loyihalar holati:**\n\n"
    for proj in projects:
        status = "🟢 Ishlayapti" if proj in running_processes else "🔴 To'xtagan"
        text += f"• **{proj}** — {status}\n"
        
    await message.answer(text, reply_markup=get_main_menu())

# --- LOYIHANI O'CHIRISH ---
@dp.message(F.text == "🗑 Loyihani o'chirish")
async def msg_remove_project_menu(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
        
    projects = [d for d in os.listdir(BASE_DIR) if os.path.isdir(os.path.join(BASE_DIR, d))]
    if not projects:
        await message.answer("ℹ️ O'chirish uchun loyihalar topilmadi.", reply_markup=get_main_menu())
        return
        
    text = "🗑 **O'chirmoqchi bo'lgan loyihangiz nomini quyidagi formatda yuboring:**\n`/del_proj <loyiha_nomi>`\n\nMavjud loyihalar:\n"
    for proj in projects:
        text += f"• `{proj}`\n"
        
    await message.answer(text, reply_markup=get_main_menu())

@dp.message(Command("del_proj"))
async def cmd_delete_project_action(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("❌ Iltimos, loyiha nomini yozing. Masalan: `/del_proj bot_name`")
        return
        
    project_name = parts[1].strip()
    proj_path = os.path.join(BASE_DIR, project_name)
    
    if project_name in running_processes:
        try:
            running_processes[project_name].terminate()
            del running_processes[project_name]
        except Exception:
            pass
            
    if os.path.exists(proj_path):
        shutil.rmtree(proj_path)
        await message.answer(f"✅ `{project_name}` loyihasi muvaffaqiyatli o'chirib tashlandi!", reply_markup=get_main_menu())
    else:
        await message.answer(f"⚠️ `{project_name}` loyihasi topilmadi.", reply_markup=get_main_menu())

# --- 2. FAYL VA PAPKALARNI BOSHQARISH (EDIT, ADD, REMOVE) ---
@dp.message(F.text == "📁 Fayllarni boshqarish")
async def msg_manage_projects(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    projects = [d for d in os.listdir(BASE_DIR) if os.path.isdir(os.path.join(BASE_DIR, d))]
    if not projects:
        await message.answer("ℹ️ Hozircha loyihalar yo'q. Avval loyiha qo'shing yoki import qiling.", reply_markup=get_main_menu())
        return
    
    text = "📁 **Loyihalar ro'yxati (Fayllarni ko'rish uchun buyruq yuboring):**\n\n"
    for proj in projects:
        text += f"• 📂 `{proj}` -> `/files {proj}`\n"
    await message.answer(text, reply_markup=get_main_menu())

@dp.message(Command("files"))
async def cmd_view_project_files(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("❌ Iltimos loyiha nomini ko'rsating: `/files <loyiha_nomi>`")
        return
    
    proj_name = parts[1].strip()
    proj_path = os.path.join(BASE_DIR, proj_name)
    if not os.path.exists(proj_path):
        await message.answer("❌ Bunday loyiha topilmadi.")
        return
    
    files_list = []
    for root, dirs, files in os.walk(proj_path):
        for file in files:
            rel_path = os.path.relpath(os.path.join(root, file), proj_path)
            files_list.append(rel_path)
            
    text = f"📂 **{proj_name}** loyihasidagi fayllar:\n\n"
    for f in files_list:
        text += f"📄 `{f}`\n   ↳ Tahrirlash: `/edit {proj_name} {f}`\n   ↳ O'chirish: `/delfile {proj_name} {f}`\n\n"
    
    text += f"\n➕ **Yangi fayl qo'shish:** `/addfile {proj_name} <fayl_yo'li>`\n"
    text += f"📁 **Yangi papka qo'shish:** `/addfolder {proj_name} <papka_nomi>`"
    await message.answer(text)

# Faylni tahrirlash (Edit)
@dp.message(Command("edit"))
async def cmd_edit_file(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("❌ Xato format. Ishlatish: `/edit <loyiha> <fayl_nomi>`")
        return
    
    proj_name, file_path = parts[1], parts[2]
    full_path = os.path.join(BASE_DIR, proj_name, file_path)
    
    if not os.path.exists(full_path):
        await message.answer("❌ Bunday fayl topilmadi.")
        return
        
    with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
        
    await state.update_data(edit_file_path=full_path, proj_name=proj_name)
    
    safe_content = content[:3000].replace("```", "` ` `")
    await message.answer(
        f"✏️ **{file_path}** faylining Hozirgi kodi:\n\n"
        f"<code>{safe_content}</code>\n\n"
        f"Iltimos, ushbu faylga yozmoqchi bo'lgan **YANGI KODNI MATN SHAKlida YOKI FAYL (document) ko'rinishida yuboring**:",
        reply_markup=get_main_menu(),
        parse_mode="HTML"
    )
    await state.set_state(ProjectEditStates.waiting_for_edit_content)

@dp.message(ProjectEditStates.waiting_for_edit_content)
async def save_edited_file(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    data = await state.get_data()
    file_path = data["edit_file_path"]
    proj_name = data["proj_name"]
    
    new_content = ""
    if message.document:
        file_info = await bot.get_file(message.document.file_id)
        downloaded_file = await bot.download_file(file_info.file_path)
        new_content = downloaded_file.read().decode("utf-8")
    elif message.text:
        new_content = message.text
    else:
        await message.answer("❌ Iltimos, kodni matn yoki fayl ko'rinishida yuboring!")
        return
    
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        await message.answer(f"✅ Fayl muvaffaqiyatli saqlandi va yangilandi!", reply_markup=get_main_menu())
        
        if proj_name in running_processes:
            running_processes[proj_name].terminate()
            del running_processes[proj_name]
            
        proj_path = os.path.join(BASE_DIR, proj_name)
        main_file = os.path.join(proj_path, "main.py")
        if os.path.exists(main_file):
            process = subprocess.Popen(["python", main_file], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=proj_path)
            running_processes[proj_name] = process
            asyncio.create_task(monitor_project(proj_name, process))
            await message.answer(f"🔄 `{proj_name}` qayta ishga tushirildi.")
    except Exception as e:
        await message.answer(f"❌ Xatolik: {e}", reply_markup=get_main_menu())
    await state.clear()

# Fayl qo'shish (Add file)
@dp.message(Command("addfile"))
async def cmd_add_file_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("❌ Format: `/addfile <loyiha> <fayl_nomi>`")
        return
    
    proj_name, file_rel_path = parts[1], parts[2]
    full_path = os.path.join(BASE_DIR, proj_name, file_rel_path)
    
    await state.update_data(new_file_path=full_path)
    await message.answer(f"📝 `{file_rel_path}` uchun **kodni matn yoki fayl (document) shaklida** yuboring:", reply_markup=get_main_menu())
    await state.set_state(ProjectEditStates.waiting_for_file_content)

@dp.message(ProjectEditStates.waiting_for_file_content)
async def save_new_file_content(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    data = await state.get_data()
    file_path = data["new_file_path"]
    
    new_content = ""
    if message.document:
        file_info = await bot.get_file(message.document.file_id)
        downloaded_file = await bot.download_file(file_info.file_path)
        new_content = downloaded_file.read().decode("utf-8")
    elif message.text:
        new_content = message.text
    else:
        await message.answer("❌ Iltimos, matn yoki fayl yuboring!")
        return

    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        await message.answer(f"✅ Yangi fayl muvaffaqiyatli yaratildi!", reply_markup=get_main_menu())
    except Exception as e:
        await message.answer(f"❌ Xatolik: {e}", reply_markup=get_main_menu())
    await state.clear()

# Fayl yoki Papkani o'chirish (Remove file)
@dp.message(Command("delfile"))
async def cmd_delete_file(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("❌ Format: `/delfile <loyiha> <fayl_yoli>`")
        return
    
    proj_name, file_path = parts[1], parts[2]
    full_path = os.path.join(BASE_DIR, proj_name, file_path)
    
    if os.path.exists(full_path):
        if os.path.isdir(full_path):
            shutil.rmtree(full_path)
        else:
            os.remove(full_path)
        await message.answer(f"✅ `{file_path}` o'chirildi!", reply_markup=get_main_menu())
    else:
        await message.answer("❌ Fayl topilmadi.", reply_markup=get_main_menu())

# Papka qo'shish
@dp.message(Command("addfolder"))
async def cmd_add_folder(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("❌ Format: `/addfolder <loyiha> <papka_nomi>`")
        return
    proj_name, folder_name = parts[1], parts[2]
    folder_path = os.path.join(BASE_DIR, proj_name, folder_name)
    os.makedirs(folder_path, exist_ok=True)
    await message.answer(f"✅ `{folder_name}` papkasi yaratildi!", reply_markup=get_main_menu())

# --- 3. SESSIYA YARATISH JARAYONI ---
@dp.message(F.text == "🔑 Sessiya yaratish")
async def msg_create_session(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Telethon"), KeyboardButton(text="Pyrogram")],
            [KeyboardButton(text="⬅️ Ortga menyuga")]
        ],
        resize_keyboard=True
    )
    await message.answer("🔑 **Sessiya yaratish uchun kutubxonani tanlang:**", reply_markup=keyboard)
    await state.set_state(SessionStates.waiting_for_lib)

@dp.message(SessionStates.waiting_for_lib, F.text.in_(["Telethon", "Pyrogram"]))
async def process_lib_choice(message: types.Message, state: FSMContext):
    lib_name = message.text.lower()
    await state.update_data(library=lib_name)
    await message.answer(f"✅ Tanlandi: **{message.text}**\n\nIltimos, **API_ID** raqamingizni yuboring:", reply_markup=get_main_menu())
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
        await message.answer("❌ API_ID faqat raqamlardan iborat bo'lishi kerak:")

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
            await status_msg.edit_text("📥 Kod keldi. Kodni raqamlar orasiga bo'sh joy qo'yib yuboring (Masalan: `1 2 3 4 5`):")
            await state.set_state(SessionStates.waiting_for_code)
            
        elif lib == "pyrogram":
            from pyrogram import Client
            client = Client("temp_session", api_id=api_id, api_hash=api_hash, in_memory=True)
            await client.connect()
            sent = await client.send_code(phone)
            await state.update_data(client=client, phone_code_hash=sent.phone_code_hash)
            await status_msg.edit_text("📥 Kod keldi. Kodni raqamlar orasiga bo'sh joy qo'yib yuboring (Masalan: `1 2 3 4 5`):")
            await state.set_state(SessionStates.waiting_for_code)
    except Exception as e:
        await status_msg.edit_text(f"❌ Xatolik yuz berdi: {e}")
        await state.clear()

@dp.message(SessionStates.waiting_for_code)
async def process_code(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    code = message.text.strip().replace(" ", "")
    data = await state.get_data()
    lib, client, phone, phone_code_hash = data["library"], data["client"], data["phone"], data["phone_code_hash"]
    
    try:
        if lib == "telethon":
            from telethon.errors import SessionPasswordNeededError
            try:
                await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
            except SessionPasswordNeededError:
                await message.answer("🔒 2 bosqichli parol mavjud. Parolni kiriting:")
                await state.set_state(SessionStates.waiting_for_password)
                return
            string_session = client.session.save()
            await client.disconnect()
            await message.answer(f"🎉 **Telethon Session yaratildi!**\n\n`{string_session}`", reply_markup=get_main_menu())
            await state.clear()
            
        elif lib == "pyrogram":
            from pyrogram.errors import SessionPasswordNeededError
            try:
                await client.sign_in(phone, phone_code_hash, code)
            except SessionPasswordNeededError:
                await message.answer("🔒 2 bosqichli parol mavjud. Parolni kiriting:")
                await state.set_state(SessionStates.waiting_for_password)
                return
            string_session = await client.export_session_string()
            await client.disconnect()
            await message.answer(f"🎉 **Pyrogram Session yaratildi!**\n\n`{string_session}`", reply_markup=get_main_menu())
            await state.clear()
    except Exception as e:
        await message.answer(f"❌ Xatolik: {e}", reply_markup=get_main_menu())
        await state.clear()

@dp.message(SessionStates.waiting_for_password)
async def process_password(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    password = message.text.strip()
    data = await state.get_data()
    lib, client = data["library"], data["client"]
    try:
        if lib == "telethon":
            await client.sign_in(password=password)
            string_session = client.session.save()
            await client.disconnect()
            await message.answer(f"🎉 **Telethon Session yaratildi!**\n\n`{string_session}`", reply_markup=get_main_menu())
        elif lib == "pyrogram":
            await client.check_password(password)
            string_session = await client.export_session_string()
            await client.disconnect()
            await message.answer(f"🎉 **Pyrogram Session yaratildi!**\n\n`{string_session}`", reply_markup=get_main_menu())
        await state.clear()
    except Exception as e:
        await message.answer(f"❌ Xatolik: {e}", reply_markup=get_main_menu())
        await state.clear()

# --- 4. TEZKOR BACKUP ---
@dp.message(F.text == "📦 Tezkor Backup olish")
async def msg_fast_backup(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    status_msg = await message.answer("⏳ Tezkor backup tayyorlanmoqda...")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    zip_filename = os.path.join(BACKUP_DIR, f"bot_backup_{timestamp}.zip")
    
    try:
        shutil.make_archive(zip_filename.replace('.zip', ''), 'zip', BASE_DIR)
        with open(zip_filename, "rb") as f:
            file_bytes = f.read()
        input_file = BufferedInputFile(file_bytes, filename=f"backup_{timestamp}.zip")
        await message.answer_document(document=input_file, caption=f"📦 **Volume Backup**\n🕒 Vaqt: `{timestamp}`", reply_markup=get_main_menu())
        os.remove(zip_filename)
        await status_msg.delete()
    except Exception as e:
        await status_msg.edit_text(f"❌ Xatolik: {e}", reply_markup=get_main_menu())

# --- 5. IMPORT QILISH (.ZIP) ---
@dp.message(F.text == "📥 Loyiha import (.zip)")
async def msg_help_import(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer(
        "📥 **Loyiha import qilish tartibi:**\n\n"
        "1. Yangi loyihangizni `.zip` formatida chatga yuboring.\n"
        "2. O'sha yuborgan ZIP faylingizga **reply** qilib yozing:\n"
        "`/import <loyiha_nomi>`",
        reply_markup=get_main_menu()
    )

@dp.message(Command("import"))
async def cmd_import(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("❌ Loyiha nomini yozing: `/import scheduler-bot`")
        return
        
    project_name = parts[1].strip()
    reply = message.reply_to_message
    
    if not reply or not reply.document or not reply.document.file_name.endswith('.zip'):
        await message.answer("❌ ZIP formatidagi faylga reply qiling!")
        return

    status_msg = await message.answer(f"⏳ `{project_name}` o'rnatilmoqda...")
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
            await status_msg.edit_text("📦 Kutubxonalar o'rnatilmoqda...")
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
        await status_msg.edit_text(f"❌ Xatolik: {e}", reply_markup=get_main_menu())

# --- 6. SERVERNI QAYTA YOQISH ---
@dp.message(F.text == "🔄 Serverni qayta yoqish")
async def msg_restart(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    for proj, proc in list(running_processes.items()):
        proc.terminate()
    running_processes.clear()
    start_all_projects_auto()
    await message.answer("🔄 Barcha loyihalar qayta ishga tushirildi!", reply_markup=get_main_menu())

# --- CRASH MONITORING ---
async def monitor_project(project_name, process):
    while True:
        retcode = process.poll()
        if retcode is not None:
            stderr_output = process.stderr.read() if process.stderr else "Noma'lum"
            error_msg = f"🚨 **Crash!**\n📁 Loyiha: `{project_name}`\n`{stderr_output[-800:]}`"
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
                print(f"Xato ({proj}): {e}")
        if os.path.exists(main_file) and proj not in running_processes:
            try:
                process = subprocess.Popen(["python", main_file], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=proj_path)
                running_processes[proj] = process
                asyncio.create_task(monitor_project(proj, process))
            except Exception as e:
                print(f"Xato ({proj}): {e}")

async def scheduled_backup_task():
    while True:
        await asyncio.sleep(12 * 60 * 60)
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
            zip_filename = os.path.join(BACKUP_DIR, f"auto_backup_{timestamp}.zip")
            shutil.make_archive(zip_filename.replace('.zip', ''), 'zip', BASE_DIR)
            with open(zip_filename, "rb") as f:
                file_bytes = f.read()
            input_file =BufferedInputFile(file_bytes, filename=f"auto_backup_{timestamp}.zip")
            await bot.send_document(chat_id=BACKUP_GROUP_ID, document=input_file, caption=f"🔄 **12 soatlik Avto-Backup**\n📅 Sana: `{timestamp}`")
            os.remove(zip_filename)
        except Exception as e:
            print(f"Avto-backup xatosi: {e}")

async def main():
    print("Manager Bot ishga tushmoqda...")
    start_all_projects_auto()
    asyncio.create_task(scheduled_backup_task())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

