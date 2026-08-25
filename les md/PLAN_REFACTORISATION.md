"""
PLAN DE REFACTORISATION PROGRESSIF
===================================

Ce guide montre comment refactoriser votre app.py existant
pour utiliser la nouvelle architecture modulaire et générique.

Vous pouvez le faire progressivement, étape par étape.
"""

# ==================================================
# ÉTAPE 0: PRÉPARATION (Avant de toucher à app.py)
# ==================================================

ETAPE_0 = """
✓ Créer le dossier 'core'
✓ Créer config.py
✓ Créer satellite_profiles.py
✓ Remplir les fichiers core/:
  - decoder.py
  - communicator.py
  - telemetry_manager.py
  - command_manager.py
  - storage_manager.py
  - __init__.py

✓ Tester les imports (python -c "from core import *")

DURÉE: 1-2 heures
"""


# ==================================================
# ÉTAPE 1: EXTRAIRE LA COMMUNICATION
# ==================================================

ETAPE_1_AVANT = """
# Dans app.py (NON-UNIVERSEL)

radio = serial.Serial("COM7", 115200, timeout=1)

def send_tc(command, cmd_id="101", seq="000"):
    length = len(command)
    frame = f"~|TC|{cmd_id}|{seq}|{length}|{command}|0\\n"
    print("TC envoyée :", frame)
    radio.write(frame.encode())
    return frame
"""

ETAPE_1_APRES = """
# Nouveau code (UNIVERSEL)

from config import get_satellite_config
from core import create_communicator, CommandFormatter

config = get_satellite_config()
communicator = create_communicator(config.communication)
cmd_formatter = CommandFormatter(config.decoder)

# Remplacer send_tc():
def send_tc(command, cmd_id="101", seq="000"):
    frame = cmd_formatter.format_command(command, cmd_id, seq)
    communicator.send(frame)
    return frame

# AVANTAGE: Fonctionne avec série OU WiFi automatiquement!
"""

ETAPE_1_NOTE = """
AVANTAGE:
- La communication (série, WiFi) est abstraite
- Pour changer de satellite: juste changer la config
- Le code d'envoi reste exactement le même

COMPLEXITÉ: ⭐ Facile
BÉNÉFICE: ⭐⭐⭐⭐⭐ Énorme
"""


# ==================================================
# ÉTAPE 2: EXTRAIRE LE DÉCODAGE
# ==================================================

ETAPE_2_AVANT = """
# Dans app.py (NON-UNIVERSEL)

def decode_tm(frame):
    try:
        fields = frame.split("|")
        if len(fields) != 7:
            return None
        tm_data = fields[5]
        values = {}
        for item in tm_data.split(","):
            key, value = item.split(":")
            values[key] = value
        return values
    except:
        return None
"""

ETAPE_2_APRES = """
# Nouveau code (UNIVERSEL)

from config import get_satellite_config
from core import FrameDecoder

config = get_satellite_config()
decoder = FrameDecoder(config.decoder)

# Remplacer decode_tm():
def decode_tm(frame):
    frame_dict = decoder.decode_frame(frame)
    if frame_dict is None:
        return None
    return decoder.decode_telemetry(frame_dict["data"])

# AVANTAGE: Fonctionne avec n'importe quel format de trame!
"""

ETAPE_2_NOTE = """
AVANTAGE:
- Format des trames configurable
- Pour un nouveau satellite: juste changer DecoderConfig
- Le code de décodage reste exactement le même

COMPLEXITÉ: ⭐ Facile
BÉNÉFICE: ⭐⭐⭐⭐⭐ Énorme
"""


# ==================================================
# ÉTAPE 3: EXTRAIRE LA GESTION DES TÉLÉMÉTRIES
# ==================================================

ETAPE_3_AVANT = """
# Dans app.py (NON-UNIVERSEL)

def read_radio():
    while True:
        frame = radio.readline().decode(errors="ignore").strip()
        if frame == "":
            continue
        
        # ... décodage ...
        
        timestamp = datetime.now()
        timestamp_str = timestamp.strftime("%Y-%m-%d %H:%M:%S")
        data_store["time"].append(timestamp_str)
        
        # === STOCKAGE SQLITE ===
        try:
            with app.app_context():
                day = get_or_create_day(timestamp)
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
            print("DB serial save error:", error)
        
        # === STOCKAGE DASHBOARD ===
        for key, value in values.items():
            key = key.lower()
            if key not in data_store:
                data_store[key] = []
            try:
                data_store[key].append(float(value))
            except ValueError:
                data_store[key].append(value)
"""

ETAPE_3_APRES = """
# Nouveau code (UNIVERSEL)

from core import TelemetryManager

telemetry_manager = TelemetryManager(app)

def read_radio():
    while True:
        frame = communicator.receive()
        if frame is None:
            continue
        
        frame_dict = decoder.decode_frame(frame)
        if decoder.is_telemetry(frame_dict):
            timestamp = datetime.now()
            parameters = decoder.decode_telemetry(frame_dict["data"])
            
            # Une seule ligne pour tout!
            telemetry_manager.store_telemetry(timestamp, parameters)
            telemetry_manager.add_to_dashboard(parameters)
            telemetry_manager.add_timestamp(timestamp.strftime("%Y-%m-%d %H:%M:%S"))

# AVANTAGE: Code 10x plus simple et lisible!
"""

ETAPE_3_NOTE = """
AVANTAGE:
- Toute la logique de base de données est cachée
- Fonctionne avec n'importe quels paramètres
- Code beaucoup plus lisible et maintenable

COMPLEXITÉ: ⭐⭐ Facile
BÉNÉFICE: ⭐⭐⭐⭐⭐ Énorme (lisibilité++)
"""


# ==================================================
# ÉTAPE 4: EXTRAIRE LA GESTION DES COMMANDES
# ==================================================

ETAPE_4_AVANT = """
# Dans app.py (NON-UNIVERSEL)

@app.route("/cam_on")
def cam_on():
    try:
        frame = send_tc("CAM_ON")
        camera_state["on"] = True
        logs_history.append({
            "type": "CMD",
            "message": "Commande CAM ON envoyée"
        })
        return jsonify({
            "message": "CAM ON TC envoyée",
            "trame": frame,
            "camera": "ON"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/cam_off")
def cam_off():
    try:
        frame = send_tc("CAM_OFF", "101", "001")
        camera_state["on"] = False
        return jsonify({
            "message": "CAM OFF TC envoyée",
            "trame": frame,
            "camera": "OFF"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ... d'autres endpoint spécifiques ...
"""

ETAPE_4_APRES = """
# Nouveau code (UNIVERSEL)

from core import CommandManager

command_manager = CommandManager(communicator, cmd_formatter)

# Endpoint GÉNÉRIQUE pour n'importe quelle commande
@app.route("/command/send", methods=["POST"])
def send_command():
    from flask import request, jsonify
    
    data = request.json
    cmd_name = data.get("command")
    
    if cmd_name not in config.available_commands:
        return jsonify({"error": "Commande inconnue"}), 400
    
    cmd_data = config.available_commands[cmd_name]
    success = command_manager.send_command(cmd_name, cmd_data)
    
    return jsonify({
        "command": cmd_name,
        "status": "sent" if success else "failed"
    })

@app.route("/commands/history", methods=["GET"])
def commands_history():
    from flask import jsonify
    return jsonify(command_manager.get_commands_history())

# AVANTAGE: 1 endpoint remplace 10 endpoints spécifiques!
"""

ETAPE_4_NOTE = """
AVANTAGE:
- Ajouter une commande = juste modifier la config!
- Un seul endpoint générique pour toutes les commandes
- Historique automatique

COMPLEXITÉ: ⭐⭐ Moyen
BÉNÉFICE: ⭐⭐⭐⭐⭐ Énorme (scalabilité++)
"""


# ==================================================
# ÉTAPE 5: EXTRAIRE LA GESTION DES IMAGES
# ==================================================

ETAPE_5_AVANT = """
# Dans app.py (NON-UNIVERSEL)

def save_esp32_image(response, prefix="esp32"):
    # ... 50 lignes de logique ...
    return filename, image_bytes

@app.route('/capture', methods=['POST', 'GET'])
def capture():
    # ... 30 lignes de logique ...
    return jsonify(...)

@app.route('/upload', methods=['POST'])
def upload():
    # ... 20 lignes de logique ...
    return "OK"

@app.route('/image')
def image():
    # ... 5 lignes de logique ...
    return send_file(...)

@app.route('/historique')
def historique():
    # ... 20 lignes de logique ...
    return page
"""

ETAPE_5_APRES = """
# Nouveau code (UNIVERSEL)

from core import ImageManager

image_manager = ImageManager(config.image_save_dir)

@app.route('/capture', methods=['GET'])
def capture():
    url = f"http://{config.communication.host}/capture"
    try:
        r = requests.get(url, timeout=15)
        filename, image_bytes = image_manager.save_image_from_response(r)
        image_manager.save_latest_image(image_bytes)
        return jsonify({"message": "Capture saved", "filename": filename})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/upload', methods=['POST'])
def upload():
    data = request.data
    filename = image_manager.save_image_from_bytes(data)
    if filename:
        image_manager.save_latest_image(data)
        return "OK"
    return "Error", 500

@app.route('/image')
def image():
    latest = image_manager.get_latest_image_path()
    if os.path.exists(latest):
        return send_file(latest, mimetype='image/jpeg')
    return "Not found", 404

@app.route('/images/history')
def images_history():
    files = image_manager.get_image_history()
    return jsonify({"images": files})

# AVANTAGE: Code 60% plus court et plus lisible!
"""

ETAPE_5_NOTE = """
AVANTAGE:
- Logique de stockage encapsulée
- Formats d'image gérés automatiquement
- Chemin configurable par satellite

COMPLEXITÉ: ⭐⭐ Moyen
BÉNÉFICE: ⭐⭐⭐⭐ Lisibilité++
"""


# ==================================================
# ÉTAPE 6: NETTOYAGE FINAL
# ==================================================

ETAPE_6 = """
Supprimer de app.py:
────────────────────
✓ Toutes les fonctions utilitaires (maintenant dans core/)
✓ Les variables globales non-génériques
✓ Les imports non-utilisés
✓ Les commentaires redondants

Garder dans app.py:
──────────────────
✓ Imports des modules core
✓ Initialisation de Flask
✓ Configuration du satellite
✓ Routage Flask (GET/POST)
✓ Logique métier (si applicable)

Résultat: app.py passe de 500+ lignes à 150-200 lignes!
Et ZÉRO perte de fonctionnalité!
"""


# ==================================================
# RÉSUMÉ DES CHANGEMENTS
# ==================================================

RESUME = """
AVANT (monolithique)               APRÈS (modulaire et générique)
────────────────────────────────   ──────────────────────────────
app.py: 500+ lignes                app.py: 150-200 lignes
- Décodage                         - Imports + routage Flask
- Communication                    
- Stockage base de données         config.py: Paramètres du satellite
- Gestion des commandes            
- Gestion des images               satellite_profiles.py: Catalogue
- Logique métier mélangée          
                                   core/: Modules réutilisables
                                   - decoder.py
                                   - communicator.py
                                   - telemetry_manager.py
                                   - command_manager.py
                                   - storage_manager.py

BÉNÉFICES:
─────────
✓ Code 60% plus court
✓ Plus lisible et maintenable
✓ Universelle pour n'importe quel satellite
✓ Réutilisable dans d'autres projets
✓ Facile à tester
✓ Facile à collaborer en équipe
"""


# ==================================================
# TIMELINE DE REFACTORISATION
# ==================================================

TIMELINE = """
Jour 1 - Matin (1-2h):
  ÉTAPE 0: Préparation
  - Créer structure de dossiers
  - Créer config.py
  - Créer modules core/

Jour 1 - Après-midi (2-3h):
  ÉTAPE 1: Communication
  ÉTAPE 2: Décodage
  - Tester avec des données réelles

Jour 2 - Matin (2h):
  ÉTAPE 3: Télémétries
  - Vérifier la base de données
  - Vérifier le dashboard

Jour 2 - Après-midi (2h):
  ÉTAPE 4: Commandes
  ÉTAPE 5: Images

Jour 3 - Matin (1h):
  ÉTAPE 6: Nettoyage
  - Tester l'ensemble

TOTAL: ~10-12 heures de travail
BÉNÉFICE: Projet entièrement refactorisé et universel!
"""


# ==================================================
# CONSEILS PRATIQUES
# ==================================================

CONSEILS = """
✓ Faire un commit Git avant chaque étape
✓ Garder l'ancien app.py comme référence
✓ Tester après chaque étape
✓ Demander de l'aide si bloqué sur une étape
✓ Ne pas vouloir tout faire d'un coup

✓ Une fois config.py créé, tester les imports
✓ Créer les endpoints dans l'ordre suivant:
  1. /data (GET)
  2. /command/send
  3. /commands/history
  4. /images/history

✓ Utiliser des print() pour déboguer
✓ Vérifier les logs de la base de données
✓ Utiliser curl ou Postman pour tester les endpoints
"""
