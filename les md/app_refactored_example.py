"""
EXEMPLE: app.py refactorisé et modulaire
=========================================

Ce fichier montre à quoi ressemblerait votre app.py après refactorisation.
Compare avec votre app.py actuel pour voir les différences!
"""

from flask import Flask, request, jsonify, render_template, send_file
from datetime import datetime
import os
import threading

# ==================================================
# 1. IMPORTS DE CONFIGURATION
# ==================================================

from config import get_satellite_config
from satellite_profiles import get_satellite_by_name

# ==================================================
# 2. IMPORTS DES MODULES CORE (Universels)
# ==================================================

from core import (
    create_communicator,
    FrameDecoder,
    CommandFormatter,
    TelemetryManager,
    CommandManager,
    ImageManager
)

# ==================================================
# 3. IMPORTS DES MODÈLES
# ==================================================

from models import db

# ==================================================
# 4. INITIALISATION FLASK
# ==================================================

app = Flask(__name__)

# Configuration de la base de données
config = get_satellite_config()
db_path = os.path.join(config.database_dir, config.database_file)
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)
with app.app_context():
    db.create_all()

# ==================================================
# 5. INITIALISATION DES MODULES CORE
# ==================================================

# Communication (série, WiFi, etc.)
communicator = create_communicator(config.communication)
communicator.connect()

# Décodage des trames
decoder = FrameDecoder(config.decoder)

# Formatage des commandes
cmd_formatter = CommandFormatter(config.decoder)

# Managers universels
telemetry_manager = TelemetryManager(app)
command_manager = CommandManager(communicator, cmd_formatter)
image_manager = ImageManager(config.image_save_dir)

# ==================================================
# 6. BOUCLE DE RÉCEPTION (Universelle)
# ==================================================

def read_satellite_data():
    """
    Boucle de réception générique.
    Fonctionne avec n'importe quel satellite!
    """
    while True:
        try:
            # Recevoir une trame (générique)
            frame = communicator.receive(timeout=config.communication.timeout)
            
            if frame is None:
                continue
            
            # Décoder la trame (générique)
            frame_dict = decoder.decode_frame(frame)
            
            if frame_dict is None:
                continue
            
            # === Traiter les ACK ===
            if decoder.is_ack(frame_dict):
                command_manager.acknowledge_command(frame_dict["seq"])
                continue
            
            # === Traiter les télémétries ===
            if decoder.is_telemetry(frame_dict):
                timestamp = datetime.now()
                timestamp_str = timestamp.strftime("%Y-%m-%d %H:%M:%S")
                
                # Décoder les paramètres (générique)
                parameters = decoder.decode_telemetry(frame_dict["data"])
                
                if parameters:
                    # Stocker en base de données (générique)
                    telemetry_manager.store_telemetry(timestamp, parameters)
                    
                    # Ajouter au dashboard (générique)
                    telemetry_manager.add_to_dashboard(parameters)
                    telemetry_manager.add_timestamp(timestamp_str)
                    
                    print(f"[DATA] {len(parameters)} paramètres enregistrés")
        
        except Exception as e:
            print(f"[ERROR] {e}")
            import time
            time.sleep(1)

# Lancer la lecture en arrière-plan
threading.Thread(target=read_satellite_data, daemon=True).start()

# ==================================================
# 7. ROUTES FLASK (Génériques et simples)
# ==================================================

# === Dashboard ===
@app.route("/")
def index():
    """Page d'accueil."""
    return render_template("index.html")

@app.route("/cmd")
def cmd_page():
    """Page de commandes."""
    return render_template("cmd.html")

@app.route("/payload")
def payload_page():
    """Page de charge utile."""
    return render_template("payload.html")

@app.route("/HK")
def housekeeping_page():
    """Page de gestion de la maison."""
    return render_template("HouseKeeping.html")

@app.route("/tracking")
def tracking_page():
    """Page de suivi."""
    return render_template("tracking.html")

# === Données ===
@app.route("/data", methods=["GET"])
def get_data():
    """
    Retourne les données du dashboard.
    Générique pour tous les satellites!
    """
    return jsonify(telemetry_manager.get_data_store())

# === Commandes ===
@app.route("/command/send", methods=["POST"])
def send_command():
    """
    Envoie une commande au satellite.
    Générique pour tous les satellites!
    
    Exemple: POST /command/send
    {
        "command": "CAM_ON"
    }
    """
    try:
        data = request.json
        cmd_name = data.get("command")
        
        # Vérifier que la commande existe dans la config
        if cmd_name not in config.available_commands:
            available = list(config.available_commands.keys())
            return jsonify({
                "error": f"Commande inconnue",
                "available": available
            }), 400
        
        # Envoyer la commande (universel)
        cmd_data = config.available_commands[cmd_name]
        success = command_manager.send_command(cmd_name, cmd_data)
        
        return jsonify({
            "command": cmd_name,
            "status": "sent" if success else "failed"
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/commands/history", methods=["GET"])
def commands_history():
    """
    Retourne l'historique des commandes.
    Générique pour tous les satellites!
    """
    limit = request.args.get("limit", 100, type=int)
    return jsonify({
        "history": command_manager.get_commands_history(limit)
    })

# === Télémétries ===
@app.route("/telemetry/by-date/<date_str>", methods=["GET"])
def telemetry_by_date(date_str):
    """
    Récupère les télémétries d'une date donnée.
    Format: YYYY-MM-DD
    """
    try:
        telemetries = telemetry_manager.get_telemetry_by_date(date_str)
        result = [
            {
                "key": t.key,
                "value": t.value,
                "timestamp": t.timestamp.isoformat()
            }
            for t in telemetries
        ]
        return jsonify({"telemetries": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/telemetry/by-key/<key>/<date_str>", methods=["GET"])
def telemetry_by_key(key, date_str):
    """
    Récupère les valeurs d'un paramètre pour une date donnée.
    Format: YYYY-MM-DD
    """
    try:
        telemetries = telemetry_manager.get_telemetry_by_key(key, date_str)
        result = [
            {
                "value": t.value,
                "timestamp": t.timestamp.isoformat()
            }
            for t in telemetries
        ]
        return jsonify({"values": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# === Images ===
@app.route('/capture', methods=['GET'])
def capture():
    """
    Capture une image depuis le satellite (WiFi).
    Générique pour tous les satellites avec caméra!
    """
    if not config.camera_enabled:
        return jsonify({"error": "Caméra non activée"}), 400
    
    try:
        # Construire l'URL selon le type de communication
        if config.communication.type == "wifi":
            url = f"http://{config.communication.host}:{config.communication.port_wifi}/capture"
            import requests
            response = requests.get(url, timeout=config.communication.timeout_wifi)
            response.raise_for_status()
            
            filename, image_bytes = image_manager.save_image_from_response(
                response,
                prefix="Capture"
            )
            
            if image_bytes:
                image_manager.save_latest_image(image_bytes)
                return jsonify({
                    "message": "Capture saved",
                    "filename": filename
                })
        
        return jsonify({"error": "Caméra non disponible"}), 500
    
    except Exception as e:
        print(f"[CAPTURE] Erreur: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/upload', methods=['POST'])
def upload():
    """
    Reçoit une image depuis le satellite.
    Générique pour tous les satellites avec caméra!
    """
    if not config.camera_enabled:
        return "Camera not enabled", 400
    
    try:
        data = request.data
        if not data:
            return "No data received", 400
        
        # Sauvegarder l'image
        filename = image_manager.save_image_from_bytes(data, prefix="Capture")
        if filename:
            image_manager.save_latest_image(data)
            return "Capture received successfully", 200
        
        return "Invalid image data", 400
    
    except Exception as e:
        print(f"[UPLOAD] Erreur: {e}")
        return f"Error: {e}", 500

@app.route('/image')
def get_latest_image():
    """Retourne la dernière image capturée."""
    latest_path = image_manager.get_latest_image_path()
    if os.path.exists(latest_path):
        return send_file(latest_path, mimetype='image/jpeg')
    return "No image available", 404

@app.route('/images/history', methods=["GET"])
def images_history():
    """
    Retourne l'historique des images.
    Générique pour tous les satellites!
    """
    limit = request.args.get("limit", 50, type=int)
    files = image_manager.get_image_history(limit=limit)
    return jsonify({"images": files})

# === Configuration ===
@app.route('/satellite/info', methods=['GET'])
def satellite_info():
    """Retourne les informations du satellite actif."""
    return jsonify({
        "name": config.name,
        "communication": {
            "type": config.communication.type,
            "port": config.communication.port,
            "host": config.communication.host,
        },
        "camera_enabled": config.camera_enabled,
        "available_commands": list(config.available_commands.keys()),
    })

@app.route('/satellite/switch', methods=['POST'])
def switch_satellite_route():
    """Change le satellite actif."""
    try:
        data = request.json
        satellite_name = data.get("satellite")
        
        # Charger le nouveau profil
        new_config = get_satellite_by_name(satellite_name)
        if not new_config:
            return jsonify({"error": f"Satellite '{satellite_name}' not found"}), 400
        
        # Mettre à jour la configuration
        from config import switch_satellite
        switch_satellite(new_config)
        
        # Reconnecter le communicateur
        communicator.disconnect()
        communicator.connect()
        
        return jsonify({
            "message": f"Switched to {satellite_name}",
            "config": {
                "name": new_config.name,
                "communication": new_config.communication.type,
            }
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ==================================================
# 8. LANCEMENT DU SERVEUR
# ==================================================

if __name__ == "__main__":
    print(f"[START] Station de base: {config.name}")
    print(f"[START] Satellite: {config.name}")
    print(f"[START] Communication: {config.communication.type}")
    print(f"[START] Commandes disponibles: {list(config.available_commands.keys())}")
    print("[START] Démarrage du serveur...")
    
    app.run(host="0.0.0.0", port=5000, debug=False)

# ==================================================
# COMMENTAIRES FINAUX
# ==================================================

"""
AVANT (votre app.py actuel):
- 500+ lignes
- Logique métier mélangée
- Spécifique à l'ESP32
- Difficile à modifier
- Impossible à réutiliser

APRÈS (ce fichier):
- 250 lignes
- Code clair et modulaire
- Fonctionne avec n'importe quel satellite
- Facile à modifier
- Réutilisable

TOUT CELA GRÂCE À:
✓ config.py - Configuration centralisée
✓ core/communicator.py - Communication abstraite
✓ core/decoder.py - Décodage générique
✓ core/telemetry_manager.py - Gestion des données
✓ core/command_manager.py - Gestion des commandes
✓ core/storage_manager.py - Gestion des fichiers

Maintenant vous pouvez:
1. Changer de satellite en 1 ligne
2. Ajouter un nouveau satellite sans modifier app.py
3. Réutiliser les modules dans d'autres projets
4. Tester facilement
5. Travailler en équipe sans conflits

C'est cela que votre professeur voulait! 🎓
"""
