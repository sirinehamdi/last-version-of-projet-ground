"""
Module de gestion du stockage des images et fichiers.
Support générique pour différents formats et emplacements.
"""

import os
import imghdr
import base64
from datetime import datetime
from typing import Tuple, Optional
import requests


class ImageManager:
    """Gère le stockage et la gestion des images."""
    
    SUPPORTED_FORMATS = ("jpg", "jpeg", "png", "gif", "bmp", "webp")
    MIN_FILE_SIZE = 200  # Bytes
    
    def __init__(self, save_dir: str = "static/img/esp32"):
        """
        Args:
            save_dir: Répertoire de sauvegarde des images
        """
        self.save_dir = save_dir
        self.latest_image_path = os.path.join("static", "Latest_Capture.jpg")
        
        # Créer les répertoires s'ils n'existent pas
        os.makedirs(self.save_dir, exist_ok=True)
        os.makedirs(os.path.dirname(self.latest_image_path), exist_ok=True)
    
    def save_image_from_response(self, response: requests.Response, prefix: str = "Capture") -> Tuple[Optional[str], Optional[bytes]]:
        """
        Sauvegarde une image depuis une réponse HTTP.
        
        Args:
            response: Réponse HTTP contenant l'image
            prefix: Préfixe du nom de fichier
        
        Returns:
            Tuple (filename, image_bytes) ou (None, None) si erreur
        """
        try:
            content_type = response.headers.get("Content-Type", "").lower()
            image_bytes = None
            extension = "jpg"
            
            # Si réponse JSON (image en base64)
            if "application/json" in content_type:
                payload = response.json()
                image_data = payload.get("image") or payload.get("data")
                if not image_data:
                    raise ValueError("Pas de données d'image dans le JSON")
                
                image_bytes = base64.b64decode(image_data)
                extension = payload.get("extension", "jpg").lower()
            else:
                # Réponse binaire directe
                image_bytes = response.content
                if not image_bytes:
                    raise ValueError("Pas de contenu d'image")
                
                # Détecter le format
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
            
            # Vérifier l'intégrité de l'image
            detected = imghdr.what(None, h=image_bytes)
            if detected:
                if detected == "jpeg":
                    detected = "jpg"
                extension = detected
            elif extension not in self.SUPPORTED_FORMATS:
                raise ValueError(f"Format d'image non supporté: {extension}")
            
            # Générer le nom de fichier
            filename = datetime.now().strftime(f"{prefix}_%Y%m%d_%H%M%S.") + extension
            save_path = os.path.join(self.save_dir, filename)
            
            # Sauvegarder l'image
            with open(save_path, 'wb') as f:
                f.write(image_bytes)
            
            print(f"[IMAGE] Sauvegardée: {filename}")
            return filename, image_bytes
        
        except Exception as e:
            print(f"[IMAGE] Erreur sauvegarde: {e}")
            return None, None
    
    def save_image_from_bytes(self, image_bytes: bytes, prefix: str = "Capture") -> Optional[str]:
        """
        Sauvegarde une image à partir d'octets bruts.
        
        Args:
            image_bytes: Contenu binaire de l'image
            prefix: Préfixe du nom de fichier
        
        Returns:
            Nom du fichier sauvegardé ou None si erreur
        """
        try:
            if not image_bytes or len(image_bytes) < self.MIN_FILE_SIZE:
                raise ValueError("Données d'image invalides ou trop petites")
            
            # Déterminer le format
            detected = imghdr.what(None, h=image_bytes)
            if not detected:
                raise ValueError("Format d'image non reconnu")
            
            if detected == "jpeg":
                detected = "jpg"
            
            extension = detected
            
            # Générer le nom de fichier
            filename = datetime.now().strftime(f"{prefix}_%Y%m%d_%H%M%S.") + extension
            save_path = os.path.join(self.save_dir, filename)
            
            # Sauvegarder
            with open(save_path, 'wb') as f:
                f.write(image_bytes)
            
            print(f"[IMAGE] Sauvegardée: {filename}")
            return filename
        
        except Exception as e:
            print(f"[IMAGE] Erreur sauvegarde: {e}")
            return None
    
    def save_latest_image(self, image_bytes: bytes) -> bool:
        """
        Sauvegarde l'image comme "dernière capture".
        
        Args:
            image_bytes: Contenu binaire de l'image
        
        Returns:
            True si succès, False sinon
        """
        try:
            os.makedirs(os.path.dirname(self.latest_image_path), exist_ok=True)
            with open(self.latest_image_path, 'wb') as f:
                f.write(image_bytes)
            print(f"[IMAGE] Dernière capture mise à jour")
            return True
        except Exception as e:
            print(f"[IMAGE] Erreur mise à jour dernière capture: {e}")
            return False
    
    def get_image_history(self, limit: int = None) -> list:
        """
        Récupère l'historique des images capturées.
        
        Args:
            limit: Nombre maximum d'images
        
        Returns:
            Liste des noms de fichiers (trié par date décroissante)
        """
        try:
            files = []
            for fichier in os.listdir(self.save_dir):
                if not fichier.lower().startswith('capture_'):
                    continue
                
                path = os.path.join(self.save_dir, fichier)
                if not os.path.isfile(path):
                    continue
                
                if os.path.getsize(path) < self.MIN_FILE_SIZE:
                    continue
                
                if not imghdr.what(path):
                    continue
                
                files.append(fichier)
            
            files.sort(reverse=True)
            
            if limit:
                files = files[:limit]
            
            return files
        except Exception as e:
            print(f"[IMAGE] Erreur lecture historique: {e}")
            return []
    
    def get_latest_image_path(self) -> str:
        """Retourne le chemin de la dernière image."""
        return self.latest_image_path
    
    def image_exists(self, filename: str) -> bool:
        """Vérifie si une image existe."""
        path = os.path.join(self.save_dir, filename)
        return os.path.isfile(path)
