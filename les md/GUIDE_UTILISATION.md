"""
GUIDE D'UTILISATION - Station de base générique et modulaire

Ce fichier montre comment utiliser tous les modules pour créer
une station de base universelle adaptée à n'importe quel satellite.
"""

# ==================================================
# 1. INITIALISATION DE LA CONFIGURATION
# ==================================================

from config import get_satellite_config
from satellite_profiles import get_satellite_by_name, list_available_satellites

# Option A: Utiliser la config active par défaut
config = get_satellite_config()

# Option B: Charger un profil de satellite spécifique
# config = get_satellite_by_name("esp32_serial")
# config = get_satellite_by_name("cubesat_a")
# config = get_satellite_by_name("satellite_xyz")

print(f"Satellite actif: {config.name}")


# ==================================================
# 2. INITIALISATION DES MODULES CORE
# ==================================================

from core import (
    create_communicator,
    FrameDecoder,
    CommandFormatter,
    TelemetryManager,
    CommandManager,
    ImageManager
)
from flask import Flask

app = Flask(__name__)

# Initialiser le communicateur (série ou WiFi automatiquement)
communicator = create_communicator(config.communication)

# Initialiser le décodeur
decoder = FrameDecoder(config.decoder)

# Initialiser le formateur de commandes
cmd_formatter = CommandFormatter(config.decoder)

# Initialiser les managers
telemetry_manager = TelemetryManager(app)
command_manager = CommandManager(communicator, cmd_formatter)
image_manager = ImageManager(config.image_save_dir)


# ==================================================
# 3. EXEMPLE: CONNEXION ET COMMUNICATION
# ==================================================

def example_connect():
    """Exemple de connexion au satellite."""
    if communicator.connect():
        print("✓ Connecté au satellite")
    else:
        print("✗ Erreur de connexion")


# ==================================================
# 4. EXEMPLE: ENVOI DE COMMANDE
# ==================================================

def example_send_command():
    """Exemple d'envoi de commande."""
    # Les commandes viennent de la config
    available_cmds = config.available_commands
    
    # Envoyer une commande (universelle, pas de if/else spécifiques)
    if "CAM_ON" in available_cmds:
        command_manager.send_command(
            name="CAM_ON",
            data=available_cmds["CAM_ON"],
            cmd_id="101"
        )


# ==================================================
# 5. EXEMPLE: TRAITEMENT DES TRAMES
# ==================================================

def example_process_frame(frame_str: str):
    """Exemple de traitement générique d'une trame."""
    
    # Décoder la trame (universel)
    frame_dict = decoder.decode_frame(frame_str)
    
    if frame_dict is None:
        print("Trame invalide")
        return
    
    # Déterminer le type de trame (universel)
    if decoder.is_ack(frame_dict):
        # Accusé de réception
        command_manager.acknowledge_command(frame_dict["seq"])
    
    elif decoder.is_telemetry(frame_dict):
        # Télémétrie reçue
        from datetime import datetime
        
        timestamp = datetime.now()
        timestamp_str = timestamp.strftime("%Y-%m-%d %H:%M:%S")
        
        # Décoder les paramètres (universel)
        parameters = decoder.decode_telemetry(frame_dict["data"])
        
        if parameters:
            # Stocker en base de données (universel)
            telemetry_manager.store_telemetry(timestamp, parameters)
            
            # Ajouter au dashboard (universel)
            telemetry_manager.add_to_dashboard(parameters)
            telemetry_manager.add_timestamp(timestamp_str)
            
            print(f"✓ {len(parameters)} paramètres enregistrés")


# ==================================================
# 6. EXEMPLE: BOUCLE DE RÉCEPTION (générique)
# ==================================================

def read_satellite_data():
    """
    Boucle de réception généralisée.
    Fonctionne avec n'importe quel satellite grâce aux modules génériques.
    """
    import threading
    
    def reader_thread():
        while True:
            # Recevoir une trame (générique)
            frame = communicator.receive(timeout=config.communication.timeout)
            
            if frame is None:
                continue
            
            # Traiter la trame (générique)
            example_process_frame(frame)
    
    # Lancer la lecture en arrière-plan
    thread = threading.Thread(target=reader_thread, daemon=True)
    thread.start()


# ==================================================
# 7. EXEMPLE: ENDPOINTS FLASK (génériques)
# ==================================================

@app.route("/data", methods=["GET"])
def get_data():
    """Récupère les données du dashboard (générique)."""
    from flask import jsonify
    return jsonify(telemetry_manager.get_data_store())


@app.route("/command/send", methods=["POST"])
def send_cmd():
    """Envoie une commande (générique)."""
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
    """Retourne l'historique des commandes (générique)."""
    from flask import jsonify
    return jsonify(command_manager.get_commands_history())


@app.route("/images/latest", methods=["GET"])
def latest_image():
    """Retourne la dernière image capturée (générique)."""
    from flask import send_file
    import os
    
    latest_path = image_manager.get_latest_image_path()
    if os.path.exists(latest_path):
        return send_file(latest_path, mimetype='image/jpeg')
    return "Pas d'image", 404


@app.route("/images/history", methods=["GET"])
def images_history():
    """Retourne l'historique des images (générique)."""
    from flask import jsonify
    files = image_manager.get_image_history(limit=50)
    return jsonify({"images": files})


# ==================================================
# 8. EXEMPLE: CHANGER DE SATELLITE À L'EXÉCUTION
# ==================================================

def switch_to_satellite(sat_name: str):
    """Permet de changer de satellite sans redémarrer."""
    from config import switch_satellite
    from satellite_profiles import get_satellite_by_name
    
    new_config = get_satellite_by_name(sat_name)
    if new_config:
        switch_satellite(new_config)
        
        # Réinitialiser les communicateurs
        communicator.disconnect()
        # Les modules se mettront à jour automatiquement
        
        print(f"Satellite changé à: {sat_name}")
    else:
        print(f"Satellite '{sat_name}' non trouvé")


# ==================================================
# 9. AVANTAGES DE CETTE ARCHITECTURE
# ==================================================

"""
✓ UNIVERSEL: Fonctionne avec n'importe quel satellite
✓ CONFIGURABLE: Pas besoin de modifier le code pour changer de satellite
✓ MODULAIRE: Chaque partie est indépendante et testable
✓ EXTENSIBLE: Facile d'ajouter de nouvelles fonctionnalités
✓ MAINTENABLE: Code clair et bien organisé
✓ RÉUTILISABLE: Tous les modules peuvent être importés ailleurs

ÉLÉMENTS RENDENT GÉNÉRIQUES:
- Décodage de trames (format configurable)
- Communication (série, WiFi, ou autre)
- Gestion des commandes (universel)
- Gestion des télémétries (universel)
- Stockage des images (universel)
- Endpoints Flask (utilise la config)

POUR AJOUTER UN NOUVEAU SATELLITE:
1. Créer un nouveau profil dans satellite_profiles.py
2. Définir la communication (série/WiFi)
3. Définir le décodage (format des trames)
4. Tout le reste fonctionne automatiquement!
"""
