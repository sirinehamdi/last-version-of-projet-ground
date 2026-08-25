from flask import Flask, request, jsonify, render_template, send_file, redirect, url_for
from datetime import datetime
import base64
import imghdr
import json
import os
import requests
from collections import deque

from models import db, Log, Command, Telemetry, Image, Month, Day
from satellite_profiles import PROFILES_FILE, load_satellite_profiles
from core.decoder import FrameDecoder, CommandFormatter
import serial
import threading
app = Flask(__name__)
app.instance_path = os.path.join(app.root_path, "instance")
os.makedirs(app.instance_path, exist_ok=True)

db_path = os.path.join(app.instance_path, "data.db")
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)
with app.app_context():
    db.create_all()

# ==================================================
# COMMUNICATION DU PROFIL SELECTIONNE
# ==================================================
radio = None
active_satellite_key = None
radio_thread = None
satellite_data_history = deque(maxlen=200)


def get_active_satellite():
    """Retourne le profil sélectionné dans Housekeeping."""
    profiles = load_satellite_profiles()
    if not profiles:
        raise RuntimeError("Aucun profil satellite n'est défini")

    if active_satellite_key is None:
        raise RuntimeError("Sélectionnez un satellite dans Housekeeping avant d'envoyer une commande")

    profile = profiles.get(active_satellite_key)
    if profile is None:
        raise RuntimeError(f"Profil satellite introuvable : {active_satellite_key}")
    return profile


def configure_selected_communication(profile):
    """Ouvre le port série du profil choisi; aucun port n'est ouvert au démarrage."""
    global radio, radio_thread

    if radio is not None:
        radio.close()
        radio = None

    if profile.communication.type != "serial":
        return

    communication = profile.communication
    if not communication.port or not communication.baudrate:
        raise RuntimeError("Le profil série doit définir port et baudrate")

    radio = serial.Serial(
        communication.port,
        communication.baudrate,
        timeout=communication.timeout or 1,
    )
    radio.reset_input_buffer()
    radio.reset_output_buffer()

    if radio_thread is None or not radio_thread.is_alive():
        radio_thread = threading.Thread(target=read_radio, daemon=True)
        radio_thread.start()


def get_active_wifi_communication():
    """Retourne la configuration WiFi du profil sélectionné."""
    profile = get_active_satellite()
    communication = profile.communication
    if communication.type != "wifi" or not communication.host:
        raise RuntimeError("Le profil sélectionné ne définit pas de connexion WiFi")
    return communication


def send_tc(command, cmd_id="101", seq="000"):
    """Envoie une commande, en série si disponible, sinon en WiFi HTTP."""
    profile = get_active_satellite()
    communication = profile.communication
    decoder = profile.decoder
    command_name = command.strip().upper()
    valid_ids = set()
    for entry in profile.available_commands:
        if "id" in entry:
            valid_ids.add(entry["id"].upper())
        if "on_id" in entry:
            valid_ids.add(entry["on_id"].upper())
        if "off_id" in entry:
            valid_ids.add(entry["off_id"].upper())
    if command_name not in valid_ids:
        raise RuntimeError(f"Commande inconnue pour le profil {profile.name}: {command_name}")
    command_to_send = command_name

    if communication.type == "serial":
        if radio is None:
            raise RuntimeError("Aucun port série détecté pour ce profil")
        frame = CommandFormatter(decoder).format_command(
            command_to_send, cmd_id, seq
        )
        print("TC envoyée :", frame)
        radio.write(frame.encode())
        store_satellite_frame(frame, frame_type=decoder.telecommand_type, direction="TX")
        return frame

    if communication.type == "wifi" and command_name in {"CAM_ON", "CAM_OFF"}:
        wifi = get_active_wifi_communication()
        port = wifi.port_wifi or 80
        timeout = wifi.timeout_wifi or 15
        url = f"http://{wifi.host}:{port}/{command_to_send.lower()}"
        try:
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()
            print(f"[AUTO-WIFI] Commande HTTP envoyée: {url}")
            frame = f"HTTP {url}"
            store_satellite_frame(frame, frame_type=decoder.telecommand_type, direction="TX")
            return frame
        except Exception as exc:
            raise RuntimeError(
                f"Aucun port série détecté et commande WiFi impossible: {exc}"
            ) from exc

    raise RuntimeError(f"Commande non supportée pour le profil actif: {command_name}")
data_store = {
    "time": [],
}
# ==================================================
# ORGANISATION DATE : ANNEE -> MOIS -> JOUR
# ==================================================

def get_or_create_day(timestamp):

    year = timestamp.year
    month_number = timestamp.month
    day_date = timestamp.date()

    month_names = [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December"
    ]

    month_name = month_names[month_number - 1]

    # ------------------------------------------
    # Chercher le mois
    # ------------------------------------------

    month = Month.query.filter_by(
        year=year,
        month=month_number
    ).first()

    # Si le mois n'existe pas → création
    if month is None:

        month = Month(
            year=year,
            month=month_number,
            name=month_name
        )

        db.session.add(month)
        db.session.flush()

    # ------------------------------------------
    # Chercher le jour
    # ------------------------------------------

    day = Day.query.filter_by(
        month_id=month.id,
        date=day_date
    ).first()

    # Si le jour n'existe pas → création
    if day is None:

        day = Day(
            month_id=month.id,
            date=day_date
        )

        db.session.add(day)
        db.session.flush()

    return day

# Etats des commandes a deux positions, indexes par profil puis par identifiant ON.
command_states = {}


def get_toggle_state_key(on_id):
    return (active_satellite_key, on_id.upper())


@app.route("/command_state/<on_id>")
def get_command_state(on_id):
    """Retourne l'etat d'une commande a deux positions du profil actif."""
    try:
        profile = get_active_satellite()
    except RuntimeError as error:
        return jsonify({"error": str(error)}), 400

    normalized_on_id = on_id.strip().upper()
    is_toggle = any(
        entry.get("on_id", "").upper() == normalized_on_id
        for entry in profile.available_commands
    )
    if not is_toggle:
        return jsonify({"error": "Commande a deux positions introuvable"}), 404

    return jsonify({
        "id": normalized_on_id,
        "on": command_states.get(get_toggle_state_key(normalized_on_id), False),
    })


def decode_tm(frame):
    try:
        decoder = FrameDecoder(get_active_satellite().decoder)
        frame_data = decoder.decode_frame(frame)
        if frame_data is None or not decoder.is_telemetry(frame_data):
            return None
        return decoder.decode_telemetry(frame_data["data"])
    except RuntimeError:
        return None


def store_satellite_frame(frame, values=None, frame_type="UNKNOWN", direction="RX"):
    satellite_data_history.appendleft({
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"),
        "raw": frame,
        "values": values or {},
        "type": frame_type,
        "direction": direction,
    })


# def read_radio():

#     while True:

#         frame = radio.readline().decode().strip()

#         if frame == "":
#             continue


#         print("RX :", frame)


#         # =========================
#         # ACK reçu
#         # =========================
#         if "|ACK|" in frame:

#             print("ACK reçu :", frame)

#             continue


#         # =========================
#         # TM reçu
#         # =========================
#         values = decode_tm(frame)

#         if values is None:
#             continue


#         timestamp=datetime.now()

#         timestamp_str=timestamp.strftime("%Y-%m-%d %H:%M:%S")

#         data_store["time"].append(timestamp_str)

#         # Enregistrer chaque parametre de la trame dans SQLite.
#         try:
#             with app.app_context():
#                 for key, value in values.items():
#                     telemetry = Telemetry(
#                         key=str(key).lower(),
#                         value=str(value),
#                         timestamp=timestamp
#                     )
#                     db.session.add(telemetry)
#                 db.session.commit()
#         except Exception as error:
#             db.session.rollback()
#             print("DB serial save error:", error)


#         for key,value in values.items():

#             key=key.lower()

#             if key not in data_store:
#                 data_store[key]=[]

#             data_store[key].append(float(value))
def read_radio():
    while radio is not None:
        try:
            frame = radio.readline().decode(errors="ignore").strip()
        except (serial.SerialException, OSError):
            return

        if frame == "":
            continue

        print("RX :", frame)

        # =========================
        # ACK reçu
        # =========================
        decoder = FrameDecoder(get_active_satellite().decoder)
        frame_data = decoder.decode_frame(frame)
        if frame_data is None:
            store_satellite_frame(frame, frame_type="RAW")
            continue

        frame_type = frame_data.get("type") or "UNKNOWN"
        if decoder.is_ack(frame_data):
            print("ACK reçu :", frame)
            store_satellite_frame(frame, frame_type=frame_type)
            continue

        # =========================
        # TM reçu
        # =========================
        values = decode_tm(frame)

        if values is None:
            store_satellite_frame(frame, frame_type=frame_type)
            continue

        store_satellite_frame(frame, values=values, frame_type=frame_type)

        for key, value in values.items():
            if str(key).strip().lower() != "status":
                continue

            try:
                mission_status = int(float(value))
            except (TypeError, ValueError):
                break

            if 1 <= mission_status <= 6:
                data_store2["status"] = mission_status
            break

        # =========================
        # DATE / HEURE
        # =========================
        timestamp = datetime.now()

        timestamp_str = timestamp.strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        # =========================
        # STOCKAGE POUR LE GRAPHIQUE
        # =========================
        data_store["time"].append(timestamp_str)

        # =========================
        # STOCKAGE SQLITE
        # Organisation :
        # Année -> Mois -> Jour -> Telemetry
        # =========================
        try:

            with app.app_context():

                # Trouver ou créer le jour
                day = get_or_create_day(timestamp)

                # Enregistrer chaque paramètre
                for key, value in values.items():

                    telemetry = Telemetry(
                        day_id=day.id,
                        key=str(key).lower(),
                        value=str(value),
                        timestamp=timestamp
                    )

                    db.session.add(telemetry)

                db.session.commit()

        except Exception as error:

            db.session.rollback()

            print(
                "DB serial save error:",
                error
            )

        # =========================
        # STOCKAGE POUR LE DASHBOARD
        # =========================
        for key, value in values.items():

            key = key.lower()

            if key not in data_store:
                data_store[key] = []

            try:
                data_store[key].append(float(value))
            except ValueError:
                data_store[key].append(value)

file_path = "data.txt"

# Créer un nouveau fichier data.txt vide
if os.path.exists(file_path):
    os.remove(file_path)

with open(file_path, "w") as f:
    pass

IMAGE_SAVE_DIR = os.path.join("static", "img", "esp32")
os.makedirs(IMAGE_SAVE_DIR, exist_ok=True)
os.makedirs('static', exist_ok=True)

# ==================================================
# PAGE WEB
# ==================================================
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/cmd")
def cmd():
    return render_template("cmd.html")

@app.route("/payload")
def payload():
    try:
        esp32_available = get_active_wifi_communication() is not None
    except RuntimeError:
        esp32_available = False

    return render_template("payload.html", esp32_available=esp32_available)

@app.route("/HK")
def HouseKeeping():
    try:
        profiles = load_satellite_profiles()
        satellites = [
            {"key": key, "name": profile.name}
            for key, profile in profiles.items()
        ]
    except (OSError, ValueError, KeyError, TypeError) as error:
        profiles = {}
        satellites = []
        print(f"[CONFIG] Impossible de charger satellites.json: {error}")

    return render_template(
        "HouseKeeping.html",
        satellites=satellites,
        active_satellite=active_satellite_key,
        active_satellite_name=(
            profiles[active_satellite_key].name
            if active_satellite_key in profiles
            else None
        ),
    )


@app.route("/satellite/switch", methods=["POST"])
def switch_satellite():
    """Active le profil choisi dans la liste Housekeeping."""
    global active_satellite_key

    data = request.get_json(silent=True) or {}
    satellite_key = str(data.get("satellite", "")).lower()
    profiles = load_satellite_profiles()
    profile = profiles.get(satellite_key)
    if profile is None:
        return jsonify({"error": "Profil satellite introuvable"}), 400

    previous_satellite_key = active_satellite_key
    active_satellite_key = satellite_key
    try:
        configure_selected_communication(profile)
    except (serial.SerialException, OSError, RuntimeError) as error:
        active_satellite_key = previous_satellite_key
        return jsonify({"error": f"Impossible de configurer {profile.name} : {error}"}), 500

    return jsonify({
        "message": f"Profil actif : {profile.name}",
        "key": satellite_key,
        "camera_enabled": profile.camera_enabled,
        "commands": profile.available_commands,
    })


@app.route("/commands")
def get_commands():
    """Retourne la liste des commandes (id + label) du profil actif, pour affichage dynamique."""
    try:
        profile = get_active_satellite()
    except RuntimeError as error:
        return jsonify({"error": str(error)}), 400

    return jsonify({"commands": profile.available_commands})


@app.route("/send_command", methods=["POST"])
def send_command():
    """Envoie une commande générique identifiée par son id, tel que défini dans satellites.json."""
    data = request.get_json(silent=True) or {}
    command_id = str(data.get("id", "")).strip().upper()
    if not command_id:
        return jsonify({"error": "Identifiant de commande manquant"}), 400

    try:
        frame = send_tc(command_id)
    except RuntimeError as error:
        return jsonify({"error": str(error)}), 500

    # Met a jour l'etat de chaque commande a deux positions du profil actif.
    try:
        profile = get_active_satellite()
        for entry in profile.available_commands:
            on_id = entry.get("on_id", "").upper()
            off_id = entry.get("off_id", "").upper()
            if command_id == on_id:
                command_states[get_toggle_state_key(on_id)] = True
            elif command_id == off_id:
                command_states[get_toggle_state_key(on_id)] = False
    except RuntimeError:
        pass

    logs_history.append({
        "type": "CMD",
        "message": f"Commande {command_id} envoyée"
    })

    return jsonify({
        "message": f"Commande {command_id} envoyée",
        "trame": frame,
        "id": command_id
    })

@app.route("/tracking")
def tracking():
    return render_template("tracking.html")
# ==================================================
# RECEPTION DONNEES ESP32 (WiFi POST JSON)
# ==================================================
# @app.route("/data", methods=["POST"])
# def receive_data():
#     print("Raw data :")
#     print(request.data)
#     data = request.json
#     print("date ", data)
    
#     timestamp = datetime.now()
#     timestamp_str = timestamp.strftime("%Y-%m-%d %H:%M:%S.%f")

#     # Ajouter "time" au data_store si pas déjà présent
#     if "time" not in data_store:
#         data_store["time"] = []
    
#     # Stocker le timestamp complet de réception en heure locale
#     data_store["time"].append(timestamp_str)
    
#     # === CRÉATION AUTOMATIQUE DES PARAMÈTRES ===
#     # Itérer sur tous les paramètres reçus du JSON
#     for key, value in data.items():
#         # Créer la liste pour ce paramètre s'il n'existe pas
#         if key not in data_store:
#             data_store[key] = []
#             print(f"[+] Nouveau parametre cree: {key}")
        
#         # Ajouter la valeur
#         data_store[key].append(value)
    
#     # Stocker le status
#     data_store2["status"] = data.get("status", 0)

#     # Enregistrement dans la base SQLite
#     try:
#         for key, value in data.items():
#             telemetry = Telemetry(key=str(key), value=str(value), timestamp=timestamp)
#             db.session.add(telemetry)
#         db.session.commit()
#     except Exception as e:
#         db.session.rollback()
#         print("DB save error:", e)

#     # === ÉCRITURE FICHIER data.txt (FORMAT SIMPLE) ===
#     # Format: YYYY-MM-DD HH:MM:SS.ffffff param:value param:value ...
#     with open(file_path, "a") as f:
#         line_parts = [timestamp_str]
        
#         # Ajouter tous les paramètres avec leurs noms
#         for key in sorted(data.keys()):
#             line_parts.append(f"{key}:{data[key]}")
        
#         line = " ".join(line_parts)
#         f.write(line + "\n")

#     print("Reçu ESP32:", data)

#     return jsonify({"status": "ok"})

@app.route("/data", methods=["POST"])
def receive_data():

    print("Raw data :")
    print(request.data)

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Le corps de la requête doit être un objet JSON"}), 400

    # Le dashboard utilise des clés normalisées, quel que soit le satellite.
    data = {
        str(key).strip().lower(): value
        for key, value in data.items()
        if str(key).strip()
    }

    print("data :", data)

    # Conserver une copie exploitable pour le panneau de télémétrie.
    store_satellite_frame(request.get_data(as_text=True), data)

    # =========================
    # DATE / HEURE
    # =========================
    timestamp = datetime.now()

    timestamp_str = timestamp.strftime(
        "%Y-%m-%d %H:%M:%S.%f"
    )

    # =========================
    # STOCKAGE POUR LE DASHBOARD
    # =========================

    if "time" not in data_store:
        data_store["time"] = []

    data_store["time"].append(timestamp_str)

    # =========================
    # CREATION DES PARAMETRES
    # =========================

    for key, value in data.items():

        if key not in data_store:

            data_store[key] = []

            print(
                f"[+] Nouveau parametre cree: {key}"
            )

        data_store[key].append(value)

    # =========================
    # STATUS
    # =========================

    data_store2["status"] = data.get(
        "status",
        0
    )

    # =========================
    # STOCKAGE SQLITE
    # Organisation :
    # Année -> Mois -> Jour -> Telemetry
    # =========================

    try:

        # Trouver ou créer le jour
        day = get_or_create_day(timestamp)

        # Enregistrer chaque paramètre
        for key, value in data.items():

            telemetry = Telemetry(
                day_id=day.id,
                key=str(key).lower(),
                value=str(value),
                timestamp=timestamp
            )

            db.session.add(telemetry)

        db.session.commit()

    except Exception as error:

        db.session.rollback()

        print(
            "DB save error:",
            error
        )

    # =========================
    # ECRITURE data.txt
    # =========================

    try:

        with open(file_path, "a") as f:

            line_parts = [timestamp_str]

            for key in sorted(data.keys()):

                line_parts.append(
                    f"{key}:{data[key]}"
                )

            line = " ".join(line_parts)

            f.write(line + "\n")

    except Exception as error:

        print(
            "data.txt error:",
            error
        )

    print(
        "Reçu ESP32:",
        data
    )

    return jsonify({
        "status": "ok"
    })
# ==================================================
# GET DATA (dashboard Angular / web)
# ==================================================
@app.route("/data", methods=["GET"])
def get_data():
    return jsonify(data_store)


@app.route("/satellite_data", methods=["GET"])
def get_satellite_data():
    parameter = request.args.get("parameter", "all").strip().lower()
    if parameter in {"", "all", "tous", "tout"}:
        parameters = []
        frames = list(satellite_data_history)
    else:
        parameters = [item.strip() for item in parameter.replace(";", ",").split(",") if item.strip()]
        frames = [
            frame for frame in satellite_data_history
            if any(item in frame["values"] for item in parameters)
        ]

    return jsonify({
        "parameter": parameter,
        "parameters": parameters,
        "count": len(frames),
        "frames": frames,
    })


logs_history = []
@app.route("/logs")
def logs():
    return jsonify(logs_history)
# ==================================================
# CAM ON (HTTP → ESP32)
# ==================================================
def save_esp32_image(response, prefix="esp32"):
    content_type = response.headers.get("Content-Type", "").lower()
    image_bytes = None
    extension = "jpg"

    if "application/json" in content_type:
        payload = response.json()
        image_data = payload.get("image") or payload.get("data")
        if not image_data:
            raise ValueError("No image data found in JSON response")

        image_bytes = base64.b64decode(image_data)
        extension = payload.get("extension", "jpg").lower()
    else:
        image_bytes = response.content
        if not image_bytes:
            raise ValueError("No image bytes found in response")

        if "jpeg" in content_type or "jpg" in content_type:
            extension = "jpg"
        elif "png" in content_type:
            extension = "png"
        elif "gif" in content_type:
            extension = "gif"
        elif "bmp" in content_type:
            extension = "bmp"
        elif "webp" in content_type:
            extension = "webp"

    if not image_bytes:
        raise ValueError("Image data is empty or invalid")

    detected = imghdr.what(None, h=image_bytes)
    if detected:
        if detected == "jpeg":
            detected = "jpg"
        extension = detected
    elif extension not in ("jpg", "jpeg", "png", "gif", "bmp", "webp"):
        raise ValueError("Unable to determine valid image format")

    filename = datetime.now().strftime(f"{prefix}_%Y%m%d_%H%M%S.") + extension
    save_path = os.path.join(IMAGE_SAVE_DIR, filename)

    with open(save_path, "wb") as f:
        f.write(image_bytes)

    return filename, image_bytes

@app.route("/status")
def status():
    return jsonify({"status": data_store2["status"]})

@app.route('/esp32_ip', methods=['GET', 'POST'])
def esp32_ip():
    try:
        communication = get_active_wifi_communication()
    except RuntimeError as error:
        return jsonify({"message": str(error)}), 400

    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        new_ip = data.get('ip') if isinstance(data, dict) else None
        if not new_ip:
            return jsonify({"message": "No IP provided."}), 400

        with PROFILES_FILE.open(encoding="utf-8") as profiles_file:
            profiles = json.load(profiles_file)
        profiles[active_satellite_key]["communication"]["host"] = new_ip.strip()
        with PROFILES_FILE.open("w", encoding="utf-8") as profiles_file:
            json.dump(profiles, profiles_file, indent=2, ensure_ascii=False)

        return jsonify({"message": "Adresse WiFi mise à jour dans satellites.json.", "ip": new_ip.strip()})
    return jsonify({"ip": communication.host})


# ==================================================
# Capture endpoints (upload from ESP32 / trigger capture)
# ==================================================


@app.route('/capture', methods=['POST', 'GET'])
def capture():
    """Trigger the ESP32 to take a picture (GET/POST) and return capture metadata."""
    try:
        communication = get_active_wifi_communication()
    except RuntimeError as error:
        return jsonify({"message": str(error)}), 400

    host = communication.host
    url = f"http://{host}:{communication.port_wifi or 80}/capture"
    attempted_urls = [url]
    try:
        r = requests.get(url, timeout=communication.timeout_wifi or 15)
        r.raise_for_status()

        if not r.content:
            raise ValueError("No image content returned from ESP32.")

        saved_file, image_bytes = save_esp32_image(r, prefix="Capture")
        latest_path = os.path.join('static', 'Derniere_Capture.jpg')

        with open(latest_path, 'wb') as f:
            f.write(image_bytes)

        return jsonify({
            "message": "Capture saved",
            "saved_image": saved_file,
            "image_url": url_for('static', filename=f'img/esp32/{saved_file}'),
            "ip": host,
            "attempted_url": url
        })
    except requests.exceptions.RequestException as e:
        error_msg = f"{type(e).__name__}: {e}"
        print(f"capture attempt failed for {url}:", error_msg)
        return jsonify({
            "message": "ERROR ESP32",
            "error": error_msg,
            "ip": host,
            "attempted_urls": attempted_urls
        }), 500
    except Exception as e:
        error_msg = f"{type(e).__name__}: {e}"
        print(f"capture processing failed for {url}:", error_msg)
        return jsonify({
            "message": "ERROR ESP32",
            "error": error_msg,
            "ip": host,
            "attempted_urls": attempted_urls
        }), 500


@app.route('/upload', methods=['POST'])
def upload():
    """Endpoint for ESP32 to POST raw image bytes. Saves archive and latest file."""
    data = request.data
    if not data:
        return "No data received", 400

    detected = imghdr.what(None, h=data)
    if not detected:
        return "Invalid image data", 400
    if detected == "jpeg":
        detected = "jpg"

    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"Capture_{timestamp}.{detected}"
        archive_path = os.path.join(IMAGE_SAVE_DIR, filename)
        with open(archive_path, 'wb') as f:
            f.write(data)

        latest_path = os.path.join('static', 'Derniere_Capture.jpg')
        with open(latest_path, 'wb') as f:
            f.write(data)

        print(f"{filename} is saved.")
        return "Capture received successfully", 200
    except Exception as e:
        print(f"Error: {e}. Saving has failed.")
        return "Writing Error.", 500


@app.route('/image')
def image():
    latest_path = os.path.join('static', 'Derniere_Capture.jpg')
    if os.path.exists(latest_path):
        return send_file(latest_path, mimetype='image/jpeg')
    return "No image available", 404


@app.route('/historique')
def historique():
    files = []
    try:
        for fichier in os.listdir(IMAGE_SAVE_DIR):
            if not fichier.lower().startswith('capture_'):
                continue
            path = os.path.join(IMAGE_SAVE_DIR, fichier)
            if not os.path.isfile(path) or os.path.getsize(path) < 200:
                continue
            if not imghdr.what(path):
                continue
            files.append(fichier)
    except Exception:
        files = []

    files.sort(reverse=True)

    page = """
    <h3>Historique des captures</h3>
    <p><a href='/'>Retour</a></p>
    <div>
    """

    for image_file in files:
        url = url_for('static', filename=f'img/esp32/{image_file}')
        page += f"<div><h5>{image_file}</h5><img src=\"{url}\" style=\"max-width:300px;\"></div><hr>"

    page += "</div>"
    return page


data_store2 = {

    "latitude": 48.8566,
    "longitude": 2.3522,
    "status": 0
}

@app.route("/position")
def position():
    return jsonify({
        "latitude": data_store2["latitude"],
        "longitude": data_store2["longitude"]
    })
# ==================================================
# RUN SERVER
# ==================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)





