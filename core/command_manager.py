"""
Module de gestion des commandes.
Envoi générique et traçabilité des commandes.
"""

from datetime import datetime
from typing import Dict, Optional, List
from dataclasses import dataclass
from enum import Enum

from core.communicator import Communicator
from core.decoder import CommandFormatter


class CommandStatus(Enum):
    """États possibles d'une commande."""
    PENDING = "pending"
    SENT = "sent"
    ACK = "ack"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class Command:
    """Représentation d'une commande."""
    name: str
    data: str
    cmd_id: str = "101"
    seq: str = "000"
    status: CommandStatus = CommandStatus.PENDING
    timestamp: Optional[datetime] = None
    response: Optional[str] = None


class CommandManager:
    """Gère l'envoi et le suivi des commandes."""
    
    def __init__(self, communicator: Communicator, formatter: CommandFormatter):
        """
        Args:
            communicator: Instance de communication
            formatter: Instance de formatage de commandes
        """
        self.communicator = communicator
        self.formatter = formatter
        self.commands_history: List[Command] = []
        self.seq_counter = 0
    
    def _get_next_seq(self) -> str:
        """Génère le prochain numéro de séquence."""
        self.seq_counter = (self.seq_counter + 1) % 1000
        return str(self.seq_counter).zfill(3)
    
    def send_command(self, name: str, data: str, cmd_id: str = "101") -> bool:
        """
        Envoie une commande au satellite.
        
        Args:
            name: Nom de la commande
            data: Données de la commande
            cmd_id: ID de la commande (défaut: 101)
        
        Returns:
            True si envoyée, False sinon
        """
        try:
            # Créer l'objet commande
            seq = self._get_next_seq()
            command = Command(
                name=name,
                data=data,
                cmd_id=cmd_id,
                seq=seq,
                timestamp=datetime.now()
            )
            
            # Formater la trame
            frame = self.formatter.format_command(data, cmd_id, seq)
            
            # Envoyer
            success = self.communicator.send(frame)
            
            if success:
                command.status = CommandStatus.SENT
                print(f"[CMD] {name} envoyée (seq: {seq})")
            else:
                command.status = CommandStatus.FAILED
                print(f"[CMD] Erreur envoi {name}")
            
            # Enregistrer l'historique
            self.commands_history.append(command)
            
            return success
        except Exception as e:
            print(f"[CMD] Exception: {e}")
            return False
    
    def acknowledge_command(self, seq: str):
        """Marque une commande comme reçue (ACK)."""
        for cmd in self.commands_history:
            if cmd.seq == seq:
                cmd.status = CommandStatus.ACK
                print(f"[CMD] ACK reçu pour seq: {seq}")
                return
    
    def get_command_status(self, seq: str) -> Optional[CommandStatus]:
        """Récupère l'état d'une commande par son numéro de séquence."""
        for cmd in self.commands_history:
            if cmd.seq == seq:
                return cmd.status
        return None
    
    def get_commands_history(self, limit: int = 100) -> List[Dict]:
        """
        Retourne l'historique des commandes.
        
        Args:
            limit: Nombre maximum de commandes
        
        Returns:
            Liste des commandes (dict)
        """
        result = []
        for cmd in self.commands_history[-limit:]:
            result.append({
                "name": cmd.name,
                "data": cmd.data,
                "seq": cmd.seq,
                "status": cmd.status.value,
                "timestamp": cmd.timestamp.isoformat() if cmd.timestamp else None,
                "response": cmd.response
            })
        return result
    
    def clear_history(self):
        """Vide l'historique des commandes."""
        self.commands_history = []
