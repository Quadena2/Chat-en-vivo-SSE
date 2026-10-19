from typing import Tuple, Optional, List, Dict, Any

from datos.contratos.i_bus_eventos import IBusEventos
from datos.contratos.i_repositorio_sala import IRepositorioSala
from datos.contratos.i_repositorio_usuario import IRepositorioUsuario


# Capa de negocio, servicio de gestion de salas de chat y presencia (online)



class ServicioSala:

    def __init__(
            self,
            repo_salas: IRepositorioSala,
            repo_usuarios: IRepositorioUsuario,
            bus_eventos: IBusEventos,
    ):
        self._repo_salas = repo_salas
        self._repo_usuarios = repo_usuarios
        self._bus_eventos = bus_eventos

    # Crea salas por defecto al arrancar la aplicacion si REDIS esta vacio
    def asegurar_salas_iniciales(self) -> None:

         salas_actuales = self._repo_salas.listar_salas()
         if not salas_actuales:
             salas_por_defecto = [
                 ("General", "Sala principal de la aplicacion de chat en vivo con Redis"),
                 ("Base de Datos III", "Big Data - DBs NoSQL - DB Distribuidas"),
                 ("Musica y Ocio", "Charla libre sobre gustos musicales, ocios, series")
             ]
             for nombre, desc in salas_por_defecto:
                 self._repo_salas.crear_sala(nombre=nombre, descripcion=desc, creador_id=0)


    # Valida los datos y crea una nueva sala de chat
    # Si se crea, avisa a todos por el canal global para que aparezca en su lista sin recargar
    def crear_nueva_sala(
            self,
            nombre: str,
            descripcion: str,
            creador_id: int,
    ) -> Tuple[bool, str, Optional[int]]:

        nombre_limpio = nombre.strip()
        desc_limpio = descripcion.strip()

        if len(nombre_limpio) < 3 or len(nombre_limpio) >25:
            return False, "El nombre de la sala debe terner entre 3 y 25 caracteres", None

        sala_id = self._repo_salas.crear_sala(nombre_limpio,desc_limpio, creador_id)
        if sala_id is None:
            return False, f"Ya existe una sala llamada '{nombre_limpio}'", None

        self.publicar_resumen_salas()

        return True, "Sala creada correctamente", sala_id

    # Comprueba si la sala existe
    def existe_sala(self, sala_id: int) -> bool:
        return self._repo_salas.existe_sala(sala_id)

    # Devuelve todas las salas agregando el numero de personas contadas en vivo en cada una
    def listar_salas_con_conectados(self) -> List[Dict[str, Any]]:

        salas = self._repo_salas.listar_salas()
        resultado = []
        for sala in salas:
            sid = int(sala["id"])
            resultado.append({
                "id": sid,
                "nombre": sala["nombre"],
                "descripcion": sala.get("descripcion", ""),
                "conectados": self._repo_salas.contar_usuarios_online(sid)
            })

        return resultado

    # Publica por el canal global el resumen de TODAS las salas con su numero de conectados
    # Asi el contador (badge) de cada sala en el panel izquierdo se actualiza en vivo para todos
    def publicar_resumen_salas(self) -> None:
        evento = {
            "tipo": "salas",
            "datos": self.listar_salas_con_conectados(),
        }
        self._bus_eventos.publicar_evento_global(evento)

    # Obtiene los datos de una sala junto con la lista de nombres de lo usuarios que estan conectados en este momento
    def obtener_sala_detallada(self, sala_id:  int) -> Optional[Dict[str, Any]]:

        sala = self._repo_salas.obtener_sala(sala_id)
        if not sala:
            return None

        return {
            "id": int(sala["id"]),
            "nombre": sala["nombre"],
            "descripcion": sala.get("descripcion", ""),
            "usuarios_online": self.obtener_nombres_online(sala_id)
        }

    # Cursa los IDs del Set de presencia de la sala con el repositorio de usuarios para deolver sus nombres orednados
    def obtener_nombres_online(self, sala_id: int) -> List[str]:

        ids_online = list(self._repo_salas.obtener_usuarios_online(sala_id))
        if not ids_online:
            return []

        mapa_nombre = self._repo_usuarios.obtener_nombres(ids_online)
        return sorted(mapa_nombre.values(), key=lambda x: x.lower())