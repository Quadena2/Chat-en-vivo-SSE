from abc import ABC, abstractmethod
from typing import Optional, Dict, List


# Contrato (Interfaz) para el repositorio de Usuario Hibrido (registro-login-invitado)

# Devine las operaciones de persistencia para usuarios registrados e invitado
class IRepositorioUsuario(ABC):

    @abstractmethod
    def crear_usuario(
            self,
            nombre: str,
            password_hash: str,
            fecha_registro: str,
            es_invitado: bool = False,
    ) -> Optional[int]:
        pass

    @abstractmethod
    def eliminar_invitado(self, usuario_id: int) -> bool:
        pass

    @abstractmethod
    def buscar_id_por_nombre(self, nombre: str) -> Optional[int]:
        pass

    @abstractmethod
    def obtener_usuario(self, usuario_id: int) -> Optional[Dict[str, str]]:
        pass

    @abstractmethod
    def obtener_nombres(self, lista_ids: List[int]) -> Dict[int, str]:
        pass

    @abstractmethod
    def existe_usuario(self, usuario_id: int) -> bool:
        pass