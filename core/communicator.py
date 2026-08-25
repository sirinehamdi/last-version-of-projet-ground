"""
Module de communication générique.
Support pour série, WiFi, TCP, etc.
"""

import serial
import requests
from typing import Optional
from abc import ABC, abstractmethod
from config import CommunicationConfig


class Communicator(ABC):
    """Interface abstraite pour la communication."""
    
    @abstractmethod
    def connect(self) -> bool:
        """Établit la connexion."""
        pass
    
    @abstractmethod
    def disconnect(self):
        """Ferme la connexion."""
        pass
    
    @abstractmethod
    def send(self, data: str) -> bool:
        """Envoie des données."""
        pass
    
    @abstractmethod
    def receive(self, timeout: Optional[int] = None) -> Optional[str]:
        """Reçoit des données."""
        pass
    
    @abstractmethod
    def is_connected(self) -> bool:
        """Vérifie l'état de la connexion."""
        pass


class SerialCommunicator(Communicator):
    """Communication par port série."""
    
    def __init__(self, config: CommunicationConfig):
        """
        Args:
            config: Configuration de la communication série
        """
        self.config = config
        self.serial = None
        self.connected = False
    
    def connect(self) -> bool:
        """Établit la connexion série."""
        try:
            self.serial = serial.Serial(
                port=self.config.port,
                baudrate=self.config.baudrate,
                timeout=self.config.timeout
            )
            self.connected = True
            print(f"[SERIAL] Connecté à {self.config.port} @ {self.config.baudrate} baud")
            return True
        except Exception as e:
            print(f"[SERIAL] Erreur de connexion: {e}")
            self.connected = False
            return False
    
    def disconnect(self):
        """Ferme la connexion série."""
        if self.serial and self.serial.is_open:
            self.serial.close()
            self.connected = False
            print("[SERIAL] Déconnecté")
    
    def send(self, data: str) -> bool:
        """Envoie des données par série."""
        try:
            if not self.is_connected():
                return False
            
            self.serial.write(data.encode())
            print(f"[SERIAL] TX: {data.strip()}")
            return True
        except Exception as e:
            print(f"[SERIAL] Erreur envoi: {e}")
            return False
    
    def receive(self, timeout: Optional[int] = None) -> Optional[str]:
        """Reçoit des données par série."""
        try:
            if not self.is_connected():
                return None
            
            if timeout:
                old_timeout = self.serial.timeout
                self.serial.timeout = timeout
            
            frame = self.serial.readline().decode(errors="ignore").strip()
            
            if timeout:
                self.serial.timeout = old_timeout
            
            if frame:
                print(f"[SERIAL] RX: {frame}")
            
            return frame if frame else None
        except Exception as e:
            print(f"[SERIAL] Erreur réception: {e}")
            return None
    
    def is_connected(self) -> bool:
        """Vérifie si connecté."""
        return self.connected and self.serial and self.serial.is_open


class WiFiCommunicator(Communicator):
    """Communication par WiFi/HTTP."""
    
    def __init__(self, config: CommunicationConfig):
        """
        Args:
            config: Configuration WiFi
        """
        self.config = config
        self.connected = False
        self.base_url = f"http://{config.host}:{config.port_wifi}"
    
    def connect(self) -> bool:
        """Teste la connexion WiFi."""
        try:
            response = requests.get(f"{self.base_url}/status", timeout=2)
            self.connected = response.status_code == 200
            if self.connected:
                print(f"[WiFi] Connecté à {self.config.host}:{self.config.port_wifi}")
            return self.connected
        except Exception as e:
            print(f"[WiFi] Erreur connexion: {e}")
            self.connected = False
            return False
    
    def disconnect(self):
        """Ferme la connexion WiFi."""
        self.connected = False
        print("[WiFi] Déconnecté")
    
    def send(self, data: str) -> bool:
        """Envoie des données par WiFi."""
        try:
            if not self.is_connected():
                return False
            
            # À adapter selon votre API ESP32
            response = requests.post(
                f"{self.base_url}/command",
                json={"cmd": data},
                timeout=self.config.timeout_wifi
            )
            print(f"[WiFi] TX: {data}")
            return response.status_code == 200
        except Exception as e:
            print(f"[WiFi] Erreur envoi: {e}")
            return False
    
    def receive(self, timeout: Optional[int] = None) -> Optional[str]:
        """Reçoit des données par WiFi (polling)."""
        try:
            if not self.is_connected():
                return None
            
            response = requests.get(
                f"{self.base_url}/telemetry",
                timeout=timeout or self.config.timeout_wifi
            )
            
            if response.status_code == 200:
                data = response.text
                if data:
                    print(f"[WiFi] RX: {data}")
                    return data
            
            return None
        except Exception as e:
            print(f"[WiFi] Erreur réception: {e}")
            return None
    
    def is_connected(self) -> bool:
        """Vérifie la connexion."""
        return self.connected


def create_communicator(config: CommunicationConfig) -> Communicator:
    """Factory pour créer le communicateur approprié."""
    if config.type == "serial":
        return SerialCommunicator(config)
    elif config.type == "wifi":
        return WiFiCommunicator(config)
    else:
        raise ValueError(f"Type de communication non supporté: {config.type}")
