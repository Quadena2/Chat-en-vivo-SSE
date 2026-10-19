from abc import ABC, abstractmethod
from typing import Dict, Any, Iterator


# Contrato (Interfaz) para el bus de eventos en tiempo real


# Define las operaciones de publicaciones y suscripciones en tiempo real
class IBusEventos(ABC):

    # Publica un evento solo para los que estan dentro de una sala (mensajes, presencia)
    @abstractmethod
    def publicar_evento_sala(
            self,
            sala_id: int,
            evento: Dict[str, Any]
    ) -> int:
        pass

    # Publica un evento para TODOS los conectados sin importar la sala
    # (ej. contadores de conectados de cada sala o una sala nueva creada)
    @abstractmethod
    def publicar_evento_global(self, evento: Dict[str, Any]) -> int:
        pass

    # Escucha a la vez el canal de la sala y el canal global
    @abstractmethod
    def escuchar_sala(self, sala_id: int) -> Iterator[str]:
        pass
