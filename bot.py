import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room
import random, string
from flask_cors import CORS
import threading, os, time
import json
from datetime import datetime
from fpdf import FPDF
import urllib.request # NAYA: PDF font download ke liye

# ==========================================
# ⚙️ CONFIGURATION
# ==========================================
BOT_TOKEN = os.environ.get("BOT_TOKEN") 
WEB_APP_URL = os.environ.get("WEB_APP_URL", "https://aapka-app-name.onrender.com") 

ADMIN_ID = 8718760365

# Channel Details for Verification
CHANNEL_USERNAME = "@errorkid_05" 
CHANNEL_LINK = "https://t.me/errorkid_05"
CHANNEL_LINK1 = "https://t.me/+H3-K7T29hVdhYzY1"

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*")

# database 
from pymongo import MongoClient

MONGO_URI = os.environ.get("MONGO_URI") 
client = MongoClient(MONGO_URI)
db = client['bseb_quiz_db']
db_collection = db['app_data']

def load_db():
    try:
        doc = db_collection.find_one({"_id": "main_data"})
        if doc and "data" in doc:
            return doc["data"]
        else:
            return {"users": {}, "questions": [], "logs": []}
    except Exception as e:
        print(f"DB Load Error: {e}")
        return {"users": {}, "questions": [], "logs": []}

def save_db(db_data):
    try:
        db_collection.update_one(
            {"_id": "main_data"}, 
            {"$set": {"data": db_data}}, 
            upsert=True
        )
    except Exception as e:
        print(f"DB Save Error: {e}")

db_data = load_db()
db_connected = True


# ==========================================
# 🔐 SUBSCRIPTION CHECK (STRICT MODE)
# ==========================================
def check_membership(user_id):
    try:
        member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        if member.status in ['creator', 'administrator', 'member']:
            return True
        return False
    except Exception as e:
        print(f"Membership Check Error: {e}")
        return False

# ==========================================
# 🧮 LOGIC
# ==========================================
def calculate_grade_stats(xp):
    level = 1; cost = 100; temp_xp = xp
    while temp_xp >= cost:
        temp_xp -= cost; level += 1; cost += 20
    percent = (temp_xp / cost) * 100
    return {"grade": level, "current_xp": temp_xp, "req_xp": cost, "percent": min(percent, 100)}

def parse_txt_file(content):
    lines = content.splitlines()
    meta = {"path": [], "mode": "normal", "medium": "hi"} 
    questions = []
    
    for line in lines[:10]:
        lower = line.lower()
        if lower.startswith("medium:"): 
            meta["medium"] = line.split(":", 1)[1].strip().lower()
        if lower.startswith("path:"): 
            raw_path = line.split(":", 1)[1].strip()
            meta["path"] = [p.strip() for p in raw_path.split("/") if p.strip()]
        if lower.startswith("mode:"): 
            meta["mode"] = line.split(":", 1)[1].strip().lower() 
            
    if not meta["path"]: 
        return None, "❌ Header Missing! Please use 'Path: Folder1 / Folder2 ...'"
        
    for line in lines:
        if "|" in line and not line.upper().startswith(("PATH:", "MEDIUM:", "MODE:")):
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 6:
                try:
                    ans = int(parts[5]) - 1
                    if 0 <= ans <= 3:
                        questions.append({"q": parts[0], "opts": parts[1:5], "ans": ans})
                except: pass
    return meta, questions


# ============================
# 🤖 BOT HANDLERS
# ==========================================

def send_welcome_menu(chat_id, first_name, user_id, lang):
    markup = InlineKeyboardMarkup()
    
    app_url = f"{WEB_APP_URL}?lang={lang}"
    
    # NAYA 5: Button Colors using Emojis
    btn_text = "🟢 🧬 अभ्यास शुरू करें 🧬" if lang == 'hi' else "🟢 🧬 START 🧬"
    
    markup.add(InlineKeyboardButton(btn_text, web_app=WebAppInfo(url=app_url)))
    markup.row(
        InlineKeyboardButton("🔵 📢 𝗢𝗳𝗳𝗶𝗰𝗶𝗮𝗹 𝗖𝗵𝗮𝗻𝗻𝗲𝗹", url=CHANNEL_LINK1),
        InlineKeyboardButton("🔵 👨‍⚕️ 𝗛𝗲𝗹𝗽 𝗖𝗲𝗻𝘁𝗲𝗿", url="https://t.me/errorkidk")
    )
    
    lang_btn_text = "🔴 ⚙️ भाषा बदलें (Change Lang)" if lang == 'hi' else "🔴 ⚙️ Change Language"
    markup.add(InlineKeyboardButton(lang_btn_text, callback_data="show_lang_menu"))
    
    try:
        photos = bot.get_user_profile_photos(user_id)
        if photos.total_count > 0:
            media = photos.photos[0][-1].file_id
        else:
            media = "https://cdn-icons-png.flaticon.com/512/3135/3135715.png"
    except Exception as e:
        media = "https://cdn-icons-png.flaticon.com/512/3135/3135715.png"

    caption = f"🏆 <b>BSEB QUIZ PRO 🧾</b> 🏆\n\n" \
              f"<blockquote>👤 <b>User:</b> {first_name}\n" \
              f"🆔 <b>ID:</b> <code>{user_id}</code>\n" \
              f"👑 <b>Status:</b> Premium Access\n" \
              f"🌐 <b>Medium:</b> {'Hindi' if lang == 'hi' else 'English'}</blockquote>\n" \
              f"<blockquote>💬 <b> BOT LIVE. </b>\n" \
              f"Click below to start our mini app.</blockquote>"
    try:
        bot.send_photo(chat_id, photo=media, caption=caption, reply_markup=markup, parse_mode="HTML")
    except:
        bot.send_message(chat_id, caption, reply_markup=markup, parse_mode="HTML")

@bot.message_handler(commands=['start'])
def start(m):
    uid = str(m.from_user.id)
    if not check_membership(int(uid)):
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("📢 Join Channel (यहाँ जुड़ें)", url=CHANNEL_LINK))
        markup.add(InlineKeyboardButton("🔄 Check Status", callback_data="check_sub"))
        
        # NAYA 1: Bilingual & Formal Access Denied Message
        msg_text = (
            "🎓 <b>Welcome to BSEB Quiz Pro! / आपका स्वागत है!</b>\n\n"
            "🇬🇧 To access the bot and continue your practice, it is mandatory to join our official channel. Please join via the button below and click 'Check Status'.\n\n"
            "🇮🇳 बॉट का उपयोग करने और अपना अभ्यास जारी रखने के लिए, हमारे आधिकारिक चैनल से जुड़ना अनिवार्य है। कृपया नीचे दिए गए बटन से चैनल ज्वाइन करें और फिर 'Check Status' पर क्लिक करें।"
        )
        bot.send_message(m.chat.id, msg_text, reply_markup=markup, parse_mode="HTML")
        return
        
    user = db_data['users'].get(uid, {})
    if 'medium' not in user:
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🇮🇳 Hindi Medium", callback_data="lang_hi"))
        markup.add(InlineKeyboardButton("🇬🇧 English Medium", callback_data="lang_en"))
        bot.send_message(m.chat.id, "🌐 **Choose your Language / अपनी भाषा चुनें:**", reply_markup=markup, parse_mode="Markdown")
        return
        
    send_welcome_menu(m.chat.id, m.from_user.first_name, uid, user['medium'])

@bot.callback_query_handler(func=lambda call: call.data.startswith("lang_"))
def set_language(call):
    # NAYA 2: Fix Loading Issue on Language Button
    bot.answer_callback_query(call.id, "Language Updated! / भाषा अपडेट हो गई!")
    
    uid = str(call.from_user.id)
    lang = call.data.split("_")[1] 
    
    if uid not in db_data['users']:
        db_data['users'][uid] = {"_id": uid, "name": call.from_user.first_name, "xp": 0, "mistakes": []}
        
    db_data['users'][uid]['medium'] = lang
    save_db(db_data)
    
    bot.delete_message(call.message.chat.id, call.message.message_id)
    send_welcome_menu(call.message.chat.id, call.from_user.first_name, uid, lang)

# NAYA 2 (Part B): Fix logic for the red 'Change Language' inline button
@bot.callback_query_handler(func=lambda call: call.data == "show_lang_menu")
def show_lang_menu_callback(call):
    bot.answer_callback_query(call.id)
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🇮🇳 Hindi Medium", callback_data="lang_hi"))
    markup.add(InlineKeyboardButton("🇬🇧 English Medium", callback_data="lang_en"))
    bot.send_message(call.message.chat.id, "⚙️ **Update Language / माध्यम बदलें:**", reply_markup=markup, parse_mode="Markdown")

@bot.message_handler(commands=['language', 'settings'])
def change_lang(m):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🇮🇳 Hindi Medium", callback_data="lang_hi"))
    markup.add(InlineKeyboardButton("🇬🇧 English Medium", callback_data="lang_en"))
    bot.send_message(m.chat.id, "⚙️ **Update Language / माध्यम बदलें:**", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "check_sub")
def callback_check(call):
    uid = call.from_user.id
    if check_membership(uid):
        bot.answer_callback_query(call.id, "✅ Verified!")
        bot.delete_message(call.message.chat.id, call.message.message_id)
        send_welcome_menu(call.message.chat.id, call.from_user.first_name, uid, "hi") # Defaulting fallback to 'hi' if medium missed
    else:
        bot.answer_callback_query(call.id, "❌ Not Joined Yet!", show_alert=True)

@bot.message_handler(commands=['broadcast'])
def broadcast_message(message):
    uid = str(message.from_user.id)
    if uid != str(ADMIN_ID): return 
    msg_text = message.text.split(maxsplit=1)
    if len(msg_text) < 2:
        bot.reply_to(message, "⚠️ Usage: `/broadcast Your Message Here`")
        return
    text_to_send = msg_text[1]
    
    users = list(db_data['users'].values())
    success, blocked = 0, 0
    status_msg = bot.reply_to(message, f"🚀 Broadcast started to {len(users)} users...")
    
    for user in users:
        try:
            bot.send_message(user['_id'], f"📢 **ANNOUNCEMENT**\n\n{text_to_send}", parse_mode="Markdown")
            success += 1
            time.sleep(0.1) 
        except:
            blocked += 1
    bot.edit_message_text(f"✅ **Broadcast Complete!**\n\nSent: {success}\nFailed/Blocked: {blocked}", message.chat.id, status_msg.message_id)

@bot.message_handler(commands=['backup'])
def export_backup(message):
    uid = str(message.from_user.id)
    if uid != str(ADMIN_ID): return  
    bot.send_message(message.chat.id, "⏳ Creating Backup... Please wait.")
    try:
        file_name = f"BiharBoard_Backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(file_name, "w", encoding="utf-8") as f:
            json.dump(db_data, f, indent=4)
        with open(file_name, "rb") as f:
            bot.send_document(message.chat.id, f, caption="✅ **Full Database Backup**\n\nIs file ko sambhal kar rakhein.")
        os.remove(file_name) 
    except Exception as e:
        bot.reply_to(message, f"❌ Backup Failed: {str(e)}")

@bot.message_handler(content_types=['document'])
def handle_docs(message):
    if str(message.from_user.id) != str(ADMIN_ID): return 
    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded = bot.download_file(file_info.file_path)
        content = downloaded.decode('utf-8')
        
        if message.caption == '/restore' and message.document.file_name.endswith('.json'):
            global db_data
            db_data = json.loads(content)
            save_db(db_data)
            bot.reply_to(message, "✅ **Restore Successful!**\nData wapas aa gaya hai.")
            return
        
        meta, parsed_q = parse_txt_file(content)
        if not meta: 
            bot.reply_to(message, parsed_q) 
            return

        db_data['questions'] = [q for q in db_data.get('questions', []) if not (q.get('path') == meta['path'] and q.get('medium', 'hi') == meta['medium'])]
        
        new_q = {"path": meta['path'], "mode": meta['mode'], "medium": meta['medium'], "data": parsed_q}
        db_data['questions'].append(new_q)
        save_db(db_data)
        
        path_str = " ➔ ".join(meta['path'])
        bot.reply_to(message, f"☁️ Saved in [{meta['medium'].upper()}]: {path_str}\n({len(parsed_q)} Qs)")
        
    except Exception as e:
        bot.reply_to(message, f"Error: {e}")


# ==========================================
# 🌐 API ROUTES
# ==========================================
@app.route('/')
def index(): 
    lang = request.args.get('lang', 'en')
    if lang == 'hi':
        return render_template('quiz_hi.html')
    return render_template('quiz_en.html')

@app.route('/api/get_data')
def get_data():
    req_lang = request.args.get('lang', 'hi') 
    
    tree = {}
    for doc in db_data.get('questions', []):
        if doc.get('medium', 'hi') != req_lang:
            continue
            
        path = doc.get('path', [])
        if not path: continue
        
        current_level = tree
        for p in path[:-1]:
            if p not in current_level:
                current_level[p] = {}
            current_level = current_level[p]
            
        last_node = path[-1]
        current_level[last_node] = {"data": doc['data'], "mode": doc.get('mode', 'normal')}
        
    return jsonify(tree)

@app.route('/api/admin/delete', methods=['POST'])
def delete_item():
    data = request.json
    if str(data.get('uid')) != str(ADMIN_ID): return jsonify({"error": "Unauthorized"})
    
    target_path = data.get('path', []) + [data.get('target')]
    
    try:
        new_questions = []
        for q in db_data.get('questions', []):
            q_path = q.get('path', [])
            if q_path[:len(target_path)] == target_path:
                continue 
            new_questions.append(q)
                
        db_data['questions'] = new_questions
        save_db(db_data)
        return jsonify({"status": "deleted"})
    except Exception as e: 
        return jsonify({"error": str(e)})

@app.route('/api/user/sync', methods=['POST'])
def sync_user():
    data = request.json
    uid, name = str(data.get('id')), data.get('name')
    score_add = int(data.get('add_score', 0))
    mistakes = data.get('mistakes', [])
    solved = data.get('solved', [])
    
    if uid not in db_data['users']:
        db_data['users'][uid] = {"_id": uid, "name": name, "xp": 0, "mistakes": []}
    
    user = db_data['users'][uid]
    user['xp'] = max(0, user.get('xp', 0) + score_add)
    user['name'] = name 
    
    if score_add > 0: 
        db_data['logs'].append({"uid": uid, "name": name, "score": score_add, "ts": time.time()})
    
    curr_mistakes = user.get('mistakes', [])
    exist = {m['q'] for m in curr_mistakes}
    
    new_mistakes_for_pdf = []
    for m in mistakes: 
        if m['q'] not in exist: 
            curr_mistakes.append(m)
            new_mistakes_for_pdf.append(m)
            
    if solved: 
        curr_mistakes = [m for m in curr_mistakes if m['q'] not in solved]
        
    user['mistakes'] = curr_mistakes
    save_db(db_data)
    
    # PDF Logic
    if new_mistakes_for_pdf:
        try:
            # NAYA 4: Hindi Font download and embedding logic for perfect PDF
            font_path = "NotoSansDevanagari-Regular.ttf"
            if not os.path.exists(font_path):
                font_url = "https://github.com/google/fonts/raw/main/ofl/notosansdevanagari/NotoSansDevanagari-Regular.ttf"
                urllib.request.urlretrieve(font_url, font_path)

            pdf = FPDF()
            pdf.add_page()
            
            # Setup custom unicode font
            try:
                pdf.add_font("Hindi", "", font_path, uni=True)
                pdf.set_font("Hindi", "", 16)
            except:
                try:
                    pdf.add_font("Hindi", "", font_path)
                    pdf.set_font("Hindi", "", 16)
                except:
                    pdf.set_font("Arial", 'B', 16)

            pdf.cell(200, 10, txt="Quiz Mistakes Report", ln=True, align='C')
            pdf.ln(10)
            
            for idx, m in enumerate(new_mistakes_for_pdf):
                q_text = f"Q{idx+1}: {m['q']}"
                try:
                    pdf.set_font("Hindi", "", 11)
                except:
                    pdf.set_font("Arial", 'B', 11)
                    q_text = q_text.encode('latin-1', 'replace').decode('latin-1')
                    
                pdf.multi_cell(0, 10, txt=q_text)
                
                try:
                    pdf.set_font("Hindi", "", 10)
                except:
                    pdf.set_font("Arial", "", 10)
                    
                for i, opt in enumerate(m['opts']):
                    prefix = "[ CORRECT ] " if i == m['ans'] else " - "
                    opt_text = f"{prefix}{opt}"
                    if not os.path.exists(font_path):
                        opt_text = opt_text.encode('latin-1', 'replace').decode('latin-1')
                    pdf.multi_cell(0, 8, txt=opt_text)
                pdf.ln(5)
                
            file_name = f"Mistakes_{uid}_{int(time.time())}.pdf"
            pdf.output(file_name)
            with open(file_name, 'rb') as f:
                bot.send_document(uid, f, caption="🚨 **Your Quiz Analytics**\n\nHere is a PDF of the questions you got wrong.")
            os.remove(file_name) 
        except Exception as e: 
            print("PDF Error:", e)

    stats = calculate_grade_stats(user['xp'])
    return jsonify({
        "grade": f"Grade {stats['grade']}", 
        "current_xp": stats['current_xp'], 
        "req_xp": stats['req_xp'], 
        "percent": stats['percent'], 
        "mistake_count": len(curr_mistakes), 
        "mistakes_list": curr_mistakes
    })

@app.route('/api/leaderboard/<filter>')
def leaderboard(filter):
    uid_req = request.args.get('uid')
    now = time.time()
    
    if filter == 'all':
        users_list = list(db_data['users'].values())
        users_list.sort(key=lambda x: x.get('xp', 0), reverse=True)
        top_100 = [{"rank": i+1, "name": u['name'], "score": u.get('xp', 0), "uid": u['_id']} for i, u in enumerate(users_list[:100])]
    else:
        time_limit = now - (86400 if filter == 'daily' else 604800)
        valid_logs = [log for log in db_data['logs'] if log['ts'] > time_limit]
        
        user_scores = {}
        for log in valid_logs:
            if log['uid'] not in user_scores: user_scores[log['uid']] = {"name": log['name'], "score": 0}
            user_scores[log['uid']]['score'] += log['score']
            
        sorted_users = sorted(user_scores.items(), key=lambda x: x[1]['score'], reverse=True)
        top_100 = [{"rank": i+1, "name": u[1]['name'], "score": u[1]['score'], "uid": u[0]} for i, u in enumerate(sorted_users[:100])]
    
    user_rank = next((u for u in top_100 if u['uid'] == uid_req), None)
    return jsonify({"top": top_100, "user": user_rank})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    t = threading.Thread(target=lambda: socketio.run(app, host="0.0.0.0", port=port, allow_unsafe_werkzeug=True))
    t.start()
    bot.infinity_polling()
