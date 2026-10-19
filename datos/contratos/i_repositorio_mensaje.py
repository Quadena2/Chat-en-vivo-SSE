from abc import ABC, abstractmethod
from typing import Dict, Any, List


# Contrato (Intefaz) para el repostiorio de mensaje del chat

# Define las operaciones para guardar y recuperar el historial de mensajes
class IRepositorioMensaje(ABC):

    @abstractmethod
    def guardar_mensaje(
            self,
            sala_id: int,
            usuario_id: int,
            nombre_autor: str,
            contenido: str,
            fecha_hora: str,
            max_historial: int = 100,
    ) -> Dict[str, Any]:
        pass

    @abstractmethod
    def obtener_ultimos_mensajes(
            self,
            sala_id: int,
            limite: int = 50
    ) -> List[Dict[str, Any]]:
        pass