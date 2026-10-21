import asyncio
import sqlite3
import pandas as pd
import os
from datetime import datetime
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher.filters import Command, Text

TOKEN = "8657817961:AAFzR-vRkj_c6bz78zdZeOxvHJP7txlJdzw"

bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
logging.basicConfig(level=logging.INFO)

# ---- 1. BAZA YARATISH ----
def db_yaratish():
    conn = sqlite3.connect('maktab_baza.db')
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS xodimlar (id INTEGER PRIMARY KEY AUTOINCREMENT, telefon TEXT UNIQUE, ism TEXT, rol TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS foydalanuvchilar (tg_id INTEGER PRIMARY KEY, telefon TEXT, rol TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS guruhlar (id INTEGER PRIMARY KEY AUTOINCREMENT, nomi TEXT, oqituvchi_tel TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS oquvchilar (id INTEGER PRIMARY KEY AUTOINCREMENT, ism TEXT, telefon TEXT UNIQUE, ota_ona_tel TEXT, guruh_id INTEGER)')
    cursor.execute('CREATE TABLE IF NOT EXISTS tolovlar (id INTEGER PRIMARY KEY AUTOINCREMENT, oquvchi_id INTEGER, summa REAL, usul TEXT, sana DATETIME DEFAULT CURRENT_TIMESTAMP, kassir_tel TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS keldi_ketdi (id INTEGER PRIMARY KEY AUTOINCREMENT, oquvchi_tel TEXT, harakat TEXT, vaqt DATETIME DEFAULT CURRENT_TIMESTAMP, lat REAL, lon REAL)')
    cursor.execute('CREATE TABLE IF NOT EXISTS davomatlar (id INTEGER PRIMARY KEY AUTOINCREMENT, guruh_id INTEGER, oquvchi_id INTEGER, holat TEXT, sana TEXT, oqituvchi_tel TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS xarajatlar (id INTEGER PRIMARY KEY AUTOINCREMENT, summa REAL, izoh TEXT, sana DATETIME DEFAULT CURRENT_TIMESTAMP, kassir_tel TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS blok_test (id INTEGER PRIMARY KEY AUTOINCREMENT, oquvchi_tel TEXT, fan TEXT, ball REAL, sana DATETIME DEFAULT CURRENT_TIMESTAMP)')
    
    cursor.execute("SELECT * FROM xodimlar WHERE telefon = '+998332050428'")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO xodimlar (telefon, ism, rol) VALUES ('+998332050428', 'Javohir (Direktor)', 'direktor')")
        cursor.execute("INSERT INTO xodimlar (telefon, ism, rol) VALUES ('+998901234567', 'Ali O\\'qituvchi', 'oqituvchi')")
        cursor.execute("INSERT INTO xodimlar (telefon, ism, rol) VALUES ('+998930490323', 'Baxtiyor', 'oqituvchi')")
        cursor.execute("INSERT INTO xodimlar (telefon, ism, rol) VALUES ('+998931345958', 'Javohir', 'oqituvchi')")
    
    conn.commit()
    conn.close()

db_yaratish()

# ---- 2. YORDAMCHI FUNKSIYALAR ----
def sessiya_saqlash(tg_id, telefon, rol):
    conn = sqlite3.connect('maktab_baza.db')
    cursor = conn.cursor()
    cursor.execute("REPLACE INTO foydalanuvchilar (tg_id, telefon, rol) VALUES (?, ?, ?)", (tg_id, telefon, rol))
    conn.commit()
    conn.close()

def sessiya_olish(tg_id):
    conn = sqlite3.connect('maktab_baza.db')
    cursor = conn.cursor()
    cursor.execute("SELECT rol, telefon FROM foydalanuvchilar WHERE tg_id = ?", (tg_id,))
    natija = cursor.fetchone()
    conn.close()
    return natija 

# ---- 3. STATELAR ----
class XodimQoshish(StatesGroup):
    ism = State()
    telefon = State()
    lavozim = State()

class XodimOchirish(StatesGroup):
    telefon = State()

class TolovQabul(StatesGroup):
    oquvchi_qidir = State()
    summa = State()
    usul = State()

class XarajatKiritish(StatesGroup):
    summa = State()
    izoh = State()

class ExcelYuklash(StatesGroup):
    oquvchi_fayl = State()
    test_fayl = State()

# ---- 4. MENYULAR ----
def get_keyboard(role):
    if role == "direktor":
        return ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="👥 Xodimlar"), KeyboardButton(text="🎓 O'quvchilar va Test")],
            [KeyboardButton(text="💰 Kassa va Kirim-Chiqim"), KeyboardButton(text="📝 Umumiy Davomat")],
            [KeyboardButton(text="📍 O'quvchilar Keldi-Ketdi")]
        ], resize_keyboard=True)
    elif role == "oqituvchi":
        return ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="📝 Davomat qilish"), KeyboardButton(text="⭐ Maosh va Reyting")]
        ], resize_keyboard=True)
    elif role == "kassir":
        return ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="💵 To'lov qabul qilish"), KeyboardButton(text="📤 Xarajat (Chiqim)")],
            [KeyboardButton(text="📊 Kassa hisoboti"), KeyboardButton(text="🔒 Kunni yopish")]
        ], resize_keyboard=True)
    elif role == "oquvchi":
        return ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="📍 Keldim / Ketdim (Lokatsiya)", request_location=True)],
            [KeyboardButton(text="📅 Dars jadvali"), KeyboardButton(text="📝 Davomatim / Natijam")],
            [KeyboardButton(text="💳 To'lov qilish")]
        ], resize_keyboard=True)
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📱 Tizimga kirish", request_contact=True)]], resize_keyboard=True)

# ---- 5. AVTORIZATSIYA ----
@dp.message_handler(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.finish()
    user = sessiya_olish(message.from_user.id)
    if user:
        await message.answer(f"Siz tizimga <b>{user[0].upper()}</b> sifatida kirgansiz.", reply_markup=get_keyboard(user[0]), parse_mode="HTML")
    else:
        await message.answer("Tizimga kirish uchun raqamingizni yuboring:", reply_markup=get_keyboard("mehmon"))

@dp.message_handler(content_types=['contact'])
async def raqamni_tekshirish(message: types.Message):
    user_id = message.from_user.id
    raqam = message.contact.phone_number
    if not raqam.startswith("+"): raqam = "+" + raqam
    
    conn = sqlite3.connect('maktab_baza.db')
    cursor = conn.cursor()
    cursor.execute("SELECT ism, rol FROM xodimlar WHERE telefon = ?", (raqam,))
    xodim = cursor.fetchone()
    
    if xodim:
        ism, rol = xodim[0], xodim[1]
        sessiya_saqlash(user_id, raqam, rol)
        await message.answer(f"✅ Muvaffaqiyatli! Salom, {ism}.", reply_markup=get_keyboard(rol))
    else:
        cursor.execute("SELECT ism FROM oquvchilar WHERE telefon = ?", (raqam,))
        oquvchi = cursor.fetchone()
        if oquvchi:
            ism = oquvchi[0]
            sessiya_saqlash(user_id, raqam, "oquvchi")
            await message.answer(f"✅ Salom, o'quvchi <b>{ism}</b>!", reply_markup=get_keyboard("oquvchi"), parse_mode="HTML")
        else:
            await message.answer("❌ Raqamingiz tizimda topilmadi.")
    conn.close()

# ---- 6. O'QUVCHI MENYULARI ----
@dp.message_handler(content_types=['location'])
async def oquvchi_lokatsiyasi(message: types.Message):
    user = sessiya_olish(message.from_user.id)
    if not user or user[0] != "oquvchi": return
    conn = sqlite3.connect('maktab_baza.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO keldi_ketdi (oquvchi_tel, harakat, vaqt, lat, lon) VALUES (?, ?, ?, ?, ?)", 
                   (user[1], "Keldi/Ketdi", datetime.now().strftime("%Y-%m-%d %H:%M:%S"), message.location.latitude, message.location.longitude))
    conn.commit()
    conn.close()
    await message.answer("✅ Joylashuvingiz va vaqtingiz qayd etildi!")

@dp.message_handler(Text(equals="📅 Dars jadvali"))
async def oquvchi_jadval(message: types.Message):
    user = sessiya_olish(message.from_user.id)
    if not user or user[0] != "oquvchi": return
    conn = sqlite3.connect('maktab_baza.db')
    cursor = conn.cursor()
    cursor.execute("""
        SELECT guruhlar.nomi, xodimlar.ism FROM oquvchilar 
        JOIN guruhlar ON oquvchilar.guruh_id = guruhlar.id 
        JOIN xodimlar ON guruhlar.oqituvchi_tel = xodimlar.telefon 
        WHERE oquvchilar.telefon = ?
    """, (user[1],))
    guruh = cursor.fetchone()
    conn.close()
    if guruh:
        await message.answer(f"📅 <b>Sizning guruh ma'lumotingiz:</b>\n\n📚 Guruh: <b>{guruh[0]}</b>\n👨‍🏫 O'qituvchi: <b>{guruh[1]}</b>", parse_mode="HTML")
    else:
        await message.answer("Siz hali guruhga biriktirilmagansiz.")

@dp.message_handler(Text(equals="📝 Davomatim / Natijam"))
async def oquvchi_natija(message: types.Message):
    user = sessiya_olish(message.from_user.id)
    if not user or user[0] != "oquvchi": return
    conn = sqlite3.connect('maktab_baza.db')
    cursor = conn.cursor()
    cursor.execute("SELECT holat, sana FROM davomatlar JOIN oquvchilar ON davomatlar.oquvchi_id = oquvchilar.id WHERE oquvchilar.telefon = ? ORDER BY davomatlar.id DESC LIMIT 5", (user[1],))
    dav = cursor.fetchall()
    cursor.execute("SELECT fan, ball, sana FROM blok_test WHERE oquvchi_tel = ? ORDER BY id DESC LIMIT 5", (user[1],))
    testlar = cursor.fetchall()
    conn.close()
    matn = "<b>📝 Oxirgi davomatlar:</b>\n"
    for d in dav: matn += f"• {d[1]} — {'✅' if d[0]=='Keldi' else '❌'}\n"
    matn += "\n<b>📈 Blok Test Natijalari:</b>\n"
    for t in testlar: matn += f"• {t[0]}: <b>{t[1]} ball</b> ({t[2][:10]})\n"
    await message.answer(matn, parse_mode="HTML")

@dp.message_handler(Text(equals="💳 To'lov qilish"))
async def tolov_qilish_menu(message: types.Message):
    inline_pay = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Payme orqali to'lash", url="https://payme.uz")],
        [InlineKeyboardButton(text="Click orqali to'lash", url="https://click.uz")]
    ])
    await message.answer("💳 O'qish to'lovini onlayn amalga oshirish:", reply_markup=inline_pay)

# ---- 7. XODIMLAR BO'LIMI (Direktor) ----
@dp.message_handler(Text(equals="👥 Xodimlar"))
async def xodimlar_menyusi(message: types.Message):
    user = sessiya_olish(message.from_user.id)
    if not user or user[0] != "direktor": return
    inline_menu = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Yangi xodim qo'shish", callback_data="xodim_qosh")],
        [InlineKeyboardButton(text="🗑 Xodimni o'chirish", callback_data="xodim_ochir")],
        [InlineKeyboardButton(text="📋 Xodimlarni ko'rish", callback_data="xodim_korish")]
    ])
    await message.answer("Xodimlar boshqaruvi:", reply_markup=inline_menu)

@dp.callback_query_handler(lambda c: c.data == "xodim_korish")
async def royxat_korsat(callback: types.CallbackQuery):
    conn = sqlite3.connect('maktab_baza.db')
    cursor = conn.cursor()
    cursor.execute("SELECT ism, rol, telefon FROM xodimlar")
    xodimlar = cursor.fetchall()
    conn.close()
    matn = "<b>Tizimdagi xodimlar:</b>\n\n"
    for x in xodimlar: matn += f"👤 {x[0]} ({x[1].upper()}) — {x[2]}\n"
    await callback.message.edit_text(matn, parse_mode="HTML")

@dp.callback_query_handler(lambda c: c.data == "xodim_qosh")
async def xodim_ism(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Yangi xodimning <b>Ismini</b> yozing:", parse_mode="HTML")
    await XodimQoshish.ism.set()

@dp.message_handler(state=XodimQoshish.ism)
async def xodim_tel(message: types.Message, state: FSMContext):
    await state.update_data(ism=message.text)
    await message.answer("Raqamini yozing (+998...):")
    await XodimQoshish.telefon.set()

@dp.message_handler(state=XodimQoshish.telefon)
async def xodim_rol(message: types.Message, state: FSMContext):
    await state.update_data(telefon=message.text)
    rollar = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="oqituvchi"), KeyboardButton(text="kassir")], [KeyboardButton(text="menejer"), KeyboardButton(text="admin")]], resize_keyboard=True, one_time_keyboard=True)
    await message.answer("Lavozimni tanlang:", reply_markup=rollar)
    await XodimQoshish.lavozim.set()

@dp.message_handler(state=XodimQoshish.lavozim)
async def xodim_saqlash(message: types.Message, state: FSMContext):
    data = await state.get_data()
    conn = sqlite3.connect('maktab_baza.db')
    try:
        conn.cursor().execute("INSERT INTO xodimlar (telefon, ism, rol) VALUES (?, ?, ?)", (data.get('telefon'), data.get('ism'), message.text))
        conn.commit()
        await message.answer(f"✅ {data.get('ism')} ishga qabul qilindi!", reply_markup=get_keyboard("direktor"))
    except:
        await message.answer("❌ Bu raqam oldin qo'shilgan!", reply_markup=get_keyboard("direktor"))
    conn.close()
    await state.finish()

@dp.callback_query_handler(lambda c: c.data == "xodim_ochir")
async def xodim_ochir_boshlash(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Bo'shatilayotgan xodim raqamini yozing (+998...):")
    await XodimOchirish.telefon.set()

@dp.message_handler(state=XodimOchirish.telefon)
async def xodim_ochirildi(message: types.Message, state: FSMContext):
    tel = message.text
    conn = sqlite3.connect('maktab_baza.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM xodimlar WHERE telefon = ?", (tel,))
    conn.commit()
    conn.close()
    await message.answer("✅ Xodim tizimdan o'chirildi!", reply_markup=get_keyboard("direktor"))
    await state.finish()

# ---- 8. MOLIYA VA KASSA ----
@dp.message_handler(Text(equals="💵 To'lov qabul qilish"))
async def tolov_boshlash(message: types.Message, state: FSMContext):
    user = sessiya_olish(message.from_user.id)
    if not user or user[0] not in ["kassir", "direktor"]: return
    await message.answer("🔍 Qaysi o'quvchidan to'lov qabul qilyapsiz? Ismini yozing:")
    await TolovQabul.oquvchi_qidir.set()

@dp.message_handler(state=TolovQabul.oquvchi_qidir)
async def tolov_qidirish(message: types.Message, state: FSMContext):
    conn = sqlite3.connect('maktab_baza.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, ism FROM oquvchilar WHERE ism LIKE ?", ('%'+message.text+'%',))
    natija = cursor.fetchall()
    conn.close()
    if not natija:
        await message.answer("❌ O'quvchi topilmadi. Qaytadan yozing:")
        return
    tugmalar = [[InlineKeyboardButton(text=oq[1], callback_data=f"toloq_{oq[0]}")] for oq in natija]
    await message.answer("O'quvchini tanlang:", reply_markup=InlineKeyboardMarkup(inline_keyboard=tugmalar))

@dp.callback_query_handler(lambda c: c.data.startswith("toloq_"))
async def tolov_summa(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(oq_id=int(callback.data.split("_")[1]))
    await callback.message.edit_text("💰 Summani kiriting (Masalan: 200000):")
    await TolovQabul.summa.set()

@dp.message_handler(state=TolovQabul.summa)
async def tolov_usul(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return
    await state.update_data(summa=message.text)
    markup = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Naqd"), KeyboardButton(text="Terminal")], [KeyboardButton(text="Click")]], resize_keyboard=True, one_time_keyboard=True)
    await message.answer("💳 Usulni tanlang:", reply_markup=markup)
    await TolovQabul.usul.set()

@dp.message_handler(state=TolovQabul.usul)
async def tolov_saqlash(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user = sessiya_olish(message.from_user.id)
    conn = sqlite3.connect('maktab_baza.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO tolovlar (oquvchi_id, summa, usul, kassir_tel) VALUES (?, ?, ?, ?)", (data['oq_id'], data['summa'], message.text, user[1]))
    cursor.execute("SELECT ism FROM oquvchilar WHERE id = ?", (data['oq_id'],))
    ism = cursor.fetchone()[0]
    conn.commit()
    conn.close()
    await message.answer(f"🧾 <b>TO'LOV QABUL QILINDI!</b>\n👤 O'quvchi: {ism}\n💰 Summa: {data['summa']} so'm\n💳 Usul: {message.text}", parse_mode="HTML", reply_markup=get_keyboard(user[0]))
    await state.finish()

@dp.message_handler(Text(equals="📤 Xarajat (Chiqim)"))
async def xarajat_boshlash(message: types.Message, state: FSMContext):
    user = sessiya_olish(message.from_user.id)
    if not user or user[0] not in ["kassir", "direktor"]: return
    await message.answer("Kassadan chiqayotgan <b>Summani</b> kiriting (Faqat raqam):", parse_mode="HTML")
    await XarajatKiritish.summa.set()

@dp.message_handler(state=XarajatKiritish.summa)
async def xarajat_izoh(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return
    await state.update_data(summa=message.text)
    await message.answer("Izoh yozing (Nima uchun sarflandi?):")
    await XarajatKiritish.izoh.set()

@dp.message_handler(state=XarajatKiritish.izoh)
async def xarajat_saqlash(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user = sessiya_olish(message.from_user.id)
    conn = sqlite3.connect('maktab_baza.db')
    conn.cursor().execute("INSERT INTO xarajatlar (summa, izoh, kassir_tel) VALUES (?, ?, ?)", (data['summa'], message.text, user[1]))
    conn.commit()
    conn.close()
    await message.answer("✅ Xarajat kassadan chiqarildi!", reply_markup=get_keyboard(user[0]))
    await state.finish()

@dp.message_handler(Text(equals=["📊 Kassa hisoboti", "💰 Kassa va Kirim-Chiqim"]))
async def kassa_hisoboti(message: types.Message):
    user = sessiya_olish(message.from_user.id)
    if not user or user[0] not in ["kassir", "direktor"]: return
    bugun = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect('maktab_baza.db')
    cursor = conn.cursor()
    cursor.execute("SELECT usul, SUM(summa) FROM tolovlar WHERE date(sana) = ? GROUP BY usul", (bugun,))
    tushumlar = cursor.fetchall()
    cursor.execute("SELECT SUM(summa) FROM xarajatlar WHERE date(sana) = ?", (bugun,))
    xarajat = cursor.fetchone()[0] or 0
    conn.close()
    
    matn = f"<b>📊 BUGUNGI KASSA ({bugun}):</b>\n\n<b>KIRIM:</b>\n"
    jami = 0
    for t in tushumlar:
        matn += f"• {t[0]}: {t[1]:,.0f} so'm\n"
        jami += t[1]
    matn += f"\n<b>CHIQIM:</b>\n• {xarajat:,.0f} so'm\n\n<b>QOLDIQ:</b> {(jami - xarajat):,.0f} so'm"
    await message.answer(matn, parse_mode="HTML")

# ---- 9. O'QITUVCHI MAOSHI VA DAVOMAT ----
@dp.message_handler(Text(equals="📝 Davomat qilish"))
async def davomat_guruhlar(message: types.Message):
    user = sessiya_olish(message.from_user.id)
    if not user or user[0] != "oqituvchi": return
    conn = sqlite3.connect('maktab_baza.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, nomi FROM guruhlar WHERE oqituvchi_tel = ?", (user[1],))
    guruhlar = cursor.fetchall()
    conn.close()
    if not guruhlar:
        await message.answer("Sizga tegishli guruhlar yo'q.")
        return
    tugmalar = [[InlineKeyboardButton(text=g[1], callback_data=f"guruh_{g[0]}")] for g in guruhlar]
    await message.answer("Guruhingizni tanlang:", reply_markup=InlineKeyboardMarkup(inline_keyboard=tugmalar))

@dp.callback_query_handler(lambda c: c.data.startswith("guruh_"))
async def davomat_boshlash(callback: types.CallbackQuery, state: FSMContext):
    guruh_id = int(callback.data.split("_")[1])
    conn = sqlite3.connect('maktab_baza.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, ism FROM oquvchilar WHERE guruh_id = ?", (guruh_id,))
    oquvchilar = cursor.fetchall()
    conn.close()
    if not oquvchilar:
        await callback.message.edit_text("Bu guruhda o'quvchilar yo'q.")
        return
    holat = {str(oq[0]): {"ism": oq[1], "keldi": True} for oq in oquvchilar}
    async with state.proxy() as data:
        data['guruh_id'] = guruh_id
        data['davomat_holati'] = holat
    await davomat_oynasi(callback, state)

async def davomat_oynasi(callback: types.CallbackQuery, state: FSMContext):
    async with state.proxy() as data:
        holat = data.get('davomat_holati', {})
    tugmalar = [[InlineKeyboardButton(text=f"{info['ism']} {'✅' if info['keldi'] else '❌'}", callback_data=f"tog_{oq_id}")] for oq_id, info in holat.items()]
    tugmalar.append([InlineKeyboardButton(text="💾 Saqlash", callback_data="davomat_saqla")])
    markup = InlineKeyboardMarkup(inline_keyboard=tugmalar)
    try: await callback.message.edit_text("Davomatni belgilang:", reply_markup=markup)
    except: pass

@dp.callback_query_handler(lambda c: c.data.startswith("tog_"))
async def davomat_ozgartir(callback: types.CallbackQuery, state: FSMContext):
    oq_id = callback.data.split("_")[1]
    async with state.proxy() as data:
        holat = data.get('davomat_holati')
        holat[oq_id]["keldi"] = not holat[oq_id]["keldi"]
        data['davomat_holati'] = holat
    await davomat_oynasi(callback, state)

@dp.callback_query_handler(lambda c: c.data == "davomat_saqla")
async def davomat_saqla(callback: types.CallbackQuery, state: FSMContext):
    async with state.proxy() as data:
        holat = data.get('davomat_holati')
        guruh_id = data.get('guruh_id')
    user = sessiya_olish(callback.from_user.id)
    
    conn = sqlite3.connect('maktab_baza.db')
    cursor = conn.cursor()
    bugun = datetime.now().strftime("%Y-%m-%d")
    for oq_id, info in holat.items():
        status = "Keldi" if info["keldi"] else "Kelmadi"
        cursor.execute("INSERT INTO davomatlar (guruh_id, oquvchi_id, holat, sana, oqituvchi_tel) VALUES (?, ?, ?, ?, ?)",
                       (guruh_id, int(oq_id), status, bugun, user[1]))
    conn.commit()
    conn.close()
    await callback.message.edit_text("✅ Davomat bazaga saqlandi!")
    await state.finish()

@dp.message_handler(Text(equals="⭐ Maosh va Reyting"))
async def oqituvchi_maosh(message: types.Message):
    user = sessiya_olish(message.from_user.id)
    if not user or user[0] != "oqituvchi": return
    conn = sqlite3.connect('maktab_baza.db')
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(id) FROM davomatlar WHERE oqituvchi_tel = ? AND holat = 'Keldi'", (user[1],))
    soni = cursor.fetchone()[0] or 0
    conn.close()
    await message.answer(f"<b>⭐ Oylik ko'rsatkich:</b>\n👥 Darsga kelgan jami o'quvchilar: {soni}\n💰 Taxminiy maosh: <b>{soni * 15000:,.0f} so'm</b>", parse_mode="HTML")

# ---- 10. O'QUVCHILAR VA BLOK TEST YUKLASH (EXCEL) ----
@dp.message_handler(Text(equals="🎓 O'quvchilar va Test"))
async def yuklash_menyu(message: types.Message):
    if sessiya_olish(message.from_user.id)[0] != "direktor": return
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎓 O'quvchilarni Yuklash", callback_data="yukla_oq")],
        [InlineKeyboardButton(text="📈 Blok Test Yuklash", callback_data="yukla_test")]
    ])
    await message.answer("Qaysi birini yuklamoqchisiz?", reply_markup=markup)

@dp.callback_query_handler(lambda c: c.data == "yukla_oq")
async def kutish_oq(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("O'quvchilar <b>Excel (.xlsx)</b> faylini yuboring.\nUstunlar: Ism, Telefon, Ota_ona_tel, Guruh_nomi, Oqituvchi_raqami", parse_mode="HTML")
    await ExcelYuklash.oquvchi_fayl.set()

@dp.callback_query_handler(lambda c: c.data == "yukla_test")
async def kutish_test(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Blok Test <b>Excel (.xlsx)</b> faylini yuboring.\nUstunlar: Telefon, Fan, Ball", parse_mode="HTML")
    await ExcelYuklash.test_fayl.set()

@dp.message_handler(state=ExcelYuklash.oquvchi_fayl, content_types=['document'])
async def oquvchi_qabul(message: types.Message, state: FSMContext):
    if not message.document.file_name.endswith('.xlsx'): return
    await message.answer("⏳ Fayl o'qilmoqda...")
    file_info = await bot.get_file(message.document.file_id)
    await bot.download_file(file_info.file_path, "temp.xlsx")
    try:
        df = pd.read_excel("temp.xlsx", dtype=str)
        conn = sqlite3.connect('maktab_baza.db')
        cursor = conn.cursor()
        yangi, guruh_soni = 0, 0
        for index, row in df.iterrows():
            ism = str(row.get("Ism", "")).strip()
            tel = str(row.get("Telefon", "")).strip().replace(".0", "")
            ota = str(row.get("Ota_ona_tel", "")).strip().replace(".0", "")
            guruh = str(row.get("Guruh_nomi", "")).strip()
            oqituvchi = str(row.get("Oqituvchi_raqami", "")).strip().replace(".0", "")
            
            if tel and not tel.startswith("+"): tel = "+" + tel
            if oqituvchi and not oqituvchi.startswith("+"): oqituvchi = "+" + oqituvchi
            if not ism or ism == "nan": continue
            
            cursor.execute("SELECT id FROM guruhlar WHERE nomi = ? AND oqituvchi_tel = ?", (guruh, oqituvchi))
            g_id = cursor.fetchone()
            if g_id: g_id = g_id[0]
            else:
                cursor.execute("INSERT INTO guruhlar (nomi, oqituvchi_tel) VALUES (?, ?)", (guruh, oqituvchi))
                g_id, guruh_soni = cursor.lastrowid, guruh_soni + 1
            try:
                cursor.execute("INSERT INTO oquvchilar (ism, telefon, ota_ona_tel, guruh_id) VALUES (?, ?, ?, ?)", (ism, tel, ota, g_id))
                yangi += 1
            except: pass
        conn.commit()
        conn.close()
        await message.answer(f"✅ Baza yangilandi! Qo'shildi: {yangi} ta")
    except Exception as e:
        await message.answer(f"❌ Xatolik: {e}")
    finally:
        if os.path.exists("temp.xlsx"): os.remove("temp.xlsx")
        await state.finish()

@dp.message_handler(state=ExcelYuklash.test_fayl, content_types=['document'])
async def test_qabul(message: types.Message, state: FSMContext):
    if not message.document.file_name.endswith('.xlsx'): return
    file_info = await bot.get_file(message.document.file_id)
    await bot.download_file(file_info.file_path, "test.xlsx")
    try:
        df = pd.read_excel("test.xlsx", dtype=str)
        conn = sqlite3.connect('maktab_baza.db')
        cursor = conn.cursor()
        for index, row in df.iterrows():
            tel = str(row.get("Telefon", "")).strip().replace(".0", "")
            if tel and not tel.startswith("+"): tel = "+" + tel
            fan, ball = str(row.get("Fan", "")), float(row.get("Ball", 0))
            cursor.execute("INSERT INTO blok_test (oquvchi_tel, fan, ball) VALUES (?, ?, ?)", (tel, fan, ball))
        conn.commit()
        conn.close()
        await message.answer("✅ Blok test natijalari bazaga saqlandi!")
    except Exception as e:
        await message.answer(f"❌ Xatolik: {e}")
    finally:
        if os.path.exists("test.xlsx"): os.remove("test.xlsx")
        await state.finish()

# ---- 11. UMUMIY DAVOMAT VA LOKATSIYA (DIREKTOR UCHUN) ----
@dp.message_handler(Text(equals="📝 Umumiy Davomat"))
async def dir_davomat(message: types.Message):
    if sessiya_olish(message.from_user.id)[0] != "direktor": return
    conn = sqlite3.connect('maktab_baza.db')
    cursor = conn.cursor()
    cursor.execute("SELECT oquvchilar.ism, davomatlar.holat, davomatlar.sana FROM davomatlar JOIN oquvchilar ON davomatlar.oquvchi_id = oquvchilar.id ORDER BY davomatlar.id DESC LIMIT 15")
    natija = cursor.fetchall()
    conn.close()
    if not natija: return await message.answer("Hozircha davomatlar yo'q.")
    matn = "<b>📊 Oxirgi davomatlar:</b>\n"
    for n in natija: matn += f"• {n[0]} — {'✅' if n[1]=='Keldi' else '❌'}\n"
    await message.answer(matn, parse_mode="HTML")

@dp.message_handler(Text(equals="📍 O'quvchilar Keldi-Ketdi"))
async def dir_lokatsiya(message: types.Message):
    if sessiya_olish(message.from_user.id)[0] != "direktor": return
    conn = sqlite3.connect('maktab_baza.db')
    cursor = conn.cursor()
    cursor.execute("SELECT oquvchilar.ism, keldi_ketdi.vaqt FROM keldi_ketdi JOIN oquvchilar ON keldi_ketdi.oquvchi_tel = oquvchilar.telefon ORDER BY keldi_ketdi.id DESC LIMIT 10")
    natija = cursor.fetchall()
    conn.close()
    if not natija: return await message.answer("Hozircha lokatsiya yo'q.")
    matn = "<b>📍 O'quvchilar kelish/ketish tarixi:</b>\n"
    for n in natija: matn += f"👤 {n[0]} ({n[1]})\n"
    await message.answer(matn, parse_mode="HTML")

async def main():
    print("✅ Tizimli Telegram Bot To'liq Ishga Tushdi!")
    await dp.start_polling(dp, skip_updates=True)

if __name__ == "__main__":
    from aiogram import executor
    
    # Python 3.15 va aiogram 2.x moslashuvi uchun maxsus oqim
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    print("✅ Tizimli Telegram Bot To'liq Ishga Tushdi!")
    executor.start_polling(dp, skip_updates=True)
