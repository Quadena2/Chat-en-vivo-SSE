
"""
Canales Redis que gestiona esta clase
    canal:sala:{id}     Canal Pub/Sub por donde viajan mensajes y presencia de UNA sala
    canal:global        Canal Pub/Sub que escuchan TODOS (contadores de cada sala, salas nuevas)
"""
import json
from typing import Dict, Any, Iterator

from datos.contratos.i_bus_eventos import IBusEventos
from datos.gestor_redis import GestorConexionRedis


class BusEventosRedis(IBusEventos):

    CANAL_GLOBAL = "canal:global"

    def __init__(self, gestor_redis: GestorConexionRedis):
        self._gestor = gestor_redis

    @property
    def _cliente(self):
        return self._gestor.obtener_cliente()

    @staticmethod
    def _nombre_canal(sala_id: int) -> str:
        return f"canal:sala:{sala_id}"

    # Convierte el diccionario del evento a JSON y lo emite por el canal indicado
    # Devuelve el nro de clientes que recibieron el mensaje en ese instante
    def _publicar(self, canal: str, evento: Dict[str, Any]) -> int:
        carga_json = json.dumps(evento, ensure_ascii=False)

        # PUBLISH envia el mensaje a todos los suscriptores activos del canal
        # PUBLISH funciona como una estacion de radio, envia carga_json al canal "canal:sala:1", redis no guarda esto en el disco duro, simplemente toma el texto y se lo reenvia (menos 1 ms) a todos los clientes que esten escuchando ese canal en ese momento
        # Devuelve un entero con la cantidad de oyentes que lo recibieron
        return int(self._cliente.publish(canal, carga_json))

    # Evento solo para los conectados en la sala (mensajes nuevos, lista de usuarios online)
    def publicar_evento_sala(
            self,
            sala_id: int,
            evento: Dict[str, Any]
    ) -> int:
        return self._publicar(self._nombre_canal(sala_id), evento)

    # Evento para todos los conectados de la aplicacion (contadores de todas las salas)
    def publicar_evento_global(self, evento: Dict[str, Any]) -> int:
        return self._publicar(self.CANAL_GLOBAL, evento)

    # Generador que abre una suscripcion al canal de la sala + canal global y cede (yield) cada nuevo evento en formato JSON apenas llegue desde Redis
    def escuchar_sala(self, sala_id: int) -> Iterator[str]:

        canal = self._nombre_canal(sala_id)

        # Creamos un objeto PubSub
        # cliente.pubsub(ignore_subscribe_messages=True) crea un obejto receptor de radio en redis-py, el parametro ignore_subscribe_messages=True por defecto apenas te suscribes a un canal, REDIS envia un mensaje de confirmacion "Te has suscrito con exito", al poner True filtras ese ruido y solo recibes los mensajes reales del chat
        pubsub = self._cliente.pubsub(ignore_subscribe_messages=True)

        # pubsub.subscribe(...) ejecuta el comando SUBSCRIBE canal:sala:1 canal:global en REDIS (una sola conexion escucha los 2 canales)
        # cuando llega un mensaje pasa por yield str(mensaje["data"]) y va directo al navegador del usuario
        pubsub.subscribe(canal, self.CANAL_GLOBAL)

        # try -- finally (unsubscribe y close), cuando un usuario cierra la pestaña del navegador o cambia de sala, flask interrumpe el generador "GeneratorExit"
        # el bloque finally ejecuta automaticamente "desuscribe" al usuario en REDIS y pubsub.close() para que la conexion TCP regrese al _pool y no se agoten las conexiones disponibles
        try:
            # Confirma que el SUSCRIBE ya esta activo en REDIS
            yield ""

            # Bucle con timeout de 1 s para no chocar con el socket_timeout=5
            while True:
                mensaje = pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if mensaje and mensaje.get("type") == "message":
                    yield str(mensaje["data"])
                else:
                    # Vacio para mantener viva la conexion SSE
                    yield ""

        finally:
            # Al cerrar la pestaña el usuario liberamos en canal y devolvemos la conexion TCP al ConecctionPool de Redis
            try:
                pubsub.unsubscribe()
            finally:
                pubsub.close()
