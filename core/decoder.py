"""
Module de décodage générique des trames.
Support de différents formats de trames selon la configuration.
"""

from typing import Optional, Dict, Any
from config import DecoderConfig


class FrameDecoder:
    """Décodeur générique de trames."""
    
    def __init__(self, config: DecoderConfig):
        """
        Args:
            config: Configuration du décodage
        """
        self.config = config
    
    def decode_frame(self, frame: str) -> Optional[Dict[str, Any]]:
        """
        Décode une trame brute selon la configuration.
        
        Format attendu: ~|TC|101|000|5|HELLO|0\n
        
        Returns:
            Dict avec les champs: type, cmd_id, seq, length, data, checksum
            Ou None si le décodage échoue
        """
        try:
            frame = frame.strip()
            
            delimiter = self.config.frame_delimiter
            if not delimiter or not frame.startswith(delimiter):
                return None

            content = frame[len(delimiter):]
            closing_delimiter = getattr(
                self.config,
                "closing_delimiter",
                None,
            ) or delimiter
            if getattr(self.config, "closing_frame_delimiter", False):
                if content.endswith(closing_delimiter):
                    content = content[:-len(closing_delimiter)]
            fields = content.split(self.config.field_separator)

            indexes = (
                self.config.frame_index,
                self.config.cmd_id_index,
                self.config.seq_index,
                self.config.length_index,
                self.config.data_index,
            )
            if any(index is None or index < 0 for index in indexes):
                return None
            if max(indexes) >= len(fields):
                return None
            
            return {
                "type": fields[self.config.frame_index],
                "cmd_id": fields[self.config.cmd_id_index],
                "seq": fields[self.config.seq_index],
                "length": fields[self.config.length_index],
                "data": fields[self.config.data_index],
                "checksum": (
                    fields[self.config.checksum_index]
                    if self.config.checksum_index is not None
                    and 0 <= self.config.checksum_index < len(fields)
                    else None
                ),
                "raw": frame
            }
        except Exception as e:
            print(f"[DECODER] Erreur décodage trame: {e}")
            return None
    
    def decode_telemetry(self, data: str) -> Optional[Dict[str, str]]:
        """
        Décode les données de télémétrie (paires clé:valeur séparées par des virgules).
        
        Format attendu: temp:23.5,pressure:1013,humidity:45
        
        Returns:
            Dict {clé: valeur, ...}
            Ou None si erreur
        """
        try:
            values = {}
            
            for item in data.split(self.config.param_separator):
                if self.config.param_keyvalue_separator not in item:
                    continue
                
                key, value = item.split(self.config.param_keyvalue_separator, 1)
                values[key.lower().strip()] = value.strip()
            
            return values if values else None
        except Exception as e:
            print(f"[DECODER] Erreur décodage télémétrie: {e}")
            return None
    
    def is_telecommand(self, frame_dict: Dict[str, Any]) -> bool:
        """Vérifie si c'est une télécommande."""
        return frame_dict.get("type") == self.config.telecommand_type
    
    def is_telemetry(self, frame_dict: Dict[str, Any]) -> bool:
        """Vérifie si c'est une télémétrie."""
        return frame_dict.get("type") == self.config.telemetry_type
    
    def is_ack(self, frame_dict: Dict[str, Any]) -> bool:
        """Vérifie si c'est un accusé de réception."""
        return frame_dict.get("type") == self.config.ack_type


class CommandFormatter:
    """Formateur générique de commandes."""
    
    def __init__(self, config: DecoderConfig):
        """
        Args:
            config: Configuration du formatage
        """
        self.config = config
    
    def format_command(self, command: str, cmd_id: str = "101", seq: str = "000") -> str:
        """
        Formate une commande selon le standard des trames.
        
        Returns:
            Trame formatée: ~|TC|101|000|5|HELLO|0\n
        """
        indexes = {
            "type": self.config.frame_index,
            "cmd_id": self.config.cmd_id_index,
            "seq": self.config.seq_index,
            "length": self.config.length_index,
            "data": self.config.data_index,
            "checksum": self.config.checksum_index,
        }
        if any(index is None or index < 0 for index in indexes.values()):
            raise ValueError("La configuration JSON doit définir tous les index de trame")

        fields = [""] * (max(indexes.values()) + 1)
        fields[indexes["type"]] = self.config.telecommand_type
        fields[indexes["cmd_id"]] = str(cmd_id)
        fields[indexes["seq"]] = str(seq)
        fields[indexes["length"]] = str(len(command))
        fields[indexes["data"]] = command
        if self.config.checksum_value is None:
            raise ValueError("La configuration JSON doit définir checksum_value")
        fields[indexes["checksum"]] = str(self.config.checksum_value)

        frame = self.config.frame_delimiter + self.config.field_separator.join(fields)
        if self.config.closing_frame_delimiter:
            frame += self.config.closing_delimiter or self.config.frame_delimiter
        return frame + self.config.line_ending
