import logging
import random
import json
import csv
import os
import datetime
# Removed sqlite3 import
import hashlib # Added for code generation
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes,
    MessageHandler, filters, ConversationHandler
)

TOKEN = "8057509848:AAHJsE1q63yn9OgBFftKiE8MUqOpidilBuw"

POSITIONS = ["1", "2", "3", "4", "5"]
COTES = ["1.23", "1.54"]
SIDES = ["Gauche", "Droite"]

# Removed DATABASE_FILE definition

# user_memory will hold all user data in memory
# Structure: { user_id: { "name": "", "username": "", "history": [] } }
# Each history entry is a dict like: {"type": "gagne" or "perdu", "cote": "1.23" or "1.54", "case": "1-5", "side": "Gauche" or "Droite", "side_ref": "gauche" or "droite", "resultat": "Bonne" or "Mauvaise", "date": "...", "heure": "...", "seconde": "...", "bet_amount": "..."}
user_memory = {}

ASK_RESULTS, ASK_CASES, ASK_SIDE, ASK_BONNE_MAUVAISE, ASK_1XBET_ID, RESET_CONFIRM, ASK_BET_AMOUNT, ASK_EXPORT_FORMAT = range(8)

# --- Security System Constants and Variables ---
ADMIN_USER_ID = "YOUR_ADMIN_TELEGRAM_ID" # <<< REPLACE with your Telegram User ID (as a string) - Get it from a bot like @userinfobot
SECRET_KEY = "YOUR_VERY_SECRET_KEY" # <<< REPLACE with a strong, unique secret key (random string of characters)
ACCESS_CODES_FILE = "access_codes.json"

# access_codes will store user IDs and their expiry times { user_id: datetime_object }
access_codes = {}

# Removed Database Initialization Function init_db()

# Removed save_data() and load_data() as database handles persistence

# --- Security System Functions ---
def load_access_codes():
    """Loads access codes from the JSON file."""
    global access_codes
    if os.path.exists(ACCESS_CODES_FILE):
        try:
            with open(ACCESS_CODES_FILE, "r", encoding="utf-8") as f:
                # Use object_hook to convert expiry strings back to datetime objects on load
                access_codes_raw = json.load(f)
                access_codes = {user_id: datetime.datetime.strptime(expiry_str, '%Y-%m-%d %H:%M:%S') for user_id, expiry_str in access_codes_raw.items()}
            logging.info(f"Loaded {len(access_codes)} access codes from {ACCESS_CODES_FILE}")
        except Exception as e:
            logging.error(f"Error loading access codes from {ACCESS_CODES_FILE}: {e}")
    else:
        logging.info(f"{ACCESS_CODES_FILE} not found. Starting with empty access codes.")

def save_access_codes():
    """Saves access codes to the JSON file."""
    try:
        # Convert datetime objects to strings for saving
        access_codes_raw = {user_id: expiry_dt.strftime('%Y-%m-%d %H:%M:%S') for user_id, expiry_dt in access_codes.items()}
        with open(ACCESS_CODES_FILE, "w", encoding="utf-8") as f:
            json.dump(access_codes_raw, f, ensure_ascii=False, indent=2)
        logging.info(f"Saved {len(access_codes)} access codes to {ACCESS_CODES_FILE}")
    except Exception as e:
        logging.error(f"Error saving access codes to {ACCESS_CODES_FILE}: {e}")

def generate_access_code(user_id):
    """Generates a unique access code based on user_id and secret_key."""
    # Ensure user_id is a string
    user_id_str = str(user_id)
    # Combine user ID and secret key
    data_to_hash = f"{user_id_str}{SECRET_KEY}"
    # Use SHA256 for hashing
    hashed_data = hashlib.sha256(data_to_hash.encode()).hexdigest()
    # Take the first 12 characters as the code (can adjust length as needed)
    access_code = hashed_data[:12]
    return access_code

def is_access_valid(user_id):
    """Checks if a user has a valid, non-expired access code."""
    user_id_str = str(user_id)
    # Also check if the user is the admin, admin always has access
    if user_id_str == ADMIN_USER_ID:
        return True

    if user_id_str in access_codes:
        expiry_dt = access_codes[user_id_str]
        # Check if the expiry date is in the future
        if expiry_dt > datetime.datetime.now():
            return True
        else:
            # Access expired, remove from memory and file
            del access_codes[user_id_str]
            save_access_codes()
            logging.info(f"Access expired for user {user_id_str}. Removed from memory and file.")
            return False
    return False # User ID not found in access codes

# --- Admin Command Handler ---
async def grant_access(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Grants access to a user for a specified duration."""
    user_id = str(update.effective_user.id)

    # Check if the user is the admin
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("🔒 You are not authorized to use this command.")
        return

    # Command format: /grant_access <target_user_id> <duration_days>
    if len(context.args) != 2:
        await update.message.reply_text("Usage: `/grant_access <user_id_to_grant_access> <duration_in_days>`", parse_mode="Markdown")
        return

    target_user_id_str = context.args[0].strip()
    duration_days_str = context.args[1].strip()

    # Validate target user ID
    if not target_user_id_str.isdigit():
        await update.message.reply_text("Invalid user ID. Please provide a numeric user ID.")
        return

    # Validate duration
    try:
        duration_days = int(duration_days_str)
        if duration_days <= 0:
            await update.message.reply_text("Duration must be a positive number of days.")
            return
    except ValueError:
        await update.message.reply_text("Invalid duration. Please provide a number of days.")
        return

    target_user_id = target_user_id_str
    expiry_date = datetime.datetime.now() + datetime.timedelta(days=duration_days)

    # Add/Update access in memory and save to file
    access_codes[target_user_id] = expiry_date
    save_access_codes()

    # Generate and provide the access code to the admin
    generated_code = generate_access_code(target_user_id)

    await update.message.reply_text(
        f"✅ Access granted for user `{target_user_id}` for {duration_days} days.\\n"
        f"Expiry: {expiry_date.strftime('%Y-%m-%d %H:%M:%S')}\\n"
        f"Generated Code for user `{target_user_id}`: `{generated_code}`\\n"
        "Please provide this code to the user.",
        parse_mode="Markdown"
    )

def get_rng(user_id_1xbet=None, bet_amount_for_rng=None):
    if user_id_1xbet or bet_amount_for_rng:
        now = datetime.datetime.now()
        now_str = now.strftime("%Y%m%d_%H%M%S_%f") # Add microseconds for more entropy
        seed = f"{user_id_1xbet}_{now_str}_{bet_amount_for_rng}" # Include bet_amount in the seed
        # Remove None parts from the seed string
        seed_parts = [part for part in seed.split('_') if part != 'None']
        seed = '_'.join(seed_parts)
        return random.Random(seed), seed
    else:
        return random.SystemRandom(), None

# get_user_history now reads from user_memory
def get_user_history(user_id):
    """Récupère l'historique d'un utilisateur depuis la mémoire."""
    return user_memory.get(user_id, {}).get("history", [])

# export_csv now reads from user_memory using get_user_history
async def export_csv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    # Collect data for the current user's history
    memory = get_user_history(user_id) # Use the in-memory function
    if not memory:
        await update.message.reply_text("Aucun historique à exporter.", reply_markup=get_main_menu())
        # Return ConversationHandler.END if called from conversation, or None otherwise
        return ConversationHandler.END if 'export_format_choice' in context.user_data else None

    rows = []
    # Get user's name and username from memory
    user_info = user_memory.get(user_id, {})
    user_name = user_info.get("name", "")
    user_username = user_info.get("username", "")

    for entry in memory:
        rows.append({
            "user_id": user_id,
            "name": user_name,
            "username": user_username,
            "type": entry.get("type", ""),
            "cote": entry.get("cote", ""),
            "case": entry.get("case", ""),
            "side": entry.get("side", ""),
            "side_ref": entry.get("side_ref", ""),
            "resultat": entry.get("resultat", ""),
            "date": entry.get("date", ""),
            "heure": entry.get("heure", ""),
            "seconde": entry.get("seconde", ""),
            "bet_amount": entry.get("bet_amount", "")
        })

    csv_filename = f"history_export_{user_id}.csv"
    try:
        with open(csv_filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["user_id", "name", "username", "type", "cote", "case", "side", "side_ref", "resultat", "date", "heure", "seconde", "bet_amount"])
            writer.writeheader()
            writer.writerows(rows)

        await update.message.reply_document(document=open(csv_filename, "rb"), filename=csv_filename)
        await update.message.reply_text("✅ Exportation CSV terminée !", reply_markup=get_main_menu())
    except Exception as e:
        logging.error(f"Error exporting CSV for user {user_id}: {e}")
        await update.message.reply_text("❌ Une erreur s'est produite lors de l'exportation CSV.", reply_markup=get_main_menu())
    finally:
         # Clean up the created file after sending
        try:
            if os.path.exists(csv_filename):
                os.remove(csv_filename)
        except OSError as e:
            logging.error(f"Error removing file {csv_filename}: {e}")
    return ConversationHandler.END

def get_main_menu():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("🍏 Prédire"), KeyboardButton("ℹ️ Fonctionnement")],
            [KeyboardButton("🎯 Conseils"), KeyboardButton("🚨 Arnaques")],
            [KeyboardButton("❓ FAQ"), KeyboardButton("📞 Contact")],
            [KeyboardButton("📝 Tutoriel"), KeyboardButton("ℹ️ À propos")],
            [KeyboardButton("🧠 Historique"), KeyboardButton("📊 Statistiques")],
            [KeyboardButton("📤 Exporter"), KeyboardButton("📥 Importer")],
            [KeyboardButton("♻️ Réinitialiser historique")]
        ],
        resize_keyboard=True
    )

def contains_scam_words(txt):
    mots_suspects = [
        "hack", "triche", "cheat", "bot miracle", "code promo", "astuce", "secret", "gagner sûr", "prédiction sûre",
        "script", "seed", "crack", "pirater", "mod", "prédire sûr", "bug", "exploit", "tricher", "logiciel"
    ]
    for mot in mots_suspects:
        if mot in txt.lower():
            return True
    return False

def current_time_data():
    now = datetime.datetime.now()
    return {
        "date": now.strftime("%d/%m"),
        "heure": now.strftime("%H:%M"),
        "seconde": now.strftime("%S")
    }

# start function now interacts with user_memory
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    first_name = update.effective_user.first_name or ""
    last_name = update.effective_user.last_name or ""
    username = update.effective_user.username or ""
    full_name = f"{first_name} {last_name}".strip()

    # Initialize user data in memory if not exists
    if user_id not in user_memory:
        user_memory[user_id] = {"name": full_name, "username": username, "history": []}
        logging.info(f"New user added to memory: {user_id}")
    else:
        # Update user info in memory (name, username might change)
        user_memory[user_id]["name"] = full_name
        user_memory[user_id]["username"] = username
        logging.info(f"User info updated in memory: {user_id}")

    await update.message.reply_text(
        "🍏 Bienvenue sur Apple Predictor Bot !\n"
        "Ce bot simule le fonctionnement du jeu Apple of Fortune sur 1xbet : à chaque niveau, une case gagnante aléatoire (aucune astuce possible).\n"
        "Nouveau : Précision sur le comptage des cases : pour chaque prédiction, tu sauras s'il faut compter depuis la gauche ou la droite !\n"
        "Tu peux suivre tes statistiques, enregistrer tes parties, profiter de conseils pour jouer responsable, et importer/exporter ton historique.\n\n"
        "Menu ci-dessous 👇",
        reply_markup=get_main_menu()
    )

async def fonctionnement(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🍏 Fonctionnement Apple of Fortune (1xbet, cotes 1.23 et 1.54) 🍏\n\n"
        "Le jeu utilise un algorithme appelé RNG (Random Number Generator), qui choisit la case gagnante totalement au hasard à chaque niveau. "
        "Il est donc impossible de prédire ou d'influencer le résultat, chaque case a 20% de chance d'être gagnante.\n\n"
        "Notre bot applique le même principe : pour chaque prédiction, la case est tirée au sort grâce à un RNG sécurisé, exactement comme sur 1xbet. "
        "Si tu veux, tu peux fournir ton ID utilisateur 1xbet pour obtenir une simulation personnalisée (la même suite de cases pour ce seed, basé sur ton ID, la date et l'heure)."
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def conseils(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🎯 Conseils de jeu responsable sur 1xbet :\n\n"
        "- Fixe-toi une limite de pertes.\n"
        "- Ne mise jamais l'argent que tu ne peux pas perdre.\n"
        "- Le jeu est 100% hasard, chaque case a autant de chances d'être gagnante.\n"
        "- Prends du recul après une série de jeux."
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def arnaques(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🚨 Attention aux arnaques sur 1xbet !\n\n"
        "Aucune application, bot, code promo ou script ne peut prédire la bonne case.\n"
        "Ceux qui promettent le contraire veulent te tromper ou te faire perdre de l'argent.\n"
        "Ne partage jamais tes identifiants 1xbet."
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "📞 Contact & Aide :\n"
        "• WhatsApp : [wa.me/+2250501945735](https://wa.me/+2250501945735)\n"
        "• Téléphone 1 : 0500448208\n"
        "• Téléphone 2 : 0501945735\n"
        "• Telegram : [@Roidesombres225](https://t.me/Roidesombres225)\n"
        "N'hésite pas à me contacter pour toute question ou aide !"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def faq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "❓ FAQ Apple of Fortune (1xbet, cotes 1.23 et 1.54)\n\n"
        "- Peut-on prédire la bonne case ? Non, c'est impossible, chaque case a 20% de chance.\n"
        "- Un code promo change-t-il le hasard ? Non.\n"
        "- Le bot donne des suggestions purement aléatoires, comme sur 1xbet.\n"
        "- Le bot précise maintenant le sens de comptage des cases pour éviter toute erreur."
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def tuto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📝 Tutoriel rapide\n\n"
        "- Clique sur 🍏 Prédire pour obtenir les cases suggérées (1.23 puis 1.54).\n"
        "- Le bot t'indique non seulement la case, mais aussi s'il faut compter depuis la gauche ou la droite.\n"
        "- Joue ces cases sur le site 1xbet. Indique si tu as joué à gauche ou à droite de la case, puis si tu as eu 'Bonne' ou 'Mauvaise' pour chaque cote.\n"
        "- Consulte ton historique et tes statistiques pour progresser.\n"
        "- Tu peux aussi exporter/importer ton historique via le menu."
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def apropos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "ℹ️ À propos\n"
        "Bot éducatif créé par SOLITAIRE HACK, adapté pour 1xbet (cotes 1.23 et 1.54 uniquement, précision sur le sens de comptage des cases)."
    )
    await update.message.reply_text(text, parse_mode="Markdown")

# stats_perso now reads from user_memory
async def stats_perso(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    # Check for valid access
    if not is_access_valid(user_id):
        await update.message.reply_text("🔒 You need a valid access code to view statistics.")
        return ConversationHandler.END # End conversation if access is invalid

    memory = get_user_history(user_id) # Use the in-memory function

    # Count total sequences (pairs of cote 1.23 and 1.54 entries)
    total_entries = len(memory)
    total_sequences = total_entries // 2 # Assuming history is saved in pairs

    if total_sequences == 0:
         await update.message.reply_text("Aucune statistique disponible pour l'instant, joue une séquence pour commencer.", reply_markup=get_main_menu())
         return

    victoire_123 = 0
    defaites_123 = 0
    victoire_154 = 0
    defaites_154 = 0

    for entry in memory:
        cote = entry.get("cote")
        resultat = entry.get("resultat")
        if resultat in ["Bonne", "Mauvaise"]:
            if cote == "1.23":
                if resultat == "Bonne":
                    victoire_123 += 1
                elif resultat == "Mauvaise":
                    defaites_123 += 1
            elif cote == "1.54":
                if resultat == "Bonne":
                    victoire_154 += 1
                elif resultat == "Mauvaise":
                    defaites_154 += 1

    # Calculate win rates
    taux_123 = round((victoire_123 / (victoire_123 + defaites_123)) * 100, 1) if (victoire_123 + defaites_123) > 0 else 0
    taux_154 = round((victoire_154 / (victoire_154 + defaites_154)) * 100, 1) if (victoire_154 + defaites_154) > 0 else 0

    txt = (
        f"📊 Tes statistiques\n"
        f"- Séquences jouées : {total_sequences}\n"
        f"- Victoires cote 1.23 : {victoire_123} | Défaites : {defaites_123} | Taux : {taux_123}%\n"
        f"- Victoires cote 1.54 : {victoire_154} | Défaites : {defaites_154} | Taux : {taux_154}%\n"
    )
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=get_main_menu())


# historique now reads from user_memory
async def historique(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    # Check for valid access
    if not is_access_valid(user_id):
        await update.message.reply_text("🔒 You need a valid access code to view history.")
        return ConversationHandler.END # End conversation if access is invalid

    memory = get_user_history(user_id) # Use the in-memory function
    if not memory:
        await update.message.reply_text(
            "Aucun historique enregistré pour l'instant.",
            reply_markup=get_main_menu()
        )
        return

    # Regroupe par séquence de 2 (1.23 puis 1.54)
    sequences = []
    # Process history entries in pairs as before
    for i in range(0, len(memory), 2):
        try:
            a = memory[i]
            b = memory[i+1]
        except IndexError:
            continue # Skip incomplete pairs

        date = a.get("date", "-")
        heure = a.get("heure", "-")
        sec = a.get("seconde", "-")
        bet_amount = a.get("bet_amount", "-")
        case123 = a.get("case", "?")
        sens123 = a.get("side", "?")
        res123 = a.get("resultat", "?")
        case154 = b.get("case", "?")
        sens154 = b.get("side", "?")
        res154 = b.get("resultat", "?")
        # Determine overall result based on the type saved for the 1.23 entry (or first entry)
        etat = "🏆" if a.get("type") == "gagne" else "💥"
        seq = (
            f"📅 {date} à {heure}:{sec} | Mise : {bet_amount}\n"
            f"1️⃣ Cote 1.23 : Case {case123} ({sens123}) — {res123}\n"
            f"2️⃣ Cote 1.54 : Case {case154} ({sens154}) — {res154}\n"
            f"Résultat : {etat}\n"
            f"--------------------"
        )
        sequences.append(seq)

    # On affiche les 15 dernières séquences
    msg = "🧠 Historique de tes 15 dernières séquences :\n\n" + "\n".join(sequences[-15:])
    await update.message.reply_text(
        msg,
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(
            [
                [KeyboardButton("♻️ Réinitialiser historique")],
                [KeyboardButton("⬅️ Menu principal")]
            ],
            resize_keyboard=True
        )
    )

async def reset_historique(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    # Check for valid access
    if not is_access_valid(user_id):
        await update.message.reply_text("🔒 You need a valid access code to reset history.")
        return ConversationHandler.END # End conversation if access is invalid

    await update.message.reply_text(
        "⚠️ Veux-tu vraiment supprimer tout ton historique ?\nRéponds OUI pour confirmer, NON pour annuler.",
        reply_markup=ReplyKeyboardMarkup([["OUI", "NON"]], resize_keyboard=True)
    )
    context.user_data["awaiting_reset"] = True
    return RESET_CONFIRM

# handle_reset_confirm now interacts with user_memory
async def handle_reset_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("awaiting_reset"):
        if update.message.text.strip().upper() == "OUI":
            user_id = str(update.effective_user.id)
            if user_id in user_memory:
                user_memory[user_id]["history"] = [] # Clear history
                logging.info(f"History reset in memory for user {user_id}")

            context.user_data["awaiting_reset"] = False
            await update.message.reply_text("✅ Ton historique a été réinitialisé.", reply_markup=get_main_menu())
            return ConversationHandler.END
        else:
            context.user_data["awaiting_reset"] = False
            await update.message.reply_text("❌ Réinitialisation annulée.", reply_markup=get_main_menu())
            return ConversationHandler.END
    # If not awaiting reset, this message was not part of the confirmation flow
    return ConversationHandler.END # Fallback to end conversation if state is wrong

async def predire_auto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    # Check for valid access
    if not is_access_valid(user_id):
        await update.message.reply_text("🔒 You need a valid access code to get predictions.")
        return ConversationHandler.END # End conversation if access is invalid

    if "id_1xbet" not in context.user_data:
        await update.message.reply_text(
            "Pour une simulation personnalisée, entre ton ID utilisateur 1xbet, puis clique sur OK pour confirmer (ou NON pour une simulation totalement aléatoire).",
            reply_markup=ReplyKeyboardMarkup(
                [[KeyboardButton("OK")], [KeyboardButton("NON")]],
                resize_keyboard=True
            )
        )
        context.user_data["awaiting_id"] = True
        context.user_data["temp_id"] = ""
        return ASK_1XBET_ID

    # Assume id_1xbet is already in context.user_data if we reach here without awaiting_id
    user_id_1xbet = context.user_data.get("id_1xbet")
    # Bet amount is now collected *before* predictions are made, so it should be in user_data
    bet_amount_for_rng = context.user_data.get("bet_amount")

    # If bet_amount is not set yet, ask for it
    if bet_amount_for_rng is None:
         await update.message.reply_text(
            "Entre le montant de ton pari (ex: 100, 50.5) :",
            reply_markup=ReplyKeyboardMarkup([["200", "300", "400"], ["500", "750", "1000"]], resize_keyboard=True)
        )
         return ASK_BET_AMOUNT # Go to the state to collect bet amount

    # If both are available, proceed with predictions
    rng, seed_str = get_rng(user_id_1xbet, bet_amount_for_rng)
    context.user_data["auto_preds"] = []
    pred_msgs = []
    sides_ref = ["gauche", "droite"]

    seed_logs = []
    # Log seed if a specific one was used (i.e., if ID or amount was provided)
    if user_id_1xbet is not None or bet_amount_for_rng is not None:
         seed_logs.append(f"🧮 Logs de calcul du seed :")
         seed_logs.append(f"Seed utilisé : `{seed_str}`")
         # Construct the random.Random call string based on what was used for seeding
         seed_components = []
         if user_id_1xbet:
             seed_components.append(f'"{user_id_1xbet}"')
         # Use bet_amount_for_rng directly as it's already validated and stored
         if bet_amount_for_rng is not None:
             seed_components.append(f'"{bet_amount_for_rng}"')
         # Add time component if either ID or bet amount was provided
         if user_id_1xbet is not None or bet_amount_for_rng is not None:
              now = datetime.datetime.now()
              now_str_log = now.strftime("%Y%m%d_%H%M%S_%f")
              seed_components.append(f'"{now_str_log}"')

         # Reconstruct the seed string as used in get_rng for logging
         log_seed = "_".join(c.strip("'\"") for c in seed_components) # Remove quotes for display
         seed_logs.append(f'random = random.Random("{log_seed}")')


    for i, cote in enumerate(COTES):
        tirage_case = rng.choice([1, 2, 3, 4, 5])
        tirage_sens = rng.choice(sides_ref)
        case = str(tirage_case)
        side_ref = tirage_sens
        context.user_data["auto_preds"].append({"cote": cote, "case": case, "side_ref": side_ref})
        pred_msgs.append(
            f"Prédiction cote {cote} : sélectionne la case {case} (en comptant depuis la {side_ref})"
        )
        # Log internal RNG calls only if a seeded RNG was used
        if user_id_1xbet is not None or bet_amount_for_rng is not None:
              seed_logs.append(
                f"Prédiction {i+1} (cote {cote}) :\n"
                f"    Tirage case : {case}   (random.choice([1,2,3,4,5]))\n"
                f"    Tirage sens : {side_ref}   (random.choice([\"gauche\",\"droite\"]))"
            )


    if user_id_1xbet is not None or bet_amount_for_rng is not None:
        await update.message.reply_text(
            "\n".join(seed_logs),
            parse_mode="Markdown"
        )
        await update.message.reply_text(
            "Voici la séquence calculée pour ce seed :\n" + "\n".join(pred_msgs),
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "🍏 Séquence automatique (simulation 1xbet)\n\n" + "\n".join(pred_msgs),
            parse_mode="Markdown",
        )
    await update.message.reply_text(
        "\nAprès avoir joué sur 1xbet, indique si tu as GAGNÉ ou PERDU la séquence (gagné si tu as eu 'Bonne' pour les 2 cotes, sinon perdu).",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton("🏆 Gagné"), KeyboardButton("💥 Perdu")]],
            resize_keyboard=True)
    )
    context.user_data["side_refs"] = [d["side_ref"] for d in context.user_data["auto_preds"]]
    return ASK_RESULTS


async def ask_1xbet_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.upper() == "NON":
        context.user_data["id_1xbet"] = None
        context.user_data.pop("awaiting_id", None)
        context.user_data.pop("temp_id", None)
        # Now ask for the bet amount
        await update.message.reply_text(
            "Entre le montant de ton pari (ex: 100, 50.5) :",
            reply_markup=ReplyKeyboardMarkup([["200", "300", "400"], ["500", "750", "1000"]], resize_keyboard=True)
        )
        return ASK_BET_AMOUNT
    elif text.upper() == "OK":
        user_id_input = context.user_data.get("temp_id", "").strip()
        # Re-validate ID on OK click just in case
        if not user_id_input.isdigit() or len(user_id_input) != 10:
             await update.message.reply_text(
                "L'ID utilisateur 1xbet doit être composé de 10 chiffres. Merci de réessayer ou de taper NON pour annuler."
            )
             # Stay in the same state
             context.user_data["temp_id"] = "" # Clear temp_id as it was invalid
             return ASK_1XBET_ID

        context.user_data["id_1xbet"] = user_id_input
        context.user_data.pop("awaiting_id", None)
        context.user_data.pop("temp_id", None)
        # Now ask for the bet amount
        await update.message.reply_text(
            "Entre le montant de ton pari (ex: 100, 50.5) :",
            reply_markup=ReplyKeyboardMarkup([["200", "300", "400"], ["500", "750", "1000"]], resize_keyboard=True)
        )
        return ASK_BET_AMOUNT
    else:
        # Add validation for 10 digits
        if not text.isdigit() or len(text) != 10:
            await update.message.reply_text(
                "L'ID utilisateur 1xbet doit être composé de 10 chiffres. Merci de réessayer ou de taper NON pour annuler."
            )
            # Stay in the same state, waiting for correct input
            context.user_data["temp_id"] = "" # Clear temp_id as it was invalid
            return ASK_1XBET_ID
        else:
            context.user_data["temp_id"] = text
            await update.message.reply_text(
                f"ID entré : {text}\nClique sur OK pour confirmer ou NON pour annuler.",
                reply_markup=ReplyKeyboardMarkup(
                    [[KeyboardButton("OK")], [KeyboardButton("NON")]],
                    resize_keyboard=True
                )
            )
            # Stay in the same state, waiting for OK or NON
            return ASK_1XBET_ID


async def after_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result_text = update.message.text.lower()
    if "gagné" in result_text or "gagne" in result_text:
        context.user_data['auto_result'] = "gagne"
    elif "perdu" in result_text:
        context.user_data['auto_result'] = "perdu"
    else:
        await update.message.reply_text("Merci de choisir 'Gagné' ou 'Perdu'.")
        return ASK_RESULTS

    context.user_data["auto_case_details"] = []
    context.user_data["auto_case_step"] = 0
    # Start collecting details for the first cote (COTES[0])
    await update.message.reply_text(
        f"Pour la cote {COTES[0]}, sur quelle case étais-tu ? (1, 2, 3, 4 ou 5)",
        reply_markup=ReplyKeyboardMarkup([[KeyboardButton(c) for c in POSITIONS]], resize_keyboard=True)
    )
    return ASK_CASES

async def collect_case(update: Update, context: ContextTypes.DEFAULT_TYPE):
    case = update.message.text.strip()
    if case not in POSITIONS:
        await update.message.reply_text("Merci d'entrer un numéro de case valide : 1, 2, 3, 4 ou 5.")
        return ASK_CASES

    step = context.user_data.get("auto_case_step", 0)
    # Ensure side_refs exists and has enough elements
    side_ref = context.user_data.get("side_refs", [])[step] if step < len(context.user_data.get("side_refs", [])) else "?"
    context.user_data["auto_case_details"].append({"cote": COTES[step], "case": case, "side_ref": side_ref}) # Store cote here
    context.user_data["auto_case_step"] = step + 1
    await update.message.reply_text(
        f"As-tu joué à GAUCHE ou à DROITE de la case {case} pour la cote {COTES[step]} (prédiction à compter depuis la {side_ref}) ?",
        reply_markup=ReplyKeyboardMarkup([[KeyboardButton("Gauche"), KeyboardButton("Droite")]], resize_keyboard=True)
    )
    return ASK_SIDE

async def collect_side(update: Update, context: ContextTypes.DEFAULT_TYPE):
    side = update.message.text.strip().capitalize()
    if side not in SIDES:
        await update.message.reply_text("Merci de répondre par 'Gauche' ou 'Droite'.")
        return ASK_SIDE

    step = context.user_data.get("auto_case_step", 1) # Should be step after collecting case, so index is step-1
    if step > 0 and step-1 < len(context.user_data.get("auto_case_details", [])):
        context.user_data["auto_case_details"][step-1]["side"] = side
        # Now ask Bonne/Mauvaise for this cote
        await update.message.reply_text(
            f"La case {context.user_data['auto_case_details'][step-1]['case']} ({side}) pour la cote {COTES[step-1]}, était-elle Bonne ou Mauvaise ?",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("Bonne"), KeyboardButton("Mauvaise")]], resize_keyboard=True)
        )
        return ASK_BONNE_MAUVAISE
    else:
        # Should not happen if conversation flow is correct
        logging.error("Error in collect_side: auto_case_step out of bounds or auto_case_details missing.")
        await update.message.reply_text("Une erreur interne s'est produite. Veuillez réessayer en cliquant sur '🍏 Prédire'.", reply_markup=get_main_menu())
        return ConversationHandler.END


# collect_bonne_mauvaise now saves to user_memory
async def collect_bonne_mauvaise(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reponse = update.message.text.strip().lower()
    if reponse not in ["bonne", "mauvaise"]:
        await update.message.reply_text("Merci de répondre par 'Bonne' ou 'Mauvaise'.")
        return ASK_BONNE_MAUVAISE

    step = context.user_data.get("auto_case_step", 1) # Should be step after collecting side, so index is step-1
    if step > 0 and step-1 < len(context.user_data.get("auto_case_details", [])):
        context.user_data["auto_case_details"][step-1]["resultat"] = reponse.capitalize()
    else:
         logging.error("Error in collect_bonne_mauvaise: auto_case_step out of bounds or auto_case_details missing.")
         await update.message.reply_text("Une erreur interne s'est produite. Veuillez réessayer en cliquant sur '🍏 Prédire'.", reply_markup=get_main_menu())
         # Clean up user_data for prediction flow
         context.user_data.pop("id_1xbet", None)
         context.user_data.pop("bet_amount", None)
         context.user_data.pop("auto_preds", None)
         context.user_data.pop("side_refs", None)
         context.user_data.pop("auto_case_details", None)
         context.user_data.pop("auto_case_step", None)
         context.user_data.pop("auto_result", None)
         return ConversationHandler.END


    # Check if we need details for the next cote
    if step < len(COTES):
        # Ask for case for the next cote
        await update.message.reply_text(
            f"Pour la cote {COTES[step]}, sur quelle case étais-tu ? (1, 2, 3, 4 ou 5)",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton(c) for c in POSITIONS]], resize_keyboard=True)
        )
        return ASK_CASES # Go back to asking for case

    # If all cote details are collected, save to user_memory and finish
    user_id = str(update.effective_user.id)
    result_type = context.user_data.get('auto_result')
    timeinfo = current_time_data()
    bet_amount = context.user_data.get("bet_amount", "-")

    # Ensure user exists in memory
    if user_id not in user_memory:
         user_memory[user_id] = {"name": "", "username": "", "history": []} # Initialize if somehow missing

    for detail in context.user_data.get("auto_case_details", []):
         history_entry = {
            "type": result_type,
            "cote": detail.get("cote", "-"),
            "case": detail.get("case", "-"),
            "side": detail.get("side", "-"),
            "side_ref": detail.get("side_ref", "-"),
            "resultat": detail.get("resultat", "-"),
            "date": timeinfo["date"],
            "heure": timeinfo["heure"],
            "seconde": timeinfo["seconde"],
            "bet_amount": bet_amount
        }
         user_memory[user_id]["history"].append(history_entry) # Append to the list in memory

    logging.info(f"Sequence saved to memory for user {user_id}")

    await update.message.reply_text(
        f"{'✅' if result_type == 'gagne' else '❌'} Séquence enregistrée !",
        reply_markup=get_main_menu()
    )

    # Clean up user_data for prediction flow
    # Do NOT remove id_1xbet here, it should persist
    # context.user_data.pop("id_1xbet", None) # Keep ID for future predictions
    context.user_data.pop("bet_amount", None)
    context.user_data.pop("auto_preds", None)
    context.user_data.pop("side_refs", None)
    context.user_data.pop("auto_case_details", None)
    context.user_data.pop("auto_case_step", None)
    context.user_data.pop("auto_result", None)

    return ConversationHandler.END


# export_txt now reads from user_memory using get_user_history
async def export_txt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    memory = get_user_history(user_id) # Use the in-memory function
    if not memory:
        await update.message.reply_text("Aucun historique à exporter.", reply_markup=get_main_menu())
        # Return ConversationHandler.END if called from conversation, or None otherwise
        return ConversationHandler.END if 'export_format_choice' in context.user_data else None

    sequences = []
    # Process history entries in pairs
    for i in range(0, len(memory), 2):
        try:
            a = memory[i]
            b = memory[i+1]
        except IndexError:
            continue # Skip incomplete pairs

        date = a.get("date", "-")
        heure = a.get("heure", "-")
        sec = a.get("seconde", "-")
        bet_amount = a.get("bet_amount", "-")
        case123 = a.get("case", "?")
        sens123 = a.get("side", "?")
        res123 = a.get("resultat", "?")
        case154 = b.get("case", "?")
        sens154 = b.get("side", "?")
        res154 = b.get("resultat", "?")
         # Determine overall result based on the type saved for the 1.23 entry (or first entry)
        etat = "🏆" if a.get("type") == "gagne" else "💥"
        seq = (
            f"📅 {date} à {heure}:{sec} | Mise : {bet_amount}\n"
            f"1️⃣ Cote 1.23 : Case {case123} ({sens123}) — {res123}\n"
            f"2️⃣ Cote 1.54 : Case {case154} ({sens154}) — {res154}\n"
            f"Résultat : {etat}\n"
            f"--------------------"
        )
        sequences.append(seq)

    txt_content = "\n".join(sequences[-100:])  # Limit to last 100 sequences
    txt_filename = f"history_export_{user_id}.txt" # Make filename unique per user
    try:
        with open(txt_filename, "w", encoding="utf-8") as f:
            f.write(txt_content)

        await update.message.reply_document(document=open(txt_filename, "rb"), filename=txt_filename)
        await update.message.reply_text("✅ Exportation TXT terminée !", reply_markup=get_main_menu())
    except Exception as e:
        logging.error(f"Error exporting TXT for user {user_id}: {e}")
        await update.message.reply_text("❌ Une erreur s'est produite lors de l'exportation TXT.", reply_markup=get_main_menu())
    finally:
        # Clean up the created file after sending
        try:
            if os.path.exists(txt_filename):
                os.remove(txt_filename)
        except OSError as e:
            logging.error(f"Error removing file {txt_filename}: {e}")
    return ConversationHandler.END

async def collect_bet_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bet_amount_str = update.message.text.strip()
    try:
        bet_amount_float = float(bet_amount_str)
        if bet_amount_float <= 0:
             await update.message.reply_text("Merci d'entrer un montant de pari positif.")
             return ASK_BET_AMOUNT
        # Store as string for consistent seed generation
        context.user_data["bet_amount"] = bet_amount_str
    except ValueError:
        await update.message.reply_text("Montant invalide. Merci d'entrer un nombre valide (ex: 100, 50.5).")
        return ASK_BET_AMOUNT

    # Now that we have ID (or None) and bet amount, proceed to generate predictions
    # Call predire_auto which now expects bet_amount to be in context.user_data
    return await predire_auto(update, context)


async def ask_export_format(update: Update, context: ContextTypes.DEFAULT_TYPE):
     user_id = str(update.effective_user.id)
     # Check for valid access
     if not is_access_valid(user_id):
         await update.message.reply_text("🔒 You need a valid access code to export data.")
         return ConversationHandler.END # End export conversation if no history

     memory = get_user_history(user_id)
     if not memory:
         await update.message.reply_text("Aucun historique à exporter.", reply_markup=get_main_menu())
         return ConversationHandler.END # End export conversation if no history

     await update.message.reply_text(
        "Quel format souhaites-tu pour l'exportation ?",
        reply_markup=ReplyKeyboardMarkup([["JSON", "CSV", "TXT"], ["⬅️ Menu principal"]], resize_keyboard=True)
    )
     return ASK_EXPORT_FORMAT

async def handle_export_format_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.message.text.strip().upper()
    user_id = str(update.effective_user.id)
    # Re-check for history, though check is also in ask_export_format and export functions
    memory = get_user_history(user_id)
    if not memory and choice != "⬅️ MENU PRINCIPAL":
         await update.message.reply_text("Aucun historique à exporter.", reply_markup=get_main_menu())
         return ConversationHandler.END

    if choice == "JSON":
        return await export_json(update, context) # Return result of the function
    elif choice == "CSV":
        return await export_csv(update, context) # Return result of the function
    elif choice == "TXT":
        return await export_txt(update, context) # Return result of the function
    elif choice == "⬅️ MENU PRINCIPAL":
        await update.message.reply_text("Opération annulée.", reply_markup=get_main_menu())
        # Clean up context data related to export choice if any
        context.user_data.pop('export_format_choice', None)
        return ConversationHandler.END
    else:
        await update.message.reply_text("Format inconnu. Choisis entre JSON, CSV ou TXT.", reply_markup=ReplyKeyboardMarkup([["JSON", "CSV", "TXT"], ["⬅️ Menu principal"]], resize_keyboard=True))
        return ASK_EXPORT_FORMAT # Stay in the same state

# export_json now reads from user_memory
async def export_json(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    memory = get_user_history(user_id) # Use the in-memory function

    if not memory:
        await update.message.reply_text("Aucun historique à exporter.", reply_markup=get_main_menu())
        # Return ConversationHandler.END if called from conversation, or None otherwise
        return ConversationHandler.END if 'export_format_choice' in context.user_data else None

    # Get user info from memory
    user_info = user_memory.get(user_id, {})

    # Structure data similar to old user_memory[user_id]
    user_history_data = {
        user_id: {
            "name": user_info.get("name", ""),
            "username": user_info.get("username", ""),
            "history": memory # The list of history entry dicts from get_user_history
        }
    }

    json_filename = f"history_export_{user_id}.json" # Make filename unique per user
    try:
        with open(json_filename, "w", encoding="utf-8") as f:
            json.dump(user_history_data, f, ensure_ascii=False, indent=2)

        await update.message.reply_document(document=open(json_filename, "rb"), filename=json_filename)
        await update.message.reply_text("✅ Exportation JSON terminée !", reply_markup=get_main_menu())
    except Exception as e:
        logging.error(f"Error exporting JSON for user {user_id}: {e}")
        await update.message.reply_text("❌ Une erreur s'est produite lors de l'exportation JSON.", reply_markup=get_main_menu())
    finally:
        # Clean up the created file after sending
        try:
            if os.path.exists(json_filename):
                os.remove(json_filename)
        except OSError as e:
            logging.error(f"Error removing file {json_filename}: {e}")
    return ConversationHandler.END

# import_data handles receiving the file and asking for confirmation
async def import_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id) # User who is importing
    # Check for valid access
    if not is_access_valid(user_id):
        await update.message.reply_text("🔒 You need a valid access code to import data.")
        return ConversationHandler.END # End conversation if access is invalid

    if update.message.document:
        file = await update.message.document.get_file()
        filename = update.message.document.file_name

        imported_data = None # Will store the parsed data
        import_successful = False

        if filename.endswith(".json"):
            try:
                content = await file.download_as_bytearray()
                data = json.loads(content.decode("utf-8"))
                # Expecting data format like { "user_id": { "name": ..., "username": ..., "history": [...] } }
                # We will take the first user's data found in the JSON
                if data and isinstance(data, dict):
                     # Find the first user ID in the imported JSON
                     imported_user_ids = list(data.keys())
                     if imported_user_ids:
                         first_imported_user_id = imported_user_ids[0]
                         imported_user_data = data[first_imported_user_id]
                         if isinstance(imported_user_data, dict) and "history" in imported_user_data and isinstance(imported_user_data["history"], list):
                              # Map imported data to the current user's ID
                              imported_data = {
                                  user_id: {
                                       "name": imported_user_data.get("name", ""),
                                       "username": imported_user_data.get("username", ""),
                                       "history": imported_user_data["history"]
                                  }
                              }
                              import_successful = True
                              await update.message.reply_text(
                                  "⚠️ Tu es sur le point d'importer des données JSON. "
                                  "Ceci remplacera TOUT ton historique actuel en mémoire.\n" # Updated message
                                  "Réponds OUI pour confirmer, NON pour annuler.",
                                  reply_markup=ReplyKeyboardMarkup([["OUI", "NON"]], resize_keyboard=True)
                              )
                         else:
                              await update.message.reply_text("Le format du fichier JSON semble incorrect.", reply_markup=get_main_menu())
                     else:
                          await update.message.reply_text("Aucune donnée utilisateur trouvée dans le fichier JSON.", reply_markup=get_main_menu())
                else:
                     await update.message.reply_text("Le format du fichier JSON semble incorrect.", reply_markup=get_main_menu())
            except Exception as e:
                logging.error(f"Error importing JSON for user {user_id}: {e}")
                await update.message.reply_text(f"Erreur lors de l'import JSON : {e}", reply_markup=get_main_menu())

        elif filename.endswith(".csv"):
            try:
                content = await file.download_as_bytearray()
                import io
                # Use DictReader for easier access by column name
                reader = csv.DictReader(io.StringIO(content.decode("utf-8")))
                # Check for required columns
                required_csv_fields = ["user_id", "type", "cote", "case", "side", "side_ref", "resultat", "date", "heure", "seconde", "bet_amount"]
                if not all(field in reader.fieldnames for field in required_csv_fields):
                    await update.message.reply_text(f"Le fichier CSV doit contenir les colonnes suivantes : {', '.join(required_csv_fields)}.", reply_markup=get_main_menu())
                    return # Exit function if fields are missing

                imported_history = []
                imported_user_info = {"name": "", "username": ""} # Attempt to get user info from the first row if available
                first_row_processed = False

                for row in reader:
                     # Assuming all rows belong to the user who is importing,
                     # but we'll keep the structure compatible by reading from the row
                     # However, we will link the imported history to the *current* user_id in memory
                     # and potentially update their name/username based on the first row.

                     # Only get user info from the first row
                     if not first_row_processed:
                          imported_user_info["name"] = row.get("name", "")
                          imported_user_info["username"] = row.get("username", "")
                          first_row_processed = True

                     imported_history.append({
                         "type": row.get("type", ""),
                         "cote": row.get("cote", ""),
                         "case": row.get("case", ""), # Use "case" key for compatibility
                         "side": row.get("side", ""),
                         "side_ref": row.get("side_ref", ""),
                         "resultat": row.get("resultat", ""),
                         "date": row.get("date", ""),
                         "heure": row.get("heure", ""),
                         "seconde": row.get("seconde", ""),
                         "bet_amount": row.get("bet_amount", "")
                     })

                if imported_history:
                    # Store data mapped to the *current* user_id
                    imported_data = {
                        user_id: {
                            "name": imported_user_info["name"],
                            "username": imported_user_info["username"],
                            "history": imported_history
                        }
                    }
                    import_successful = True
                    await update.message.reply_text(
                        "⚠️ Tu es sur le point d'importer des données CSV. "
                        "Ceci remplacera TOUT ton historique actuel en mémoire.\n" # Updated message
                        "Réponds OUI pour confirmer, NON pour annuler.",
                        reply_markup=ReplyKeyboardMarkup([["OUI", "NON"]], resize_keyboard=True)
                    )
                else:
                    await update.message.reply_text("Aucune donnée valide trouvée dans le fichier CSV.", reply_markup=get_main_menu())

            except Exception as e:
                logging.error(f"Error importing CSV for user {user_id}: {e}")
                await update.message.reply_text(f"Erreur lors de l'import CSV : {e}", reply_markup=get_main_menu())

        elif filename.endswith(".txt"):
            try:
                content = await file.download_as_bytearray()
                # Decode content and split into sequences
                text_content = content.decode("utf-8")
                sequences_text = text_content.split("--------------------") # Split by delimiter

                imported_history = []
                # Regex to extract data from each line of a sequence
                import re
                date_time_m = re.compile(r"📅 (.*) à (.*):(.*) \| Mise : (.*)")
                cote_m = re.compile(r"[12]️⃣ Cote (.*) : Case (.*) \((.*)\) — (.*)")
                result_m = re.compile(r"Résultat : (.*)")

                for seq_text in sequences_text:
                    lines = seq_text.strip().split('\n')
                    # Need at least 4 lines for a complete sequence block plus delimiter
                    if len(lines) >= 4:
                        try:
                            # Parse lines - assuming standard TXT format
                            date_heure_sec_mise = date_time_m.match(lines[0])
                            cote123_details = cote_m.match(lines[1])
                            cote154_details = cote_m.match(lines[2])
                            overall_result = result_m.match(lines[3])

                            if date_heure_sec_mise and cote123_details and cote154_details and overall_result:
                                date, heure, seconde, bet_amount = date_heure_sec_mise.groups()

                                # Determine result type based on emoji
                                result_type = "gagne" if "🏆" in overall_result.group(1) else "perdu"

                                # Add entries for both cotes
                                # Cote 1.23
                                cote123, case123, sens123, res123 = cote123_details.groups()
                                imported_history.append({
                                    "type": result_type,
                                    "cote": cote123,
                                    "case": case123,
                                    "side": sens123,
                                    "side_ref": "", # TXT export doesn't have side_ref, default to empty string
                                    "resultat": res123,
                                    "date": date,
                                    "heure": heure,
                                    "seconde": seconde,
                                    "bet_amount": bet_amount
                                })

                                # Cote 1.54
                                cote154, case154, sens154, res154 = cote154_details.groups()
                                imported_history.append({
                                    "type": result_type,
                                    "cote": cote154,
                                    "case": case154,
                                    "side": sens154,
                                    "side_ref": "", # TXT export doesn't have side_ref, default to empty string
                                    "resultat": res154,
                                    "date": date,
                                    "heure": heure,
                                    "seconde": seconde,
                                    "bet_amount": bet_amount
                                })

                        except Exception as parse_error:
                            logging.warning(f"Could not parse sequence in TXT import: {lines[0] if lines else 'Empty'}. Error: {parse_error}")
                            # Skip to next sequence if parsing fails for one block
                            continue

                if imported_history:
                    # Assume imported history belongs to the current user
                    user_id = str(update.effective_user.id)
                    # We cannot get name/username from TXT, so use empty strings or potentially fetch from DB if user exists
                    imported_data_structure = {
                        user_id: {
                            "name": "", # Cannot parse from TXT
                            "username": "", # Cannot parse from TXT
                            "history": imported_history
                         }
                    }

                    imported_data = imported_data_structure
                    import_successful = True
                    await update.message.reply_text(
                        "⚠️ Tu es sur le point d'importer des données TXT. "
                        "Ceci remplacera TOUT ton historique actuel en mémoire.\n" # Updated message
                        "Note : Le format TXT n'inclut pas le nom et le pseudo, ceux de ton profil actuel seront conservés ou définis.\n"
                        "Réponds OUI pour confirmer, NON pour annuler.",
                        reply_markup=ReplyKeyboardMarkup([["OUI", "NON"]], resize_keyboard=True)
                    )
                else:
                    await update.message.reply_text("Aucune donnée valide trouvée dans le fichier TXT.", reply_markup=get_main_menu())

            except Exception as e:
                logging.error(f"Error importing TXT for user {user_id}: {e}")
                await update.message.reply_text(f"Erreur lors de l'import TXT : {e}", reply_markup=get_main_menu())
        else:
            await update.message.reply_text("Merci d'envoyer un fichier au format .json, .csv ou .txt.", reply_markup=get_main_menu())

        # Store the imported data in user_data if parsing was successful, regardless of format
        if import_successful:
             context.user_data["imported_data_to_confirm"] = imported_data
             context.user_data["awaiting_import_confirmation"] = True
        else:
             # If import wasn't successful, clean up
             context.user_data.pop("imported_data_to_confirm", None)
             context.user_data.pop("awaiting_import_confirmation", None)


    else:
        await update.message.reply_text("Merci d'envoyer un fichier à importer (JSON, CSV ou TXT) juste après cette commande.", reply_markup=get_main_menu())
    # Stay in the same state waiting for confirmation or another file if error
    # Return None to keep the conversation handler active if awaiting confirmation,
    # otherwise ConversationHandler.END if no file was sent or parsing failed.
    if context.user_data.get("awaiting_import_confirmation"):
         return # Stay in the current state, waiting for confirmation
    else:
         # This return was missing, causing the import to end immediately after receiving a file
         # that wasn't OUI/NON and didn't trigger confirmation.
         # Let's explicitly return ConversationHandler.END here if no confirmation is pending.
         return ConversationHandler.END


# handle_import_confirmation now writes to user_memory
async def handle_import_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("awaiting_import_confirmation"):
        response = update.message.text.strip().lower()
        if response == "oui":
            imported_data = context.user_data.get("imported_data_to_confirm")
            user_id = str(update.effective_user.id)

            if not imported_data or user_id not in imported_data:
                 logging.error(f"Import confirmation received but no data found for user {user_id}")
                 await update.message.reply_text("Une erreur interne s'est produite. Importation annulée.", reply_markup=get_main_menu())
                 # Clean up context data
                 context.user_data.pop("imported_data_to_confirm", None)
                 context.user_data.pop("awaiting_import_confirmation", None)
                 return ConversationHandler.END

            user_data_to_import = imported_data[user_id]
            history_to_import = user_data_to_import.get("history", [])
            imported_name = user_data_to_import.get("name", "")
            imported_username = user_data_to_import.get("username", "")

            # Ensure user exists in memory; create if not (shouldn't happen if /start is used)
            if user_id not in user_memory:
                 user_memory[user_id] = {"name": "", "username": "", "history": []}
                 logging.info(f"Created user {user_id} in memory during import confirmation.")

            # 1. Replace existing history for the user in memory
            user_memory[user_id]["history"] = history_to_import
            logging.info(f"Replaced existing history in memory for user {user_id} with {len(history_to_import)} entries.")

            # 2. Update user's name and username if available in imported data (prioritize imported if not empty)
            # Use current Telegram info as fallback if imported fields are empty
            current_first_name = update.effective_user.first_name or ""
            current_last_name = update.effective_user.last_name or ""
            current_username = update.effective_user.username or ""
            current_full_name = f"{current_first_name} {current_last_name}".strip()

            name_to_save = imported_name if imported_name else user_memory[user_id].get("name", current_full_name) # Keep existing name if imported is empty
            username_to_save = imported_username if imported_username else user_memory[user_id].get("username", current_username) # Keep existing username if imported is empty

            user_memory[user_id]["name"] = name_to_save
            user_memory[user_id]["username"] = username_to_save
            logging.info(f"Updated user info in memory for {user_id} during import confirmation.")


            context.user_data.pop("imported_data_to_confirm", None)
            context.user_data.pop("awaiting_import_confirmation", None)
            await update.message.reply_text("✅ Import terminé ! Ton historique en mémoire a été remplacé.", reply_markup=get_main_menu()) # Updated message
            return ConversationHandler.END


        elif response == "non":
            context.user_data.pop("imported_data_to_confirm", None)
            context.user_data.pop("awaiting_import_confirmation", None)
            await update.message.reply_text("❌ Import annulé. Tes données précédentes en mémoire sont intactes.", reply_markup=get_main_menu()) # Updated message
            return ConversationHandler.END
        else:
            # If response is not OUI or NON, stay in confirmation state
            await update.message.reply_text("Merci de répondre par OUI ou NON.", reply_markup=ReplyKeyboardMarkup([["OUI", "NON"]], resize_keyboard=True))
            return # Stay in the current state

    # If not awaiting confirmation, this message was not part of the confirmation flow
    # End the conversation or let the general handler take over
    pass # Let the message continue to other handlers if not in confirmation state

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().lower()
    # Check if the message is part of a conversation that is not handled by handle_button
    # e.g., if awaiting_reset or awaiting_import_confirmation is True, those handlers should act first.
    # The ConversationHandlers are checked before this general handler.
    # So if a ConversationHandler is active and matched the message, this handler won't be called.
    # We only need to check scam words and general menu buttons here.

    if contains_scam_words(text):
        await update.message.reply_text(
            "❌ Il n'existe aucune astuce, hack, bot, ou méthode secrète pour gagner à Apple of Fortune. "
            "Le jeu sur 1xbet repose sur un hasard pur (RNG) : chaque case a exactement 20% de chance d'être gagnante à chaque tour. "
            "Méfie-toi des arnaques sur internet !",
            reply_markup=get_main_menu()
        )
        return
    # The rest of the buttons like "🍏 Prédire", "📤 Exporter", "♻️ Réinitialiser historique"
    # are handled by the ConversationHandlers defined in main().
    # The remaining buttons ("ℹ️ Fonctionnement", "🎯 Conseils", etc.) are handled below.
    elif "importer" in text:
        # The import_data function is also a MessageHandler for documents.
        # This part handles the button click prompting the user to send the file.
        await update.message.reply_text("Merci d'envoyer le fichier JSON, CSV ou TXT que tu veux importer, via le trombone (📎).", reply_markup=get_main_menu())
    elif "fonctionnement" in text:
        await fonctionnement(update, context)
    elif "conseils" in text:
        await conseils(update, context)
    elif "arnaques" in text:
        await arnaques(update, context)
    elif "contact" in text:
        await contact(update, context)
    elif "faq" in text:
        await faq(update, context)
    elif "tutoriel" in text:
        await tuto(update, context)
    elif "à propos" in text or "a propos" in text:
        await apropos(update, context)
    elif "historique" in text:
        await historique(update, context)
    elif "statistique" in text or "statistic" in text:
        await stats_perso(update, context)
    elif "⬅️ menu principal" in text:
         # This button might be used within conversations, handle it here too as a fallback
         await update.message.reply_text("Retour au menu principal.", reply_markup=get_main_menu())
         # Note: If this is hit while in a conversation state, the conversation will effectively be cancelled implicitly.
         # It's better to handle "⬅️ Menu principal" explicitly in each conversation's fallbacks.
    else:
        # Generic fallback for unhandled text messages
        # Check if the message was part of an expected flow (e.g. during import confirmation)
        # If it was, the ConversationHandler or specific handler (like handle_import_confirmation)
        # would have consumed it. If it reaches here, it's truly unknown or outside a flow.
        await update.message.reply_text(
            "Commande inconnue. Utilise le menu en bas ou tape /start.",
            reply_markup=get_main_menu()
        )


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Load access codes on startup
    load_access_codes()

    application = ApplicationBuilder().token(TOKEN).build()

    # Commandes classiques
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("fonctionnement", fonctionnement))
    application.add_handler(CommandHandler("conseils", conseils))
    application.add_handler(CommandHandler("arnaques", arnaques))
    application.add_handler(CommandHandler("contact", contact))
    application.add_handler(CommandHandler("faq", faq))
    application.add_handler(CommandHandler("tuto", tuto))
    application.add_handler(CommandHandler("apropos", apropos))
    application.add_handler(CommandHandler("historique", historique))
    application.add_handler(CommandHandler("statistiques", stats_perso))
    application.add_handler(CommandHandler("stats", stats_perso))
    # The /import command itself doesn't handle the file, it just prompts.
    # The file handling and confirmation are done by MessageHandlers and the conversation.
    application.add_handler(CommandHandler("import", import_data))

    # Add a handler for "commence" to start the bot
    application.add_handler(MessageHandler(filters.Regex("^(commence|Commence)$"), start))

    # ConversationHandler for the automatic prediction flow
    auto_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^(🍏 Prédire|prédire|predire)$"), predire_auto),
        ],
        states={
            ASK_1XBET_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_1xbet_id)],
            ASK_BET_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_bet_amount)],
            ASK_RESULTS: [MessageHandler(filters.Regex("^(🏆 Gagné|💥 Perdu|gagné|perdu|gagne)$"), after_result)],
            ASK_CASES: [MessageHandler(filters.Regex("^[1-5]$"), collect_case)],
            ASK_SIDE: [MessageHandler(filters.Regex("^(Gauche|Droite|gauche|droite)$"), collect_side)],
            ASK_BONNE_MAUVAISE: [MessageHandler(filters.Regex("^(Bonne|Mauvaise|bonne|mauvaise)$"), collect_bonne_mauvaise)],
        },
        fallbacks=[
            CommandHandler("start", start),
            MessageHandler(filters.Regex("^(⬅️ Menu principal|menu principal)$"), lambda u, c: u.message.reply_text("Opération annulée.", reply_markup=get_main_menu()) and ConversationHandler.END), # Handle explicit menu return
            MessageHandler(filters.TEXT | filters.COMMAND, lambda u, c: u.message.reply_text("Opération annulée.", reply_markup=get_main_menu()) and ConversationHandler.END) # Generic fallback to end conversation
        ],
        allow_reentry=True, # Allow restarting the conversation
        name="auto_pred_conversation", # Give it a name for debugging
        persistent=False # Conversations are not persistent across bot restarts by default
    )
    application.add_handler(auto_conv)

    # ConversationHandler for history reset
    reset_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^(♻️ Réinitialiser historique|réinitialiser historique|reinitialiser historique)$"), reset_historique)
        ],
        states={
            RESET_CONFIRM: [MessageHandler(filters.Regex("^(OUI|NON|oui|non)$"), handle_reset_confirm)]
        },
         fallbacks=[
            CommandHandler("start", start),
            MessageHandler(filters.Regex("^(⬅️ Menu principal|menu principal)$"), lambda u, c: u.message.reply_text("Réinitialisation annulée.", reply_markup=get_main_menu()) and ConversationHandler.END), # Handle explicit menu return
            MessageHandler(filters.TEXT | filters.COMMAND, lambda u, c: u.message.reply_text("Réinitialisation annulée.", reply_markup=get_main_menu()) and ConversationHandler.END) # Generic fallback
        ],
        allow_reentry=True,
        name="reset_history_conversation",
        persistent=False
    )
    application.add_handler(reset_conv)


    # ConversationHandler for export format choice
    export_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^(📤 Exporter|exporter)$"), ask_export_format)
        ],
        states={
            ASK_EXPORT_FORMAT: [MessageHandler(filters.Regex("^(JSON|CSV|TXT|⬅️ Menu principal|menu principal)$"), handle_export_format_choice)]
        },
        fallbacks=[
            CommandHandler("start", start),
            MessageHandler(filters.TEXT | filters.COMMAND, lambda u, c: u.message.reply_text("Exportation annulée.", reply_markup=get_main_menu()) and ConversationHandler.END) # Generic fallback
        ],
        allow_reentry=True,
        name="export_conversation",
        persistent=False
    )
    application.add_handler(export_conv)
    # Handler for documents (used by import) - This handler is outside a conversation
    # because the user sends the file *after* clicking the "Importer" button.
    # The confirmation happens in handle_import_confirmation, which is also a regular MessageHandler
    # but with a filter for OUI/NON and a check for the awaiting_import_confirmation state.
    application.add_handler(MessageHandler(filters.Document.ALL, import_data))
    # Handler for the import confirmation (OUI/NON) - This needs to be a general handler
    # because the response comes after the file has been received and processed by import_data.
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex("^(OUI|NON|oui|non)$"), handle_import_confirmation))
    # Handler general for menu buttons and other text (fallback)
    # This should be added *after* all ConversationHandlers and specific MessageHandlers,
    # so that those take precedence.
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_button))
    print("Bot démarré (stockage en mémoire)...") # Updated startup message
    application.run_polling()
if __name__ == "__main__":
    main()
