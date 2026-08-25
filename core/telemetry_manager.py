"""
Module de gestion des télémétries.
Enregistrement et stockage générique des données.
"""

from datetime import datetime
from typing import Dict, Any, Optional
from flask import Flask
from models import db, Telemetry, Day, Month


class TelemetryManager:
    """Gère le stockage et la gestion des télémétries."""
    
    def __init__(self, app: Flask):
        """
        Args:
            app: Instance Flask
        """
        self.app = app
        self.data_store: Dict[str, list] = {"time": []}
    
    def get_or_create_day(self, timestamp: datetime) -> Day:
        """
        Récupère ou crée un jour dans la base de données.
        Organise: Année -> Mois -> Jour
        """
        year = timestamp.year
        month_number = timestamp.month
        day_date = timestamp.date()
        
        month_names = [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ]
        month_name = month_names[month_number - 1]
        
        # Chercher le mois
        month = Month.query.filter_by(year=year, month=month_number).first()
        
        if month is None:
            month = Month(year=year, month=month_number, name=month_name)
            db.session.add(month)
            db.session.flush()
        
        # Chercher le jour
        day = Day.query.filter_by(month_id=month.id, date=day_date).first()
        
        if day is None:
            day = Day(month_id=month.id, date=day_date)
            db.session.add(day)
            db.session.flush()
        
        return day
    
    def store_telemetry(self, timestamp: datetime, parameters: Dict[str, Any]) -> bool:
        """
        Enregistre les données de télémétrie.
        
        Args:
            timestamp: Horodatage
            parameters: Dict {clé: valeur}
        
        Returns:
            True si succès, False sinon
        """
        try:
            with self.app.app_context():
                # Récupérer ou créer le jour
                day = self.get_or_create_day(timestamp)
                
                # Enregistrer chaque paramètre
                for key, value in parameters.items():
                    telemetry = Telemetry(
                        day_id=day.id,
                        key=str(key).lower(),
                        value=str(value),
                        timestamp=timestamp
                    )
                    db.session.add(telemetry)
                
                db.session.commit()
                print(f"[TELEMETRY] {len(parameters)} paramètres enregistrés")
                return True
        except Exception as e:
            db.session.rollback()
            print(f"[TELEMETRY] Erreur de stockage: {e}")
            return False
    
    def add_to_dashboard(self, parameters: Dict[str, Any]):
        """
        Ajoute les données au dashboard en mémoire.
        
        Args:
            parameters: Dict {clé: valeur}
        """
        for key, value in parameters.items():
            key_lower = key.lower()
            
            if key_lower not in self.data_store:
                self.data_store[key_lower] = []
                print(f"[DASHBOARD] Nouveau paramètre: {key_lower}")
            
            try:
                self.data_store[key_lower].append(float(value))
            except (ValueError, TypeError):
                self.data_store[key_lower].append(value)
    
    def add_timestamp(self, timestamp_str: str):
        """Ajoute un timestamp au dashboard."""
        self.data_store["time"].append(timestamp_str)
    
    def get_data_store(self) -> Dict[str, list]:
        """Retourne le data_store pour le dashboard."""
        return self.data_store.copy()
    
    def clear_data_store(self):
        """Vide le data_store."""
        self.data_store = {"time": []}
    
    def get_telemetry_by_date(self, date_str: str) -> list:
        """
        Récupère les télémétries d'une date donnée.
        
        Args:
            date_str: Format "YYYY-MM-DD"
        
        Returns:
            Liste des télémétries
        """
        try:
            from datetime import datetime
            date = datetime.strptime(date_str, "%Y-%m-%d").date()
            
            telemetries = Telemetry.query.join(Day).filter(
                Day.date == date
            ).all()
            
            return telemetries
        except Exception as e:
            print(f"[TELEMETRY] Erreur requête: {e}")
            return []
    
    def get_telemetry_by_key(self, key: str, date_str: str) -> list:
        """
        Récupère les télémétries d'une clé donnée pour une date.
        
        Args:
            key: Clé du paramètre
            date_str: Format "YYYY-MM-DD"
        
        Returns:
            Liste des valeurs avec timestamps
        """
        try:
            from datetime import datetime
            date = datetime.strptime(date_str, "%Y-%m-%d").date()
            
            telemetries = Telemetry.query.join(Day).filter(
                Day.date == date,
                Telemetry.key == key.lower()
            ).order_by(Telemetry.timestamp).all()
            
            return telemetries
        except Exception as e:
            print(f"[TELEMETRY] Erreur requête: {e}")
            return []
