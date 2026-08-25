"""
Configuration centralisée pour différents satellites.
Ce fichier permet de changer rapidement entre satellites sans modifier le code.
"""

import os
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class CommunicationConfig:
    """Configuration de la communication avec le satellite."""
    
    # Type: 'serial' ou 'wifi'
    type: str
    
    # Pour série
    port: Optional[str] = None
    baudrate: Optional[int] = None
    timeout: Optional[int] = 1
    
    # Pour WiFi
    host: Optional[str] = None
    port_wifi: Optional[int] = None
    timeout_wifi: Optional[int] = 15


@dataclass
class DecoderConfig:
    """Configuration du décodage des trames."""
    
    # Délimiteurs
    frame_delimiter: str = "~"
    field_separator: str = "|"
    param_separator: str = ","
    param_keyvalue_separator: str = ":"
    
    # Indices des champs dans la trame
    frame_index: Optional[int] = None
    cmd_id_index: Optional[int] = None
    seq_index: Optional[int] = None
    length_index: Optional[int] = None
    data_index: Optional[int] = None
    checksum_index: Optional[int] = None
    checksum_value: Optional[str] = None
    closing_frame_delimiter: bool = False
    closing_delimiter: Optional[str] = None
    line_ending: str = "\n"
    
    # Types de trames
    telecommand_type: str = "TC"
    telemetry_type: str = "TM"
    ack_type: str = "ACK"


@dataclass
class SatelliteConfig:
    """Configuration complète d'un satellite."""
    
    name: str
    communication: CommunicationConfig
    decoder: DecoderConfig
    
    # Paramètres de la caméra
    camera_enabled: bool = True
    image_save_dir: str = "static/img/esp32"
    
    # Paramètres de stockage
    database_dir: str = "instance"
    database_file: str = "data.db"
    
    # Paramètres du tableau de bord
    dashboard_log_enabled: bool = True
    
    # Commandes disponibles : liste de {"id": <identifiant envoyé au satellite>, "label": <nom affiché>}
    available_commands: List[Dict[str, str]] = None
    
    def __post_init__(self):
        if self.available_commands is None:
            self.available_commands = [
                {"id": "CAM_ON", "label": "Camera ON"},
                {"id": "CAM_OFF", "label": "Camera OFF"},
                {"id": "RESET", "label": "Reset"},
                {"id": "STATUS", "label": "Status"},
            ]


# ==================================================
# PROFILS DE SATELLITES
# ==================================================

# Configuration par défaut pour ESP32
ESP32_DEFAULT = SatelliteConfig(
    name="ESP32_Default",
    communication=CommunicationConfig(
        type="serial",
        port="COM7",
        baudrate=115200,
        timeout=1
    ),
    decoder=DecoderConfig(
        frame_delimiter="~",
        field_separator="|",
        param_separator=",",
        param_keyvalue_separator=":",
        frame_index=1,
        cmd_id_index=2,
        seq_index=3,
        length_index=4,
        data_index=5,
        checksum_index=6,
        telecommand_type="TC",
        telemetry_type="TM",
        ack_type="ACK"
    ),
    camera_enabled=True,
    image_save_dir="static/img/esp32",
    database_dir="instance",
    database_file="data.db",
    dashboard_log_enabled=True,
    available_commands=[
        {"id": "CAM_ON", "label": "Camera ON"},
        {"id": "CAM_OFF", "label": "Camera OFF"},
        {"id": "RESET", "label": "Reset"},
    ]
)

# Exemple: Configuration WiFi (commentée)
# ESP32_WIFI = SatelliteConfig(
#     name="ESP32_WiFi",
#     communication=CommunicationConfig(
#         type="wifi",
#         host="172.20.10.2",
#         port_wifi=80,
#         timeout_wifi=15
#     ),
#     decoder=DecoderConfig(...),
#     ...
# )

# ==================================================
# SATELLITE ACTIF
# ==================================================

# À modifier pour changer de satellite
ACTIVE_SATELLITE = ESP32_DEFAULT


# ==================================================
# FONCTION UTILITAIRE
# ==================================================

def get_satellite_config() -> SatelliteConfig:
    """Retourne la configuration du satellite actif."""
    return ACTIVE_SATELLITE


def switch_satellite(config: SatelliteConfig):
    """Change le satellite actif."""
    global ACTIVE_SATELLITE
    ACTIVE_SATELLITE = config
    print(f"[CONFIG] Satellite changé à: {config.name}")
