import os
import shutil
import zipfile
import asyncio
import subprocess
from datetime import datetime
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile

# --- SOZLAMALAR ---
TOKEN = "8746921322:AAESSZswzjovLzDFD6N6CCA29D7qYxh4fPI"
ADMIN_ID = 6926668577  # Sizning Admin ID'ingiz
BACKUP_GROUP_ID = -1004339696809

BASE_DIR = "/data/bot"
BACKUP_DIR = "/data/backups"
os.makedirs(BASE_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)

bot = Bot(token=TOKEN)
dp = Dispatcher()
running_processes = {}

# --- ASOSIY MENYU TUGMALARI ---
def get_main_menu():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟢 Faol loyihalar", callback_data="list_projects")],
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

# --- 2. TEZKOR BACKUP OLISH ---
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

# --- 3. IMPORT QILISH YO'RIQNOMASI ---
@dp.callback_query(F.data == "help_import")
async def cb_help_import(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    await callback.message.edit_text(
        "📥 **Loyiha import qilish tartibi:**\n\n"
        "1. Yangi loyihangizni `.zip` formatida chatga yuboring.\n"
        "2. O'sha yuborgan ZIP faylingizga **reply** qilib quyidagi buyruqni yozing:\n"
        "`/import <loyiha_nomi>`\n\n"
        "Masalan: `/import my_shop_bot`\n\n"
        "Shundan so'ng bot uni avtomatik o'rnatadi va 24/7 yurgizib yuboradi.",
        reply_markup=get_main_menu()
    )

# --- ZIP ORQALI IMPORT QILISH BUYRUĞI (.import <name>) ---
@dp.message(Command("import"))
async def cmd_import(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
        
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("❌ Iltimos, loyiha nomini yozing. Masalan: `/import test_bot`")
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
        await status_msg.edit_text(f"❌ Xatolik: {e}", reply_markup=get_main_menu())

# --- 4. SERVERNI QAYTA YOQISH ---
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
        main_file = os.path.join(BASE_DIR, proj, "main.py")
        if os.path.exists(main_file) and proj not in running_processes:
            try:
                process = subprocess.Popen(
                    ["python", main_file],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    cwd=os.path.dirname(main_file)
                )
                running_processes[proj] = process
                asyncio.create_task(monitor_project(proj, process))
            except Exception as e:
                print(f"Xato ({proj}): {e}")

# --- 12 SOATLIK AVTO-BACKUP FON REJIMI ---
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
                caption=(
                    f"🔄 **Avtomatik 12 soatlik Volume Backup**\n\n"
                    f"📅 Sana va vaqt: `{timestamp}`\n"
                    f"⚙️ Holat: Barcha loyihalar va bazalar (`.db`) xavfsiz saqlandi."
                )
            )
            os.remove(zip_filename)
        except Exception as e:
            print(f"Avtomatik backup xatosi: {e}")

async def main():
    print("Hosting Manager Bot ishga tushmoqda...")
    start_all_projects_auto()
    asyncio.create_task(scheduled_backup_task())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
