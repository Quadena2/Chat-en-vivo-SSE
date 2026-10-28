
"""
Clavs Redis que gestiona esta clase
    id:sala                 String          Secuencia para generar IDs de sala (INCR)
    sala:{id}               Hash            Datos: id, nombre, descripcion, creador_id
    indice:sala:nombre      Hash            Nombre en minuscula -> id (unicidad HSETNX)
    salas                   Set             IDs de todas las salas creadas
    sala:{id}:conexiones    Sorted Set      Conexiones abiertas ahora mismo en la sala
                                            miembro = "{usuario_id}:{conexion_id}"
                                            score   = timestamp del ultimo latido (heartbeat)

Por que un Sorted Set y no un Set simple de IDs:
    - Un usuario puede tener varias pestañas abiertas en la misma sala (varias conexiones).
      Con un Set de IDs, al cerrar UNA pestaña se borraba al usuario aunque siguiera en otra.
    - Si Flask se reinicia o se cae, el bloque "finally" de la conexion nunca se ejecuta
      y con un Set el nombre quedaba "online" para siempre. Con el score (hora del ultimo
      latido) podemos detectar y borrar conexiones muertas con ZREMRANGEBYSCORE.
"""
import time
from typing import Optional, Dict, List, Set
from datos.contratos.i_repositorio_sala import IRepositorioSala
from datos.gestor_redis import GestorConexionRedis


class RepositorioSalaRedis(IRepositorioSala):

    CLAVE_SECUENCIA_ID = "id:sala"
    CLAVE_INDICE_NOMBRES = "indice:sala:nombre"
    CLAVE_CONJUNTO_SALAS = "salas"

    # ttl_presencia: segundos sin latido tras los cuales una conexion se considera muerta
    def __init__(self, gestor_redis: GestorConexionRedis, ttl_presencia: int = 15):
        self._gestor = gestor_redis
        self._ttl_presencia = ttl_presencia

    @property
    def _cliente(self):
        return self._gestor.obtener_cliente()

    @staticmethod
    def _clave_sala(sala_id: int)  -> str:
        return f"sala:{sala_id}"

    @staticmethod
    def _clave_conexiones(sala_id: int) -> str:
        return f"sala:{sala_id}:conexiones"

    @staticmethod
    def _miembro(usuario_id: int, conexion_id: str) -> str:
        return f"{usuario_id}:{conexion_id}"

    # Hora minima de latido para que una conexion siga considerandose viva
    def _limite_vigencia(self) -> float:
        return time.time() - self._ttl_presencia

    # Crea una sala si el nombre no esta repetido, devuelve su ID o None
    def crear_sala(self, nombre: str, descripcion: str, creador_id: int) -> Optional[int]:
        cliente = self._cliente

        # Gener ID unico de forma atonica con INCR
        nuevo_id = cliente.incr(self.CLAVE_SECUENCIA_ID)

        # HSETNX reserva el nombre en minusculas para evitar salas duplicadas
        reservado = cliente.hsetnx(self.CLAVE_INDICE_NOMBRES, nombre.lower(), nuevo_id)
        if not reservado:
            return None

        # Guarda el Hash de la sala y registra su ID en el Set global "salas"
        tuberia = cliente.pipeline(transaction=True)
        tuberia.hset(self._clave_sala(nuevo_id), mapping={
            "id": str(nuevo_id),
            "nombre": nombre,
            "descripcion": descripcion,
            "creador_id": str(creador_id),
        })
        tuberia.sadd(self.CLAVE_CONJUNTO_SALAS, nuevo_id)
        tuberia.execute()

        return nuevo_id

    # Devuelve el diccionario con los datos de la sala o None si no existe
    def obtener_sala(self, sala_id: int) -> Optional[Dict[str, str]]:
        datos = self._cliente.hgetall(self._clave_sala(sala_id))
        return datos or None

    # Obtiene todas las salas existentes en solo 2 viajes de red
    def listar_salas(self) -> List[Dict[str, str]]:
        cliente = self._cliente

        # SMEMBERS trae todos los IDs guardados en el Set "salas"
        ids_salas = sorted(int(sid) for sid in cliente.smembers(self.CLAVE_CONJUNTO_SALAS))
        if not ids_salas:
            return []

        # Pipeline con HGETALL para traer los datos de cada sala de golpe
        tuberia = cliente.pipeline(transaction=False)
        for sid in ids_salas:
            tuberia.hgetall(self._clave_sala(sid))
        resultados = tuberia.execute()

        return [sala for sala in resultados if sala]

    # Comprueba si la sala existe en el Set global
    def existe_sala(self, sala_id: int) -> bool:
        return bool(self._cliente.sismember(self.CLAVE_CONJUNTO_SALAS, sala_id))

    # Registra una conexion (pestaña) del usuario en la sala con la hora actual como score
    # ZADD agrega el miembro al Sorted Set, si ya existia solo actualiza su score
    def registrar_entrada_usuario(self, sala_id: int, usuario_id: int, conexion_id: str) -> None:
        self._cliente.zadd(
            self._clave_conexiones(sala_id),
            {self._miembro(usuario_id, conexion_id): time.time()},
        )

    # Latido (heartbeat): actualiza la hora de la conexion para indicar que sigue viva
    # ZADD XX CH -> XX solo actualiza si el miembro YA existe (nunca lo vuelve a crear)
    #               CH devuelve cuantos miembros cambiaron
    # Devuelve False si la conexion ya no estaba (alguien la saco: logout, salida o limpieza)
    def renovar_presencia(self, sala_id: int, usuario_id: int, conexion_id: str) -> bool:
        cambiados = self._cliente.zadd(
            self._clave_conexiones(sala_id),
            {self._miembro(usuario_id, conexion_id): time.time()},
            xx=True,
            ch=True,
        )
        return bool(cambiados)

    # Elimina la conexion (pestaña) de la sala
    # ZREM saca el miembro del Sorted Set y devuelve cuantos borro
    # Devuelve True solo si realmente estaba (evita avisar 2 veces la misma salida)
    def registrar_salida_usuario(self, sala_id: int, usuario_id: int, conexion_id: str) -> bool:
        borrados = self._cliente.zrem(
            self._clave_conexiones(sala_id),
            self._miembro(usuario_id, conexion_id),
        )
        return bool(borrados)

    # Saca TODAS las conexiones de un usuario en TODAS las salas (se usa al cerrar sesion)
    # Devuelve la lista de IDs de salas donde estaba conectado
    def eliminar_usuario_de_salas(self, usuario_id: int) -> List[int]:
        cliente = self._cliente
        prefijo = f"{usuario_id}:"
        salas_afectadas = []

        for sid in cliente.smembers(self.CLAVE_CONJUNTO_SALAS):
            clave = self._clave_conexiones(int(sid))

            # ZRANGE 0 -1 trae todos los miembros del Sorted Set
            miembros = [m for m in cliente.zrange(clave, 0, -1) if m.startswith(prefijo)]
            if miembros:
                cliente.zrem(clave, *miembros)
                salas_afectadas.append(int(sid))

        return sorted(salas_afectadas)

    # Borra las conexiones que no enviaron latido dentro del TTL (Flask reiniciado, red caida, etc.)
    # ZREMRANGEBYSCORE elimina de un solo golpe todos los miembros con score entre -inf y el limite
    # Devuelve cuantas conexiones muertas se borraron
    def limpiar_conexiones_vencidas(self, sala_id: int) -> int:
        return int(self._cliente.zremrangebyscore(
            self._clave_conexiones(sala_id), "-inf", self._limite_vigencia()
        ))

    # Devuelve el conjunto set con los IDs de usuarios conectados (sin repetir)
    # ZRANGEBYSCORE trae solo las conexiones con latido reciente (score >= limite)
    # Varias pestañas del mismo usuario se juntan en un solo ID gracias al set()
    def obtener_usuarios_online(self, sala_id: int) -> Set[int]:
        miembros = self._cliente.zrangebyscore(
            self._clave_conexiones(sala_id), self._limite_vigencia(), "+inf"
        )
        return {int(miembro.split(":", 1)[0]) for miembro in miembros}

    # Devuelve la cantidad de PERSONAS conectadas (no de pestañas)
    # No se usa ZCARD porque contaria cada pestaña abierta como una persona distinta
    def contar_usuarios_online(self, sala_id: int) -> int:
        return len(self.obtener_usuarios_online(sala_id))

    # Comprueba si el usuario aun tiene al menos una pestaña activa en cualquiera de las salas
    def usuario_tiene_conexiones_activas(self, usuario_id: int) -> bool:
        cliente = self._cliente
        prefijo = f"{usuario_id}:"
        limite = self._limite_vigencia()

        for sid in cliente.smembers(self.CLAVE_CONJUNTO_SALAS):
            clave = self._clave_conexiones(int(sid))
            miembros_vivos = cliente.zrangebyscore(clave, limite, "+inf")
            if any(m.startswith(prefijo) for m in miembros_vivos):
                return True

        return False
