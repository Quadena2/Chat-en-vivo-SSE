import time
from datetime import datetime
from typing import Tuple, Optional, Dict, Any, List, Iterator

from datos.contratos.i_bus_eventos import IBusEventos
from datos.contratos.i_repositorio_mensaje import IRepositorioMensaje
from datos.contratos.i_repositorio_sala import IRepositorioSala
from datos.contratos.i_repositorio_usuario import IRepositorioUsuario
from negocio.servicio_sala import ServicioSala


# Capa de negocio, Servicio de chat en vivo (mensajes, presencia y steraming)



class ServicioChat:

    def __init__(
            self,
            repo_mensajes: IRepositorioMensaje,
            repo_salas: IRepositorioSala,
            repo_usuario: IRepositorioUsuario,
            bus_eventos: IBusEventos,
            servicio_sala: ServicioSala,
            max_historial: int = 100,
            intervalo_latido: int = 5,
    ):
        self._repo_mensajes = repo_mensajes
        self._repo_salas = repo_salas
        self._repo_usuario = repo_usuario
        self._bus_eventos = bus_eventos
        self._servicio_sala = servicio_sala
        self._max_historial = max_historial
        self._intervalo_latido = intervalo_latido

    # Valida un mensaje, se guarda en la lista de REDIS de la sala y lo publica inmediatamente en el canal Pub/Sub para todos los conectados
    def enviar_mensaje(
            self,
            sala_id: int,
            usuario_id: int,
            contenido: str
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:

        texto = contenido.strip() if isinstance(contenido, str) else ""
        if not texto:
            return False, "El mensaje no puede estar vacio", None

        if len(texto) > 500:
            return False, "El mensaje no puede superar los 500 caracteres", None

        if not self._repo_salas.existe_sala(sala_id):
            return False, "Sala no encontrada", None

        usuario = self._repo_usuario.obtener_usuario(usuario_id)
        if not usuario:
            return False, "Usuario no valido", None

        hora_actual = datetime.now().strftime("%H:%M:%S")

        # Guardar en el historial persistente de REDIS (RPUSH - LTRIM)
        mensaje_guardado = self._repo_mensajes.guardar_mensaje(
            sala_id= sala_id,
            usuario_id=usuario_id,
            nombre_autor=usuario["nombre"],
            contenido=texto,
            fecha_hora=hora_actual,
            max_historial=self._max_historial,
        )

        # Emitir en vivo por REDIS Pub/Sub (PUBLISH)
        evento = {
            "tipo": "mensaje",
            "datos": mensaje_guardado,
        }
        self._bus_eventos.publicar_evento_sala(sala_id, evento)

        return True, "Mensaje enviado", mensaje_guardado

    # Recuperar los ultimos mensajes guardados en la sala
    def obtener_historial_sala(self, sala_id: int, limite: int = 50) -> List[Dict[str, Any]]:
        return self._repo_mensajes.obtener_ultimos_mensajes(sala_id, limite=limite)

    # Calcula la lista actualizada de usuarios online en la sala y la publica por REDIS Pub/Sub para que a todos se les actualice el estado
    # Ademas publica por el canal global el contador de todas las salas (panel izquierdo)
    def _emitir_actualizacion_presencia(
            self,
            sala_id: int,
            accion: str,
            nombre_usuario: str
    ) -> None:

        lista_nombres = self._servicio_sala.obtener_nombres_online(sala_id)

        evento = {
            "tipo": "presencia",
            "datos": {
                # entrada, salida o limpieza (conexiones muertas borradas)
                "accion": accion,
                "usuario": nombre_usuario,
                "usuarios_online": lista_nombres,
                "total_online": len(lista_nombres),
                "hora": datetime.now().strftime("%H:%M:%S"),
            },
        }

        self._bus_eventos.publicar_evento_sala(sala_id, evento)
        self._servicio_sala.publicar_resumen_salas()

    # Salida explicita de una sala (el navegador avisa con navigator.sendBeacon al cerrar/cambiar de pestaña)
    # Es mas rapido que esperar a que Flask detecte que la conexion SSE se corto
    def salir_de_sala(self, sala_id: int, usuario_id: int, conexion_id: str) -> None:
        if self._repo_salas.registrar_salida_usuario(sala_id, usuario_id, conexion_id):
            usuario = self._repo_usuario.obtener_usuario(usuario_id)
            nombre = usuario["nombre"] if usuario else f"Usuario #{usuario_id}"
            self._emitir_actualizacion_presencia(sala_id, "salida", nombre)

    # Cierre de sesion: saca al usuario de todas las salas donde tenga conexiones abiertas
    # Debe llamarse ANTES de borrar el perfil del invitado (para conocer su nombre)
    def desconectar_usuario(self, usuario_id: int) -> None:
        usuario = self._repo_usuario.obtener_usuario(usuario_id)
        nombre = usuario["nombre"] if usuario else f"Usuario #{usuario_id}"

        for sala_id in self._repo_salas.eliminar_usuario_de_salas(usuario_id):
            self._emitir_actualizacion_presencia(sala_id, "salida", nombre)

    # Generador que se coneta al stream SSE de Flask
    # Al abrirse la conexin se registra la conexion como 'online' en la sala
    # Escucha en bucle todos los eventos del canal SUBSCRIBE de REDIS
    # Cada "intervalo_latido" segundos renueva su latido y limpia conexiones muertas
    # Al cerrarse la pestaña o cambia de sala (finally) lo saca de 'online'
    def suscribir_flujo_sala(self, sala_id: int, usuario_id: int, conexion_id: str) -> Iterator[str]:

        usuario = self._repo_usuario.obtener_usuario(usuario_id)
        nombre_usuario = usuario["nombre"] if usuario else f"Usuario #{usuario_id}"

        flujo_redis = self._bus_eventos.escuchar_sala(sala_id)

        try:
            # Avanzamos hasta el primer yield lo que garantiza que SUBSCRIBE ya esta activo
            next(flujo_redis, None)

            # ZADD en REDIS y PUBLISH a todos (incluso el mismo)
            self._repo_salas.registrar_entrada_usuario(sala_id, usuario_id, conexion_id)
            self._repo_salas.limpiar_conexiones_vencidas(sala_id)
            self._emitir_actualizacion_presencia(sala_id, "entrada", nombre_usuario)

            # Indica al navegador que reintente la conexion a los 3 s si se corta
            yield "retry: 3000\n\n"

            ultimo_latido = time.monotonic()

            # Escuchar continua sin vencimineto
            for evento_json in flujo_redis:
                if evento_json:
                    yield f"data: {evento_json}\n\n"
                else:
                    # Comentario SSE keepalive (mantiene vivo el canal y detecta desconexion)
                    yield ": keepalive\n\n"

                # Latido periodico (heartbeat) de esta conexion
                if time.monotonic() - ultimo_latido >= self._intervalo_latido:
                    ultimo_latido = time.monotonic()

                    # Si la conexion ya no existe en Redis (logout o salida por sendBeacon)
                    # se termina el stream, si la pagina sigue abierta el navegador reconecta solo
                    if not self._repo_salas.renovar_presencia(sala_id, usuario_id, conexion_id):
                        break

                    # Borra conexiones de otros que murieron sin avisar (Flask reiniciado, etc.)
                    if self._repo_salas.limpiar_conexiones_vencidas(sala_id) > 0:
                        self._emitir_actualizacion_presencia(sala_id, "limpieza", "")
        finally:
            flujo_redis.close()
            # Salida automatica cuando el navegador corta la conexion SSE
            # ZREM en REDIS + aviso PUBLISH a los que siguen en la sala
            # Solo se avisa si la conexion seguia registrada (evita avisos duplicados)
            if self._repo_salas.registrar_salida_usuario(sala_id, usuario_id, conexion_id):
                self._emitir_actualizacion_presencia(sala_id, "salida", nombre_usuario)