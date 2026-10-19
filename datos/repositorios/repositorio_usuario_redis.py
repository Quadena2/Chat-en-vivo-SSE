"""
Claves redis que gestionan esta classe
    id:usuario                  String      Secuencia atomica para generar iDs
    usuario:{id}                Hash        Perfil: id, nombre, password_hash, fecha_registro, es_invitado
    indice:usuario:nombre       Hash        Nombre en minuscula -> id (unicidad HSETNX)
    usuarios                    Set         IDs de todos los usuarios activos/registrados
    contador:usuarios           String      Total de usuarios activos/registrados
"""
from typing import Optional, Dict, List

from datos.contratos.i_repositorio_usuario import IRepositorioUsuario
from datos.gestor_redis import GestorConexionRedis


class RepositorioUsuarioRedis(IRepositorioUsuario):

    CLAVE_SECUENCIA_ID = "id:usuario"
    CLAVE_INDICES_NOMBRES = "indice:usuario:nombre"
    CLAVE_CONJUNTO_USUARIOS = "usuarios"
    CLAVE_CONTADOR_USUARIOS = "contador:usuarios"

    def __init__(self, gestor_redis: GestorConexionRedis):
        self._gestor = gestor_redis

    @property
    def _cliente(self):
        return self._gestor.obtener_cliente()

    @staticmethod
    def _clave_usuario(usuario_id: int) -> str:
        return f"usuario:{usuario_id}"

    # Crea un usuario (registrado o invitado) y devuelve su ID, None si el nombre ya esta en uso
    def crear_usuario(
            self,
            nombre: str,
            password_hash: str,
            fecha_registro: str,
            es_invitado: bool = False,
    ) -> Optional[int]:

        cliente = self._cliente

        # INCR atomico - dos ussuarios simultanemos nunca obtiene el mismo ID
        nuevo_id = cliente.incr(self.CLAVE_SECUENCIA_ID)

        # HSETNX - reserva atomica del nombre en minusculas
        reservado = cliente.hsetnx(self.CLAVE_INDICES_NOMBRES, nombre.lower(), nuevo_id)
        if not reservado:
            return None

        # Transaccion MULTI/EXEC para guardar todos los datos juntos
        tuberia = cliente.pipeline(transaction=True)
        tuberia.hset(self._clave_usuario(nuevo_id), mapping={
            "id": str(nuevo_id),
            "nombre": nombre,
            "password_hash": password_hash,
            "fecha_registro": fecha_registro,
            "es_invitado": "1" if es_invitado else "0",
        })
        tuberia.sadd(self.CLAVE_CONJUNTO_USUARIOS, nuevo_id)
        tuberia.incr(self.CLAVE_CONTADOR_USUARIOS)
        tuberia.execute()

        return nuevo_id

    # Si el usuario es un invitado temporal se libera el nombre del indice y bora su perfil al salir del chat
    def eliminar_invitado(self, usuario_id: int) -> bool:

        datos = self.obtener_usuario(usuario_id)
        if not datos or datos.get("es_invitado") != "1":
            return False

        nombre_minuscula = datos["nombre"].lower()
        tuberia = self._cliente.pipeline(transaction=True)
        tuberia.hdel(self.CLAVE_INDICES_NOMBRES, nombre_minuscula)
        tuberia.delete(self._clave_usuario(usuario_id))
        tuberia.srem(self.CLAVE_CONJUNTO_USUARIOS, usuario_id)
        tuberia.decr(self.CLAVE_CONTADOR_USUARIOS)
        tuberia.execute()

        return True

    # Devuelve el ID (int) asociado al nombre o None si no existe
    def buscar_id_por_nombre(self, nombre: str) -> Optional[int]:

        usuario_id = self._cliente.hget(self.CLAVE_INDICES_NOMBRES, nombre.lower())
        return int(usuario_id) if usuario_id else None

    # Devuelve el Hash completo del usuario (dict) o None si no existe
    def obtener_usuario(self, usuario_id: int) -> Optional[Dict[str, str]]:

        datos = self._cliente.hgetall(self._clave_usuario(usuario_id))
        return datos or None

    # Devuelve {id: nombre} para varios usuarios usando un pipeline
    def obtener_nombres(self, lista_ids: List[int]) -> Dict[int, str]:

        ids_limpios = [int(uid) for uid in lista_ids]
        if not ids_limpios:
            return {}

        tuberia = self._cliente.pipeline(transaction=False)
        for uid in ids_limpios:
            tuberia.hget(self._clave_usuario(uid), "nombre")
        nombres = tuberia.execute()

        # "zip" conbina cada ID ocn el resultado correspondiente de HGET
        # El "if nombre" omite usuarios que no tengan un nombre devuelto
        return {
            uid: nombre for uid, nombre in zip(ids_limpios, nombres) if nombre
        }

    # SISMEMBER comprueba si el ID pertenece al Set 'usuario', 'bool(...)' convierte el resultado de Redis en un True o False
    # Nota: si Redis no esta configurado con "decode_responses=True" algunas respuestas pueden venir como "bytes" y no "str"
    def existe_usuario(self, usuario_id: int) -> bool:
        return bool(self._cliente.sismember(self.CLAVE_CONJUNTO_USUARIOS, usuario_id))





