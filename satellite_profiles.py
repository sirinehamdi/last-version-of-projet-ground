"""Charge les profils de satellites depuis le fichier satellites.json modifiable."""

import json
from pathlib import Path
from typing import Dict, List, Optional

from config import CommunicationConfig, DecoderConfig, SatelliteConfig


PROFILES_FILE = Path(__file__).with_name("satellites.json")


def _build_profile(profile: dict) -> SatelliteConfig:
    """Convertit un profil JSON en objets utilisés par l'application."""
    return SatelliteConfig(
        name=profile["name"],
        communication=CommunicationConfig(**profile["communication"]),
        decoder=DecoderConfig(**profile["decoder"]),
        camera_enabled=profile.get("camera_enabled", True),
        image_save_dir=profile.get("image_save_dir", "static/img/esp32"),
        database_dir=profile.get("database_dir", "instance"),
        database_file=profile.get("database_file", "data.db"),
        dashboard_log_enabled=profile.get("dashboard_log_enabled", True),
        available_commands=profile.get("available_commands"),
    )


def load_satellite_profiles() -> Dict[str, SatelliteConfig]:
    """Lit le catalogue JSON. Redémarrer le serveur après une modification."""
    with PROFILES_FILE.open(encoding="utf-8") as profiles_file:
        profiles = json.load(profiles_file)

    if not isinstance(profiles, dict):
        raise ValueError("satellites.json doit contenir un objet de profils")

    return {key.lower(): _build_profile(value) for key, value in profiles.items()}


def get_satellite_by_name(name: str) -> Optional[SatelliteConfig]:
    """Retourne un profil à partir de sa clé, par exemple esp32_wifi."""
    if not name:
        return None
    return load_satellite_profiles().get(name.lower())


def list_available_satellites() -> List[str]:
    """Liste les clés des profils disponibles."""
    return list(load_satellite_profiles().keys())