import os
import time
import json
import re
import uuid
import threading
import telebot
from telebot import types
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
import uvicorn

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "9298788182:AAHoXdCXG45c9HY2H472OzhR3l5U3hIhVT0")
CONFIG_FILE = "config.json"
DATA_DIR = "generated_htmls"
PORT = int(os.getenv("PORT", 10000))
WEB_BASE_URL = os.getenv("WEB_BASE_URL", "https://json-bot-17bm.onrender.com")

os.makedirs(DATA_DIR, exist_ok=True)

env_admin = os.getenv("ADMIN_ID")
initial_admins = [int(env_admin)] if env_admin and env_admin.isdigit() else [8338099238]

default_config = {
    "admin_ids": initial_admins,
    "channels": [
        {
            "id": "@shein577",
            "link": "https://t.me/shein577",
            "title": "Main Channel"
        }
    ],
    "force_sub": True,
    "users": initial_admins.copy()
}

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                for a in initial_admins:
                    if a not in cfg.get("admin_ids", []):
                        cfg.setdefault("admin_ids", []).append(a)
                if "channels" not in cfg:
                    cfg["channels"] = []
                    if cfg.get("channel_id"):
                        cfg["channels"].append({
                            "id": cfg.get("channel_id"),
                            "link": cfg.get("channel_link", "https://t.me"),
                            "title": "Channel 1"
                        })
                return cfg
        except Exception:
            return default_config.copy()
    else:
        save_config(default_config)
        return default_config.copy()

def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4)

config = load_config()
bot = telebot.TeleBot(BOT_TOKEN)

# ==================== FASTAPI WEB SERVER ====================
app = FastAPI()

@app.api_route("/", methods=["GET", "HEAD"])
def home():
    return {"status": "ok", "message": "One-Tap JSON Viewer Bot is live!"}

@app.api_route("/healthz", methods=["GET", "HEAD"])
def healthz():
    return {"status": "ok"}

@app.get("/view/{filename}", response_class=HTMLResponse)
def view_html(filename: str):
    clean_name = os.path.basename(filename)
    filepath = os.path.join(DATA_DIR, clean_name)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="JSON Viewer file not found or expired.")
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()

# ==================== BOT HELPER LOGIC ====================

def is_admin(user_id):
    return user_id in config.get("admin_ids", [])

def get_unjoined_channels(user_id):
    if not config.get("force_sub", True):
        return []
    
    channels = config.get("channels", [])
    if not channels:
        return []

    unjoined = []
    for ch in channels:
        ch_id = ch.get("id")
        if not ch_id:
            continue
        try:
            member = bot.get_chat_member(ch_id, user_id)
            if member.status not in ['creator', 'administrator', 'member']:
                unjoined.append(ch)
        except Exception as e:
            print(f"Error checking channel {ch_id}: {e}")
            pass
    return unjoined

def parse_json_content(raw_text):
    raw_text = raw_text.strip()
    try:
        parsed = json.loads(raw_text)
        if isinstance(parsed, list):
            return parsed
        elif isinstance(parsed, dict):
            for k, v in parsed.items():
                if isinstance(v, list) and len(v) > 0 and isinstance(v[0], (dict, list)):
                    return v
            return [parsed]
    except Exception:
        pass

    items = []
    lines = raw_text.splitlines()
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            items.append(obj)
        except Exception:
            pass
    if items:
        return items

    pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
    matches = re.findall(pattern, raw_text)
    for m in matches:
        try:
            obj = json.loads(m)
            items.append(obj)
        except Exception:
            pass

    return items

def generate_html_viewer(json_items, output_path):
    template_path = os.path.join(os.path.dirname(__file__), "template.html")
    with open(template_path, "r", encoding="utf-8") as f:
        html = f.read()

    js_data = f"const jsonDataList = {json.dumps(json_items, ensure_ascii=False)};"
    html = html.replace("// RAW_JSON_DATA_PLACEHOLDER", js_data)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)


# ==================== BOT HANDLERS ====================

@bot.message_handler(commands=['start'])
def handle_start(message):
    user_id = message.from_user.id
    if user_id not in config.get("users", []):
        config["users"].append(user_id)
        save_config(config)

    if not is_admin(user_id):
        unjoined = get_unjoined_channels(user_id)
        if unjoined:
            show_force_sub_message(message.chat.id, unjoined)
            return

    show_main_menu(message.chat.id, message.from_user.first_name, is_admin(user_id))


def show_force_sub_message(chat_id, unjoined_channels):
    text = (
        "🔒 *Access Locked - Join Our Channels*\n\n"
        "Bot use karne ke liye aapko hamare official channels ko join karna anivarya hai.\n\n"
        "👇 *Kripya sabhi channels join karein aur 'Verify Joined' par click karein:*"
    )
    markup = types.InlineKeyboardMarkup()
    for i, ch in enumerate(unjoined_channels, 1):
        title = ch.get("title") or f"Channel {i}"
        markup.add(types.InlineKeyboardButton(f"📢 Join {title}", url=ch.get("link", "https://t.me")))
    
    markup.add(types.InlineKeyboardButton("🔄 Verify Joined ✅", callback_data="check_sub"))
    bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=markup)


def show_main_menu(chat_id, first_name, is_adm=False):
    welcome_text = (
        f"👋 *Hello {first_name}!*\n\n"
        f"✨ *One-Tap JSON Viewer Bot Me Swagat Hai!*\n\n"
        f"Is bot se aap kisi bhi JSON file ko stylish interactive cards me badal sakte hain:\n"
        f"🔹 *Har JSON alag-alag card* me display hoga\n"
        f"🔹 *One-Tap COPY JSON* button\n"
        f"🔹 *Used Data Delete* karne ka option\n"
        f"🔹 *Search Bar* (Filter mobile / IDs / tokens)\n\n"
        f"👉 *Apni JSON File (`.json` ya `.txt`) yahan send karein:* 📤"
    )
    markup = types.InlineKeyboardMarkup()
    if is_adm:
        markup.add(types.InlineKeyboardButton("⚙️ Open Admin Panel", callback_data="admin_panel"))

    bot.send_message(chat_id, welcome_text, parse_mode="Markdown", reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data == "check_sub")
def callback_check_sub(call):
    user_id = call.from_user.id
    unjoined = get_unjoined_channels(user_id)
    if not unjoined:
        try:
            bot.answer_callback_query(call.id, "✅ Verified Successfully! Welcome.")
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except Exception:
            pass
        show_main_menu(call.message.chat.id, call.from_user.first_name, is_admin(user_id))
    else:
        try:
            bot.answer_callback_query(
                call.id,
                f"❌ Aapne abhi tak {len(unjoined)} channel(s) join nahi kiye! Kripya sabhi join karein.",
                show_alert=True
            )
        except Exception:
            pass


# ==================== ADMIN PANEL ====================

@bot.message_handler(commands=['admin'])
def handle_admin_command(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.send_message(message.chat.id, "❌ Aap admin nahi hain.")
        return
    show_admin_panel(message.chat.id)


def show_admin_panel(chat_id, message_id=None):
    total_users = len(config.get("users", []))
    force_sub_status = "🟢 ENABLED" if config.get("force_sub", True) else "🔴 DISABLED"
    channels = config.get("channels", [])
    ch_text = ""
    if channels:
        for idx, ch in enumerate(channels, 1):
            ch_text += f"{idx}. `{ch.get('id')}` - [{ch.get('title')}]({ch.get('link')})\n"
    else:
        ch_text = "_Koi channel add nahi hai._\n"

    text = (
        f"👑 *ADMIN CONTROL PANEL*\n\n"
        f"👥 *Total Bot Users:* `{total_users}`\n"
        f"🔒 *Force Subscribe:* `{force_sub_status}`\n\n"
        f"📢 *Connected Channels ({len(channels)}):*\n{ch_text}\n"
        f"Niche diye gaye buttons se channels aur settings control karein:"
    )

    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_toggle = types.InlineKeyboardButton(
        f"Force Sub: {'Turn OFF' if config.get('force_sub', True) else 'Turn ON'}",
        callback_data="admin_toggle_fsub"
    )
    btn_add_ch = types.InlineKeyboardButton("➕ Add Channel", callback_data="admin_add_channel")
    btn_manage_ch = types.InlineKeyboardButton("🗑️ Remove Channel", callback_data="admin_list_remove_channels")
    btn_add_admin = types.InlineKeyboardButton("👤 Add Admin", callback_data="admin_add_admin")
    btn_broadcast = types.InlineKeyboardButton("📣 Broadcast Message", callback_data="admin_broadcast")
    btn_close = types.InlineKeyboardButton("🔙 Close Panel", callback_data="admin_close")

    markup.add(btn_toggle)
    markup.add(btn_add_ch, btn_manage_ch)
    markup.add(btn_add_admin, btn_broadcast)
    markup.add(btn_close)

    if message_id:
        bot.edit_message_text(text, chat_id, message_id, parse_mode="Markdown", reply_markup=markup, disable_web_page_preview=True)
    else:
        bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=markup, disable_web_page_preview=True)


@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_"))
def handle_admin_callback(call):
    user_id = call.from_user.id
    if not is_admin(user_id):
        try:
            bot.answer_callback_query(call.id, "❌ Access Denied!", show_alert=True)
        except Exception:
            pass
        return

    try:
        bot.answer_callback_query(call.id)
    except Exception:
        pass

    data = call.data
    if data == "admin_panel":
        show_admin_panel(call.message.chat.id, call.message.message_id)

    elif data == "admin_toggle_fsub":
        config["force_sub"] = not config.get("force_sub", True)
        save_config(config)
        show_admin_panel(call.message.chat.id, call.message.message_id)

    elif data == "admin_add_channel":
        msg = bot.send_message(
            call.message.chat.id,
            "📢 *Channel Add Karne Ka Format:*\n\n"
            "`ChannelTitle | @channel_username | https://t.me/invite_link`\n\n"
            "*Example:*\n`Main Channel | @shein577 | https://t.me/shein577`\n\n"
            "⚠️ _Note: Bot ko channel me Administrator banana zaroori hai._",
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, process_add_channel)

    elif data == "admin_list_remove_channels":
        channels = config.get("channels", [])
        if not channels:
            bot.send_message(call.message.chat.id, "ℹ️ Koi channel add nahi hai jise remove kiya jaye.")
            return

        markup = types.InlineKeyboardMarkup()
        for i, ch in enumerate(channels):
            markup.add(types.InlineKeyboardButton(f"🗑️ Delete {ch.get('title')} ({ch.get('id')})", callback_data=f"del_ch_{i}"))
        markup.add(types.InlineKeyboardButton("🔙 Back", callback_data="admin_panel"))

        bot.edit_message_text(
            "🗑️ *Kaunsa channel remove karna chahte hain? Click karein:*",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )

    elif data == "admin_add_admin":
        msg = bot.send_message(
            call.message.chat.id,
            "➕ Send the Telegram Numeric User ID of the new admin:\n*(Example: `123456789`)*",
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, process_add_admin)

    elif data == "admin_broadcast":
        msg = bot.send_message(call.message.chat.id, "📣 Send the message you want to broadcast to all users:")
        bot.register_next_step_handler(msg, process_broadcast)

    elif data == "admin_close":
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except Exception:
            pass


@bot.callback_query_handler(func=lambda call: call.data.startswith("del_ch_"))
def handle_channel_delete(call):
    if not is_admin(call.from_user.id):
        return
    idx = int(call.data.replace("del_ch_", ""))
    channels = config.get("channels", [])
    if 0 <= idx < len(channels):
        removed = channels.pop(idx)
        save_config(config)
        bot.answer_callback_query(call.id, f"✅ {removed.get('title')} removed!")
    show_admin_panel(call.message.chat.id, call.message.message_id)


def process_add_channel(message):
    try:
        parts = [p.strip() for p in message.text.split("|")]
        if len(parts) == 3:
            title, ch_id, link = parts[0], parts[1], parts[2]
            new_ch = {"title": title, "id": ch_id, "link": link}
            config.setdefault("channels", []).append(new_ch)
            save_config(config)
            bot.send_message(message.chat.id, f"✅ *Channel '{title}' successfully added!*", parse_mode="Markdown")
            show_admin_panel(message.chat.id)
        elif len(parts) == 2:
            ch_id, link = parts[0], parts[1]
            new_ch = {"title": ch_id, "id": ch_id, "link": link}
            config.setdefault("channels", []).append(new_ch)
            save_config(config)
            bot.send_message(message.chat.id, f"✅ *Channel successfully added!*", parse_mode="Markdown")
            show_admin_panel(message.chat.id)
        else:
            bot.send_message(message.chat.id, "❌ Invalid format. Use: `Title | @username | link`")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Error: {e}")


def process_add_admin(message):
    try:
        new_id = int(message.text.strip())
        if new_id not in config.get("admin_ids", []):
            config["admin_ids"].append(new_id)
            save_config(config)
            bot.send_message(message.chat.id, f"✅ User ID `{new_id}` is now an Admin!", parse_mode="Markdown")
        else:
            bot.send_message(message.chat.id, "ℹ️ Yeh user pehle se hi Admin hai.")
    except Exception:
        bot.send_message(message.chat.id, "❌ Invalid User ID. Numeric ID bhejiye.")


def process_broadcast(message):
    users = config.get("users", [])
    sent = 0
    failed = 0
    status_msg = bot.send_message(message.chat.id, "⏳ Broadcasting started...")
    for uid in users:
        try:
            bot.copy_message(uid, message.chat.id, message.message_id)
            sent += 1
        except Exception:
            failed += 1
    bot.edit_message_text(f"✅ *Broadcast Finished!*\n\nSent: `{sent}`\nFailed: `{failed}`", message.chat.id, status_msg.message_id, parse_mode="Markdown")


# ==================== FILE HANDLING ====================

@bot.message_handler(content_types=['document'])
def handle_document(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        unjoined = get_unjoined_channels(user_id)
        if unjoined:
            show_force_sub_message(message.chat.id, unjoined)
            return

    doc = message.document
    progress_msg = bot.send_message(message.chat.id, "⏳ *File process ho rahi hai...*", parse_mode="Markdown")

    try:
        file_info = bot.get_file(doc.file_id)
        downloaded_bytes = bot.download_file(file_info.file_path)
        content_text = downloaded_bytes.decode('utf-8', errors='ignore')

        json_items = parse_json_content(content_text)
        if not json_items:
            bot.edit_message_text(
                "❌ *File me koi valid JSON data nahi mila!* Kripya valid `.json` ya line-by-line JSON wali `.txt` file bhejein.",
                message.chat.id,
                progress_msg.message_id,
                parse_mode="Markdown"
            )
            return

        total_count = len(json_items)
        file_token = str(uuid.uuid4())[:8]
        out_filename = f"OneTap_JSON_{total_count}_{file_token}.html"
        out_filepath = os.path.join(DATA_DIR, out_filename)

        generate_html_viewer(json_items, out_filepath)

        caption = (
            f"✅ *Aapka JSON Viewer Ready Hai!*\n\n"
            f"📦 *Total JSON Cards:* `{total_count}`\n\n"
            f"📱 *How to use:*\n"
            f"• Niche button se **🌐 Open Directly in Browser** karein.\n"
            f"• Ya attached HTML file download karke open karein."
        )

        web_base = os.getenv("WEB_BASE_URL", WEB_BASE_URL).strip()
        markup = types.InlineKeyboardMarkup()
        if web_base:
            web_url = f"{web_base.rstrip('/')}/view/{out_filename}"
            markup.add(types.InlineKeyboardButton("🌐 Open Directly in Browser", url=web_url))

        with open(out_filepath, "rb") as html_file:
            bot.send_document(
                message.chat.id,
                html_file,
                caption=caption,
                parse_mode="Markdown",
                reply_markup=markup if web_base else None
            )

        bot.delete_message(message.chat.id, progress_msg.message_id)

    except Exception as e:
        bot.edit_message_text(f"❌ Error: {str(e)}", message.chat.id, progress_msg.message_id)


# Handle Direct Raw Text JSON Paste
@bot.message_handler(func=lambda msg: msg.text and (msg.text.strip().startswith("{") or msg.text.strip().startswith("[")))
def handle_text_json(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        unjoined = get_unjoined_channels(user_id)
        if unjoined:
            show_force_sub_message(message.chat.id, unjoined)
            return

    progress_msg = bot.send_message(message.chat.id, "⏳ *Text process ho raha hai...*", parse_mode="Markdown")
    try:
        json_items = parse_json_content(message.text)
        if not json_items:
            bot.edit_message_text("❌ No valid JSON found.", message.chat.id, progress_msg.message_id)
            return

        total_count = len(json_items)
        file_token = str(uuid.uuid4())[:8]
        out_filename = f"OneTap_JSON_{total_count}_{file_token}.html"
        out_filepath = os.path.join(DATA_DIR, out_filename)

        generate_html_viewer(json_items, out_filepath)

        web_base = os.getenv("WEB_BASE_URL", WEB_BASE_URL).strip()
        markup = types.InlineKeyboardMarkup()
        if web_base:
            web_url = f"{web_base.rstrip('/')}/view/{out_filename}"
            markup.add(types.InlineKeyboardButton("🌐 Open Directly in Browser", url=web_url))

        with open(out_filepath, "rb") as html_file:
            bot.send_document(
                message.chat.id,
                html_file,
                caption=f"✅ *HTML Ready!* Total Cards: `{total_count}`\nOpen in Browser.",
                parse_mode="Markdown",
                reply_markup=markup if web_base else None
            )
        bot.delete_message(message.chat.id, progress_msg.message_id)
    except Exception as e:
        bot.edit_message_text(f"❌ Error: {str(e)}", message.chat.id, progress_msg.message_id)


def start_bot_polling():
    while True:
        try:
            print("🚀 Telegram Bot is polling...")
            bot.infinity_polling(skip_pending=True, timeout=20, long_polling_timeout=20)
        except Exception as e:
            print(f"⚠️ Polling Exception (retrying in 5s): {e}")
            time.sleep(5)


if __name__ == "__main__":
    t = threading.Thread(target=start_bot_polling, daemon=True)
    t.start()

    print(f"🌐 FastAPI Web Server listening on port {PORT}...")
    uvicorn.run(app, host="0.0.0.0", port=PORT, access_log=True)
