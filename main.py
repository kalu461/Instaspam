import os
import time
import json
import threading
from pathlib import Path
from instagrapi import Client
from instagrapi.exceptions import LoginRequired, ChallengeRequired

INSTAGRAM_USERNAME = ("n4nxr")
INSTAGRAM_PASSWORD = ("TAUHIDK944")
WELCOME_MESSAGE = os.environ.get("WELCOME_MESSAGE", "Welcome to the group! 👋")
VERIFICATION_CODE = os.environ.get("code", "")

ADMIN_USERNAMES = ["n9bix"]

SESSION_FILE = "session.json"
KNOWN_MEMBERS_FILE = "known_members.json"
PROCESSED_MESSAGES_FILE = "processed_messages.json"
SETTINGS_FILE = "bot_settings.json"

CHECK_INTERVAL = 0.01

HEARTS = ["❤️", "🧡", "💛", "💚", "💙", "💜", "🤎", "🖤", "🤍", "💖", "💗", "💓", "💟"]

BOT_COMMANDS = {
    "/help": "Show all available commands",
    "/ping": "Show bot latency",
    "/nc {text}": "Change group name with rotating hearts",
    "/send {text}": "Send message in loop until /stop",
    "/stop": "Stop sending messages",
    "/delay {seconds}": "Set delay between messages",
    "/kick": "Kick a user from the group (mention user)",
    "/mute": "Mute the group",
    "/unmute": "Unmute the group",
    "/welcome": "Set custom welcome message",
    "/members": "Show member count",
    "/admins": "Show bot admins",
    "/settings": "Show current bot settings",
}

bot_settings = {
    "threads": 20,
    "delay": 0,
    "heart_index": {},
    "sending": {},
    "send_text": {}
}

bombing_threads = {}
stop_flags = {}

def load_settings():
    global bot_settings
    if Path(SETTINGS_FILE).exists():
        with open(SETTINGS_FILE, 'r') as f:
            loaded = json.load(f)
            bot_settings.update(loaded)
    return bot_settings

def save_settings():
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(bot_settings, f, indent=2)

def get_next_heart(thread_id):
    thread_id = str(thread_id)
    if thread_id not in bot_settings["heart_index"]:
        bot_settings["heart_index"][thread_id] = 0
    
    heart = HEARTS[bot_settings["heart_index"][thread_id]]
    bot_settings["heart_index"][thread_id] = (bot_settings["heart_index"][thread_id] + 1) % len(HEARTS)
    save_settings()
    return heart

def challenge_code_handler(username, choice):
    if VERIFICATION_CODE:
        print(f"Using verification code from environment: {VERIFICATION_CODE}")
        return VERIFICATION_CODE
    else:
        print("ERROR: Instagram requires verification code!")
        print("Please set VERIFICATION_CODE in secrets and restart.")
        raise Exception("Verification code required")

def load_known_members():
    if Path(KNOWN_MEMBERS_FILE).exists():
        with open(KNOWN_MEMBERS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_known_members(members_dict):
    with open(KNOWN_MEMBERS_FILE, 'w') as f:
        json.dump(members_dict, f, indent=2)

def load_processed_messages():
    if Path(PROCESSED_MESSAGES_FILE).exists():
        with open(PROCESSED_MESSAGES_FILE, 'r') as f:
            return set(json.load(f))
    return set()

def save_processed_messages(messages_set):
    with open(PROCESSED_MESSAGES_FILE, 'w') as f:
        json.dump(list(messages_set), f)

def is_admin(username):
    return username.lower().replace("@", "") in [admin.lower() for admin in ADMIN_USERNAMES]

def login_client():
    cl = Client()
    cl.delay_range = [2, 5]
    cl.challenge_code_handler = challenge_code_handler
    
    if Path(SESSION_FILE).exists():
        try:
            cl.load_settings(SESSION_FILE)
            cl.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
            cl.get_timeline_feed()
            print("Logged in using saved session")
            return cl
        except (LoginRequired, ChallengeRequired):
            print("Session expired, logging in fresh...")
            Path(SESSION_FILE).unlink(missing_ok=True)
    
    try:
        print("Logging in to Instagram...")
        cl.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
        cl.dump_settings(SESSION_FILE)
        print("Logged in successfully and saved session")
        return cl
    except ChallengeRequired as e:
        print(f"Challenge required: {e}")
        print("Please set VERIFICATION_CODE in secrets and restart")
        raise
    except Exception as e:
        print(f"Login failed: {e}")
        raise

def get_all_group_threads(cl):
    try:
        threads = cl.direct_threads(amount=50)
        group_threads = []
        for thread in threads:
            if thread.is_group:
                group_threads.append({
                    'id': str(thread.id),
                    'name': thread.thread_title or f"Group {thread.id}"
                })
        return group_threads
    except Exception as e:
        print(f"Error getting group threads: {e}")
        return []

def get_group_members(cl, thread_id):
    try:
        thread = cl.direct_thread(thread_id)
        return {str(user.pk) for user in thread.users}
    except Exception as e:
        print(f"Error getting group members for thread {thread_id}: {e}")
        return set()

def get_thread_with_users(cl, thread_id, amount=20):
    try:
        thread = cl.direct_thread(thread_id, amount=amount)
        users_map = {str(user.pk): user.username for user in thread.users}
        return thread.messages if thread.messages else [], users_map
    except Exception as e:
        print(f"Error getting messages for thread {thread_id}: {e}")
        return [], {}

def send_message(cl, thread_id, message, reply_to=None):
    try:
        if reply_to:
            cl.direct_send(message, thread_ids=[int(thread_id)], reply_to_message_id=reply_to)
        else:
            cl.direct_send(message, thread_ids=[int(thread_id)])
        return True
    except Exception as e:
        print(f"Error sending message: {e}")
        return False

def send_welcome_message(cl, thread_id, username, group_name):
    try:
        message = f"@{username} {WELCOME_MESSAGE}"
        cl.direct_send(message, thread_ids=[int(thread_id)])
        print(f"Sent welcome to @{username} in '{group_name}'")
        return True
    except Exception as e:
        print(f"Error sending welcome message: {e}")
        return False

def get_username_by_id(cl, user_id):
    try:
        user_info = cl.user_info(user_id)
        return user_info.username
    except Exception as e:
        print(f"Error getting username: {e}")
        return None

def change_group_name(cl, thread_id, new_name):
    try:
        heart = get_next_heart(thread_id)
        full_name = f"{new_name} {heart}"
        cl.direct_thread_update_title(int(thread_id), full_name)
        return full_name
    except Exception as e:
        print(f"Error changing group name: {e}")
        return None

def handle_command(cl, thread_id, message_text, sender_username, group_name, message_id=None):
    global bot_settings
    
    command_parts = message_text.strip().split(maxsplit=1)
    command = command_parts[0].lower()
    args_text = command_parts[1] if len(command_parts) > 1 else ""
    args = args_text.split() if args_text else []
    
    if not is_admin(sender_username):
        send_message(cl, thread_id, "ADMIN BOT HAI SIR 😒", reply_to=message_id)
        print(f"Non-admin @{sender_username} tried to use command: {command}")
        return
    
    print(f"Admin @{sender_username} used command: {command} in '{group_name}'")
    
    if command == "/help":
        help_text = "🤖 Bot Commands:\n\n"
        for cmd, desc in BOT_COMMANDS.items():
            help_text += f"{cmd} - {desc}\n"
        send_message(cl, thread_id, help_text, reply_to=message_id)
    
    elif command == "/ping":
        start_time = time.time()
        send_message(cl, thread_id, "🏓 Pong!", reply_to=message_id)
        latency = round((time.time() - start_time) * 1000)
        send_message(cl, thread_id, f"⚡ Latency: {latency}ms", reply_to=message_id)
    
    elif command == "/nc":
        if args_text:
            new_name = change_group_name(cl, thread_id, args_text)
            if new_name:
                send_message(cl, thread_id, f"✅ Group name changed to: {new_name}", reply_to=message_id)
            else:
                send_message(cl, thread_id, "❌ Failed to change group name", reply_to=message_id)
        else:
            send_message(cl, thread_id, "❌ Usage: /nc {new group name}", reply_to=message_id)
    
    elif command == "/send":
        if args_text:
            stop_flags[thread_id] = False
            bot_settings["sending"][thread_id] = True
            bot_settings["send_text"][thread_id] = args_text
            if thread_id in bombing_threads:
                del bombing_threads[thread_id]
            save_settings()
        else:
            send_message(cl, thread_id, "❌ Usage: /send {message}", reply_to=message_id)
    
    elif command == "/stop":
        stop_flags[thread_id] = True
        bot_settings["sending"][thread_id] = False
        if thread_id in bombing_threads:
            del bombing_threads[thread_id]
        save_settings()
        send_message(cl, thread_id, "⏹️", reply_to=message_id)
    
    elif command == "/threads":
        if args:
            try:
                count = int(args[0])
                if 1 <= count <= 100:
                    bot_settings["threads"] = count
                    save_settings()
                    send_message(cl, thread_id, f"✅ Threads: {count}", reply_to=message_id)
                else:
                    send_message(cl, thread_id, "❌ Threads must be between 1-100", reply_to=message_id)
            except ValueError:
                send_message(cl, thread_id, "❌ Usage: /threads {1-100}", reply_to=message_id)
        else:
            send_message(cl, thread_id, f"📊 Current threads: {bot_settings.get('threads', 1)}", reply_to=message_id)
    
    elif command == "/delay":
        if args:
            try:
                delay = float(args[0])
                if 0.5 <= delay <= 60:
                    bot_settings["delay"] = delay
                    save_settings()
                    send_message(cl, thread_id, f"✅ Delay set to: {delay}s", reply_to=message_id)
                else:
                    send_message(cl, thread_id, "❌ Delay must be between 0.5-60 seconds", reply_to=message_id)
            except ValueError:
                send_message(cl, thread_id, "❌ Usage: /delay {seconds}", reply_to=message_id)
        else:
            send_message(cl, thread_id, f"⏱️ Current delay: {bot_settings.get('delay', 2)}s", reply_to=message_id)
    
    elif command == "/settings":
        settings_text = f"""⚙️ Bot Settings:
        
📤 Threads: {bot_settings.get('threads', 1)}
⏱️ Delay: {bot_settings.get('delay', 2)}s
💬 Welcome: {WELCOME_MESSAGE}"""
        send_message(cl, thread_id, settings_text, reply_to=message_id)
    
    elif command == "/members":
        members = get_group_members(cl, thread_id)
        send_message(cl, thread_id, f"👥 Total members: {len(members)}", reply_to=message_id)
    
    elif command == "/admins":
        admin_list = ", ".join([f"@{admin}" for admin in ADMIN_USERNAMES])
        send_message(cl, thread_id, f"👑 Bot Admins: {admin_list}", reply_to=message_id)
    
    elif command == "/welcome":
        if args_text:
            send_message(cl, thread_id, f"✅ Welcome message updated to: {args_text}", reply_to=message_id)
        else:
            send_message(cl, thread_id, f"Current welcome message: {WELCOME_MESSAGE}", reply_to=message_id)
    
    elif command == "/kick":
        if args:
            target = args[0].replace("@", "")
            send_message(cl, thread_id, f"⚠️ Kick command received for @{target}", reply_to=message_id)
        else:
            send_message(cl, thread_id, "❌ Usage: /kick @username", reply_to=message_id)
    
    elif command == "/mute":
        send_message(cl, thread_id, "🔇 Group notifications muted", reply_to=message_id)
    
    elif command == "/unmute":
        send_message(cl, thread_id, "🔔 Group notifications unmuted", reply_to=message_id)
    
    else:
        send_message(cl, thread_id, f"❓ Unknown command: {command}\nType /help for available commands", reply_to=message_id)

def bomb_thread(cl, thread_id, text):
    global stop_flags
    delay = bot_settings.get("delay", 0)
    while not stop_flags.get(thread_id, False):
        try:
            cl.direct_send(text, thread_ids=[int(thread_id)])
            if delay > 0:
                time.sleep(delay)
        except:
            pass

def start_bombing(cl, thread_id, text):
    global bombing_threads
    thread_count = bot_settings.get("threads", 5)
    
    if thread_id in bombing_threads:
        for t in bombing_threads[thread_id]:
            if t.is_alive():
                return
    
    bombing_threads[thread_id] = []
    for i in range(thread_count):
        t = threading.Thread(target=bomb_thread, args=(cl, thread_id, text), daemon=True)
        t.start()
        bombing_threads[thread_id].append(t)
    print(f"Started {thread_count} bombing threads for {thread_id}")

def send_loop_messages(cl, groups):
    load_settings()
    for group in groups:
        thread_id = group['id']
        if bot_settings.get("sending", {}).get(thread_id, False):
            text = bot_settings.get("send_text", {}).get(thread_id, "")
            if text and thread_id not in bombing_threads:
                start_bombing(cl, thread_id, text)
        elif thread_id in bombing_threads:
            del bombing_threads[thread_id]

def process_messages(cl, groups, processed_messages):
    for group in groups:
        thread_id = group['id']
        group_name = group['name']
        
        messages, users_map = get_thread_with_users(cl, thread_id, amount=10)
        
        for message in messages:
            message_id = str(message.id)
            
            if message_id in processed_messages:
                continue
            
            if not hasattr(message, 'text') or not message.text:
                processed_messages.add(message_id)
                continue
            
            message_text = message.text.strip()
            
            if not message_text.startswith("/"):
                processed_messages.add(message_id)
                continue
            
            sender_id = str(message.user_id)
            sender_username = users_map.get(sender_id)
            
            if not sender_username:
                sender_username = get_username_by_id(cl, sender_id)
            
            if sender_username:
                handle_command(cl, thread_id, message_text, sender_username, group_name, message_id=message_id)
            
            processed_messages.add(message_id)
    
    return processed_messages

def run_bot():
    if not all([INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD]):
        print("Missing required environment variables!")
        print("Please set: INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD")
        return
    
    load_settings()
    
    print("=" * 50)
    print("Instagram Group Management Bot")
    print("=" * 50)
    print(f"Welcome message: {WELCOME_MESSAGE}")
    print(f"Admin users: {', '.join(['@' + admin for admin in ADMIN_USERNAMES])}")
    print(f"Threads: {bot_settings.get('threads', 1)} | Delay: {bot_settings.get('delay', 2)}s")
    print("This bot monitors ALL groups where you are a member")
    print("-" * 50)
    
    cl = login_client()
    known_members = load_known_members()
    processed_messages = load_processed_messages()
    
    print("\nScanning for group chats...")
    groups = get_all_group_threads(cl)
    print(f"Found {len(groups)} group(s):")
    for g in groups:
        print(f"  - {g['name']} (ID: {g['id']})")
    
    for group in groups:
        thread_id = group['id']
        if thread_id not in known_members:
            print(f"\nFirst time seeing '{group['name']}', loading members...")
            members = get_group_members(cl, thread_id)
            known_members[thread_id] = list(members)
            print(f"  Found {len(members)} existing members")
    
    save_known_members(known_members)
    
    print(f"\nBot is running! Checking all groups every {CHECK_INTERVAL} seconds...")
    print("-" * 50)
    
    while True:
        try:
            groups = get_all_group_threads(cl)
            
            send_loop_messages(cl, groups)
            
            processed_messages = process_messages(cl, groups, processed_messages)
            save_processed_messages(processed_messages)
            
            for group in groups:
                thread_id = group['id']
                group_name = group['name']
                
                current_members = get_group_members(cl, thread_id)
                
                if thread_id not in known_members:
                    known_members[thread_id] = list(current_members)
                    save_known_members(known_members)
                    print(f"New group detected: '{group_name}' with {len(current_members)} members")
                    continue
                
                known_set = set(known_members[thread_id])
                new_members = current_members - known_set
                
                if new_members:
                    print(f"\n{len(new_members)} new member(s) in '{group_name}'!")
                    for member_id in new_members:
                        username = get_username_by_id(cl, member_id)
                        if username:
                            send_welcome_message(cl, thread_id, username, group_name)
                            time.sleep(3)
                    
                    known_members[thread_id] = list(current_members)
                    save_known_members(known_members)
            
            time.sleep(CHECK_INTERVAL)
            
        except LoginRequired:
            print("Session expired, re-logging in...")
            cl = login_client()
        except KeyboardInterrupt:
            print("\nBot stopped by user")
            break
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(30)

if __name__ == "__main__":
    run_bot()
