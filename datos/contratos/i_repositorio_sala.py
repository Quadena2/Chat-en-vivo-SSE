from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Set


# Contrato (Interfaz) para el repositorio de salas y presencia de usuarios

# Define las operaciones para gestionar salas y usuarios activos en ellas
# La presencia se maneja por CONEXION (cada pestaña abierta = 1 conexion SSE),
# asi un usuario con 2 pestañas abiertas no desaparece al cerrar solo una
class IRepositorioSala(ABC):

    @abstractmethod
    def crear_sala(self, nombre: str, descripcion: str, creador_id: int) -> Optional[int]:
        pass

    @abstractmethod
    def obtener_sala(self, sala_id: int) -> Optional[Dict[str, str]]:
        pass

    @abstractmethod
    def listar_salas(self) -> List[Dict[str, str]]:
        pass

    @abstractmethod
    def existe_sala(self, sala_id: int) -> bool:
        pass

    @abstractmethod
    def registrar_entrada_usuario(self, sala_id: int, usuario_id: int, conexion_id: str) -> None:
        pass

    @abstractmethod
    def renovar_presencia(self, sala_id: int, usuario_id: int, conexion_id: str) -> bool:
        pass

    @abstractmethod
    def registrar_salida_usuario(self, sala_id: int, usuario_id: int, conexion_id: str) -> bool:
        pass

    @abstractmethod
    def eliminar_usuario_de_salas(self, usuario_id: int) -> List[int]:
        pass

    @abstractmethod
    def limpiar_conexiones_vencidas(self, sala_id: int) -> int:
        pass

    @abstractmethod
    def obtener_usuarios_online(self, sala_id: int) -> Set[int]:
        pass

    @abstractmethod
    def contar_usuarios_online(self, sala_id: int) -> int:
        pass

    @abstractmethod
    def usuario_tiene_conexiones_activas(self, usuario_id: int) -> bool:
        pass