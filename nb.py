import logging
import random
import json
import csv
import os
import datetime
import sqlite3 # Added sqlite3 import
import uuid  # Pour générer des codes uniques
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes,
    MessageHandler, filters, ConversationHandler
)

TOKEN = "8057509848:AAHJsE1q63yn9OgBFftKiE8MUqOpidilBuw"

POSITIONS = ["1", "2", "3", "4", "5"]
COTES = ["1.23", "1.54"]
SIDES = ["Gauche", "Droite"]

# Removed DATA_FILE and CSV_FILE as we will use a database
DATABASE_FILE = "apple_predictor.db" # Define database file name

# user_memory will no longer hold all data, mainly used for user info cache if needed
# But for simplicity, we might access DB directly in functions
user_memory = {}

ASK_RESULTS, ASK_CASES, ASK_SIDE, ASK_BONNE_MAUVAISE, ASK_1XBET_ID, RESET_CONFIRM, ASK_BET_AMOUNT, ASK_EXPORT_FORMAT = range(8)

# Database Initialization Function
def init_db():
    """Initialise la base de données SQLite en créant les tables si elles n'existent pas."""
    conn = None
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()

        # Create users table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            name TEXT,
            username TEXT
        );
        ''')

        # Create history table
        # Renamed 'case' to 'case_number' to avoid potential SQL keyword conflict
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS history (
            history_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            type TEXT,
            cote TEXT,
            case_number TEXT,
            side TEXT,
            side_ref TEXT,
            resultat TEXT,
            date TEXT,
            heure TEXT,
            seconde TEXT,
            bet_amount TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        );
        ''')

        # Create access_control table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS access_control (
            user_id TEXT PRIMARY KEY,
            access_code TEXT,
            expiration_time DATETIME
        );
        ''')

        conn.commit()
        logging.info("Database initialized successfully.")
    except sqlite3.Error as e:
        logging.error(f"Database error during initialization: {e}")
        if conn:
            conn.rollback() # Rollback changes if an error occurs
    finally:
        if conn:
            conn.close()

# Removed save_data() and load_data() as database handles persistence

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

# get_user_history now reads from the database
def get_user_history(user_id):
    """Récupère l'historique d'un utilisateur depuis la base de données."""
    conn = None
    history = []
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        # Select history entries for the specific user, ordered by history_id to maintain sequence
        cursor.execute("SELECT type, cote, case_number, side, side_ref, resultat, date, heure, seconde, bet_amount FROM history WHERE user_id = ? ORDER BY history_id", (user_id,))
        rows = cursor.fetchall()
        # Map rows to dictionary format similar to the old JSON structure
        for row in rows:
             history.append({
                "type": row[0],
                "cote": row[1],
                "case": row[2], # Use "case" key for compatibility with existing functions
                "side": row[3],
                "side_ref": row[4],
                "resultat": row[5],
                "date": row[6],
                "heure": row[7],
                "seconde": row[8],
                "bet_amount": row[9]
            })
    except sqlite3.Error as e:
        logging.error(f"Database error fetching history for user {user_id}: {e}")
    finally:
        if conn:
            conn.close()
    return history

# export_csv now reads from the database using get_user_history
async def export_csv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    # Collect data for the current user's history
    memory = get_user_history(user_id) # Use the new DB function
    if not memory:
        await update.message.reply_text("Aucun historique à exporter.", reply_markup=get_main_menu())
        # Return ConversationHandler.END if called from conversation, or None otherwise
        return ConversationHandler.END if 'export_format_choice' in context.user_data else None

    rows = []
    # Need user's name and username from the DB
    user_info = {}
    conn = None
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT name, username FROM users WHERE user_id = ?", (user_id,))
        user_row = cursor.fetchone()
        if user_row:
            user_info["name"] = user_row[0] or ""
            user_info["username"] = user_row[1] or ""
    except sqlite3.Error as e:
        logging.error(f"Database error fetching user info for export {user_id}: {e}")
    finally:
        if conn:
            conn.close()

    for entry in memory:
        rows.append({
            "user_id": user_id,
            "name": user_info.get("name", ""),
            "username": user_info.get("username", ""),
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

# start function now interacts with the database for user info
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    first_name = update.effective_user.first_name or ""
    last_name = update.effective_user.last_name or ""
    username = update.effective_user.username or ""
    full_name = f"{first_name} {last_name}".strip()

    conn = None
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()

        # Check if user exists
        cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        user_exists = cursor.fetchone()

        if not user_exists:
            # Insert new user
            cursor.execute("INSERT INTO users (user_id, name, username) VALUES (?, ?, ?)",
                           (user_id, full_name, username))
            conn.commit()
            logging.info(f"New user added: {user_id}")
        else:
            # Update existing user info (name, username might change)
            cursor.execute("UPDATE users SET name = ?, username = ? WHERE user_id = ?",
                           (full_name, username, user_id))
            conn.commit()
            logging.info(f"User info updated: {user_id}")

    except sqlite3.Error as e:
        logging.error(f"Database error in start function for user {user_id}: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

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

# stats_perso now reads from the database
async def stats_perso(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    conn = None
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()

        # Count total sequences (pairs of cote 1.23 and 1.54 entries)
        cursor.execute("SELECT COUNT(*) FROM history WHERE user_id = ?", (user_id,))
        total_entries = cursor.fetchone()[0]
        total_sequences = total_entries // 2 # Assuming history is saved in pairs

        if total_sequences == 0:
             await update.message.reply_text("Aucune statistique disponible pour l'instant, joue une séquence pour commencer.", reply_markup=get_main_menu())
             return

        # Count wins and losses for each cote
        cursor.execute("SELECT cote, resultat, COUNT(*) FROM history WHERE user_id = ? AND (resultat = 'Bonne' OR resultat = 'Mauvaise') GROUP BY cote, resultat", (user_id,))
        results = cursor.fetchall()

        victoire_123 = 0
        defaites_123 = 0
        victoire_154 = 0
        defaites_154 = 0

        for cote, resultat, count in results:
            if cote == "1.23":
                if resultat == "Bonne":
                    victoire_123 = count
                elif resultat == "Mauvaise":
                    defaites_123 = count
            elif cote == "1.54":
                if resultat == "Bonne":
                    victoire_154 = count
                elif resultat == "Mauvaise":
                    defaites_154 = count

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

    except sqlite3.Error as e:
        logging.error(f"Database error fetching stats for user {user_id}: {e}")
        await update.message.reply_text("❌ Une erreur s'est produite lors du chargement des statistiques.", reply_markup=get_main_menu())
    finally:
        if conn:
            conn.close()

# historique now reads from the database
async def historique(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    memory = get_user_history(user_id) # Use the new DB function
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
    await update.message.reply_text(
        "⚠️ Veux-tu vraiment supprimer tout ton historique ?\nRéponds OUI pour confirmer, NON pour annuler.",
        reply_markup=ReplyKeyboardMarkup([["OUI", "NON"]], resize_keyboard=True)
    )
    context.user_data["awaiting_reset"] = True
    return RESET_CONFIRM

# handle_reset_confirm now interacts with the database
async def handle_reset_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("awaiting_reset"):
        if update.message.text.strip().upper() == "OUI":
            user_id = str(update.effective_user.id)
            conn = None
            try:
                conn = sqlite3.connect(DATABASE_FILE)
                cursor = conn.cursor()
                # Delete history for the specific user
                cursor.execute("DELETE FROM history WHERE user_id = ?", (user_id,))
                conn.commit()
                logging.info(f"History reset for user {user_id}")
                context.user_data["awaiting_reset"] = False
                await update.message.reply_text("✅ Ton historique a été réinitialisé.", reply_markup=get_main_menu())
                return ConversationHandler.END
            except sqlite3.Error as e:
                logging.error(f"Database error resetting history for user {user_id}: {e}")
                if conn:
                    conn.rollback()
                context.user_data["awaiting_reset"] = False # Exit reset state on error
                await update.message.reply_text("❌ Une erreur s'est produite lors de la réinitialisation.", reply_markup=get_main_menu())
                return ConversationHandler.END # End conversation on error
            finally:
                if conn:
                    conn.close()
        else:
            context.user_data["awaiting_reset"] = False
            await update.message.reply_text("❌ Réinitialisation annulée.", reply_markup=get_main_menu())
            return ConversationHandler.END
    # If not awaiting reset, this message was not part of the confirmation flow
    return ConversationHandler.END # Fallback to end conversation if state is wrong

async def predire_auto(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    if user_id_1xbet or bet_amount_for_rng:
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


# collect_bonne_mauvaise now saves to the database
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

    # If all cote details are collected, save to DB and finish
    user_id = str(update.effective_user.id)
    result_type = context.user_data.get('auto_result')
    timeinfo = current_time_data()
    bet_amount = context.user_data.get("bet_amount", "-")

    conn = None
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()

        for i, detail in enumerate(context.user_data.get("auto_case_details", [])):
             cote = detail.get("cote", "-")
             case = detail.get("case", "-")
             side = detail.get("side", "-")
             side_ref = detail.get("side_ref", "-")
             resultat = detail.get("resultat", "-")

             cursor.execute(
                "INSERT INTO history (user_id, type, cote, case_number, side, side_ref, resultat, date, heure, seconde, bet_amount) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (user_id, result_type, cote, case, side, side_ref, resultat, timeinfo["date"], timeinfo["heure"], timeinfo["seconde"], bet_amount)
            )
        conn.commit()
        logging.info(f"Sequence saved to DB for user {user_id}")

        await update.message.reply_text(
            f"{'✅' if result_type == 'gagne' else '❌'} Séquence enregistrée !",
            reply_markup=get_main_menu()
        )

    except sqlite3.Error as e:
        logging.error(f"Database error saving sequence for user {user_id}: {e}")
        if conn:
            conn.rollback()
        await update.message.reply_text("❌ Une erreur s'est produite lors de l'enregistrement de la séquence.", reply_markup=get_main_menu())
    finally:
        if conn:
            conn.close()

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


# export_txt now reads from the database using get_user_history
async def export_txt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    memory = get_user_history(user_id) # Use the new DB function
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
            if os.path.exists(txt_filename)):
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

# export_json now reads from the database
async def export_json(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    memory = get_user_history(user_id) # Use the new DB function

    if not memory:
        await update.message.reply_text("Aucun historique à exporter.", reply_markup=get_main_menu())
        # Return ConversationHandler.END if called from conversation, or None otherwise
        return ConversationHandler.END if 'export_format_choice' in context.user_data else None

    # Need user info from DB
    user_info = {}
    conn = None
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT name, username FROM users WHERE user_id = ?", (user_id,))
        user_row = cursor.fetchone()
        if user_row:
            user_info["name"] = user_row[0] or ""
            user_info["username"] = user_row[1] or ""
    except sqlite3.Error as e:
        logging.error(f"Database error fetching user info for JSON export {user_id}: {e}")
    finally:
        if conn:
            conn.close()

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
            if os.path.exists(json_filename)):
                os.remove(json_filename)
        except OSError as e:
            logging.error(f"Error removing file {json_filename}: {e}")
    return ConversationHandler.END

# import_data handles receiving the file and asking for confirmation
async def import_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.document:
        file = await update.message.document.get_file()
        filename = update.message.document.file_name
        user_id = str(update.effective_user.id) # User who is importing

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
                              imported_data = {
                                  user_id: { # Map imported data to the current user's ID
                                       "name": imported_user_data.get("name", ""),
                                       "username": imported_user_data.get("username", ""),
                                       "history": imported_user_data["history"]
                                  }
                              }
                              import_successful = True
                              await update.message.reply_text(
                                  "⚠️ Tu es sur le point d'importer des données JSON. "
                                  "Ceci remplacera TOUT ton historique actuel.\n"
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
                     # However, we will link the imported history to the *current* user_id in the DB
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
                        "Ceci remplacera TOUT ton historique actuel.\n"
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
                                    "side_ref": "?", # TXT export doesn't have side_ref
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
                                    "side_ref": "?", # TXT export doesn't have side_ref
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
                        "Ceci remplacera TOUT ton historique actuel.\n"
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
         return ConversationHandler.END # End the import process if no file or error

# handle_import_confirmation now writes to the database
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

            conn = None
            try:
                conn = sqlite3.connect(DATABASE_FILE)
                cursor = conn.cursor()

                # Start a transaction for atomic operation
                conn.execute("BEGIN TRANSACTION")

                # 1. Delete existing history for the user
                cursor.execute("DELETE FROM history WHERE user_id = ?", (user_id,))
                logging.info(f"Deleted existing history for user {user_id} before import.")

                # 2. Update user's name and username if available in imported data
                # Use current Telegram info as fallback if imported fields are empty
                current_first_name = update.effective_user.first_name or ""
                current_last_name = update.effective_user.last_name or ""
                current_username = update.effective_user.username or ""
                current_full_name = f"{current_first_name} {current_last_name}".strip()

                name_to_save = imported_name if imported_name else current_full_name
                username_to_save = imported_username if imported_username else current_username

                # Ensure user exists before trying to update
                cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
                user_exists = cursor.fetchone()

                if not user_exists:
                     # Create user if they don't exist (should be rare if /start is used)
                     cursor.execute("INSERT INTO users (user_id, name, username) VALUES (?, ?, ?)",
                                    (user_id, name_to_save, username_to_save))
                     logging.info(f"Created user {user_id} during import.")
                else:
                     # Update existing user
                     cursor.execute("UPDATE users SET name = ?, username = ? WHERE user_id = ?",
                                    (name_to_save, username_to_save, user_id))
                     logging.info(f"Updated user info for {user_id} during import.")


                # 3. Insert new history from imported data
                for entry in history_to_import:
                     # Ensure required keys exist, provide defaults
                    type_ = entry.get("type", "-")
                    cote = entry.get("cote", "-")
                    # Use "case" key from imported data, map to "case_number" column
                    case_number = entry.get("case", "-")
                    side = entry.get("side", "-")
                    # Allow empty side_ref for older TXT imports
                    side_ref = entry.get("side_ref", "") # Default to empty string instead of "-"
                    resultat = entry.get("resultat", "-")
                    date = entry.get("date", "-")
                    heure = entry.get("heure", "-")
                    seconde = entry.get("seconde", "-")
                    bet_amount = entry.get("bet_amount", "-") # Stored as text

                    cursor.execute(
                        "INSERT INTO history (user_id, type, cote, case_number, side, side_ref, resultat, date, heure, seconde, bet_amount) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (user_id, type_, cote, case_number, side, side_ref, resultat, date, heure, seconde, bet_amount)
                    )
                logging.info(f"Inserted {len(history_to_import)} history entries for user {user_id}.")

                conn.execute("COMMIT") # Commit the transaction
                logging.info(f"Import completed successfully for user {user_id}.")

                context.user_data.pop("imported_data_to_confirm", None)
                context.user_data.pop("awaiting_import_confirmation", None)
                await update.message.reply_text("✅ Import terminé ! Ton historique a été remplacé.", reply_markup=get_main_menu())

            except sqlite3.Error as e:
                logging.error(f"Database error during import confirmation for user {user_id}: {e}")
                if conn:
                    conn.execute("ROLLBACK") # Rollback changes on error
                context.user_data.pop("imported_data_to_confirm", None)
                context.user_data.pop("awaiting_import_confirmation", None)
                await update.message.reply_text("❌ Une erreur s'est produite lors de l'importation. Tes données précédentes sont intactes.", reply_markup=get_main_menu())
            finally:
                if conn:
                    conn.close()

        elif response == "non":
            context.user_data.pop("imported_data_to_confirm", None)
            context.user_data.pop("awaiting_import_confirmation", None)
            await update.message.reply_text("❌ Import annulé. Tes données précédentes sont intactes.", reply_markup=get_main_menu())
        else:
            # If response is not OUI or NON, stay in confirmation state
            await update.message.reply_text("Merci de répondre par OUI ou NON.", reply_markup=ReplyKeyboardMarkup([["OUI", "NON"]], resize_keyboard=True))
            return # Stay in the current state

    # If not awaiting confirmation, this message was not part of the confirmation flow
    # End the conversation or let the general handler take over
    # Returning None here will let the general handler process the message if it wasn't OUI/NON
    # If it was OUI/NON but not awaiting, the handler filter will prevent it from reaching here
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

# Fonction pour générer un code unique
def generate_access_code(user_id, duration_minutes):
    """Génère un code unique pour un utilisateur avec une durée d'accès."""
    code = str(uuid.uuid4())[:8]  # Code unique de 8 caractères
    expiration_time = datetime.datetime.now() + datetime.timedelta(minutes=duration_minutes)
    conn = sqlite3.connect(DATABASE_FILE)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO access_control (user_id, access_code, expiration_time) VALUES (?, ?, ?)",
            (user_id, code, expiration_time)
        )
        conn.commit()
        return code, expiration_time
    except sqlite3.Error as e:
        logging.error(f"Error generating access code for user {user_id}: {e}")
    finally:
        conn.close()

# Fonction pour vérifier si un utilisateur a un accès valide
def has_valid_access(user_id):
    """Vérifie si l'utilisateur a un accès valide."""
    conn = sqlite3.connect(DATABASE_FILE)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT expiration_time FROM access_control WHERE user_id = ?",
            (user_id,)
        )
        row = cursor.fetchone()
        if row:
            expiration_time = datetime.datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
            return datetime.datetime.now() < expiration_time
        return False
    except sqlite3.Error as e:
        logging.error(f"Error checking access for user {user_id}: {e}")
        return False
    finally:
        conn.close()

# Commande pour entrer un code d'accès
async def enter_access_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    code = update.message.text.strip()
    conn = sqlite3.connect(DATABASE_FILE)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT expiration_time FROM access_control WHERE user_id = ? AND access_code = ?",
            (user_id, code)
        )
        row = cursor.fetchone()
        if row:
            expiration_time = datetime.datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
            if datetime.datetime.now() < expiration_time:
                await update.message.reply_text("✅ Accès validé ! Bienvenue sur le bot.")
                return
            else:
                await update.message.reply_text("❌ Code expiré. Veuillez demander un nouveau code.")
        else:
            await update.message.reply_text("❌ Code invalide. Veuillez réessayer.")
    except sqlite3.Error as e:
        logging.error(f"Error validating access code for user {user_id}: {e}")
        await update.message.reply_text("❌ Une erreur s'est produite. Veuillez réessayer.")
    finally:
        conn.close()

# Middleware pour vérifier l'accès avant chaque commande
async def access_middleware(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not has_valid_access(user_id):
        await update.message.reply_text("❌ Accès refusé. Veuillez entrer un code valide.")
        return False
    return True

# Ajoutez un décorateur pour protéger les commandes
async def protected_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await access_middleware(update, context):
        await update.message.reply_text("✅ Vous avez accès à cette commande protégée.")

# Ajoutez une commande pour générer un code (réservée à l'administrateur)
async def generate_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != "YOUR_TELEGRAM_ID":  # Remplacez par votre ID Telegram
        await update.message.reply_text("❌ Vous n'êtes pas autorisé à générer des codes.")
        return
    try:
        user_id = context.args[0]
        duration_minutes = int(context.args[1])
        code, expiration_time = generate_access_code(user_id, duration_minutes)
        await update.message.reply_text(
            f"✅ Code généré pour l'utilisateur {user_id} : {code}\n"
            f"Valide jusqu'à : {expiration_time.strftime('%Y-%m-%d %H:%M:%S')}",
            reply_markup=get_admin_menu()
        )
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Utilisation : /generate_code <user_id> <durée_en_minutes>", reply_markup=get_admin_menu())

def get_admin_menu():
    """Generate the admin menu keyboard."""
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("🔑 Générer un code"), KeyboardButton("📋 Voir les utilisateurs")],
            [KeyboardButton("⬅️ Menu principal")]
        ],
        resize_keyboard=True
    )

async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display the admin menu."""
    if str(update.effective_user.id) != "YOUR_TELEGRAM_ID":  # Replace with your Telegram ID
        await update.message.reply_text("❌ Vous n'êtes pas autorisé à accéder au menu admin.")
        return
    await update.message.reply_text("🔧 Menu Admin :", reply_markup=get_admin_menu())

def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    init_db() # Initialize the database at the start

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
    application.add_handler(CommandHandler("enter_code", enter_access_code))
    application.add_handler(CommandHandler("generate_code", generate_code))
    application.add_handler(CommandHandler("protected", protected_command))
    application.add_handler(CommandHandler("admin", admin_menu))


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
            MessageHandler(filters.Regex("^(⬅️ Menu principal|menu principal)$"), lambda u, c: u.message.reply_text("Réinitialisation annulée.", reply_markup=get_main_menu()) and ConversationHandler.END),
            MessageHandler(filters.TEXT | filters.COMMAND, lambda u, c: u.message.reply_text("Réinitialisation annulée.", reply_markup=get_main_menu()) and ConversationHandler.END)
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
        ],
        fallbacks=[
            CommandHandler("start", start),
            MessageHandler(filters.TEXT | filters.COMMAND, lambda u, c: u.message.reply_text("Exportation annulée.", reply_markup=get_main_menu()) and ConversationHandler.END)  # Fixed syntax
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
    print("Bot démarré et base de données initialisée...")
    application.run_polling()
if __name__ == "__main__":
    main()
