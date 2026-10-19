"""
Claves Redis que gestiona esta clase:
    id:mensaje              String      Secuencia global para IDs de mensajes (INCR)
    sala:{id}:mensajes      List        Lista cronologica de mensajes en formato JSON
    contador:mensajes       String      Total historico de mensajes enviados (INCR)
"""
import json
from typing import Dict, Any, List

from datos.contratos.i_repositorio_mensaje import IRepositorioMensaje
from datos.gestor_redis import GestorConexionRedis


class RepositorioMensajeRedis(IRepositorioMensaje):

    CLAVE_SECUENCIA_ID ="id:mensaje"
    CLAVE_CONTADOR_MENSAJES = "contador:mensajes"

    def __init__(self, gestor_redis: GestorConexionRedis):
        self._gestor = gestor_redis

    @property
    def _cliente(self):
        return self._gestor.obtener_cliente()

    @staticmethod
    def _clave_mensaje_sala(sala_id: int) -> str:
        return f"sala:{sala_id}:mensajes"

    # Genera el ID del mensaje, lo serializa a JSON y lo guarda al final de la lista de la sala, recortando los menasjes antiguos para no saturar la RAM
    def guardar_mensaje(
            self,
            sala_id: int,
            usuario_id: int,
            nombre_autor: str,
            contenido: str,
            fecha_hora: str,
            max_historial: int = 100,
    ) -> Dict[str, Any]:

        cliente = self._cliente

        # ID atomico para el mensaje
        mensaje_id = cliente.incr(self.CLAVE_SECUENCIA_ID)

        mensaje_dict = {
            "id": mensaje_id,
            "sala_id": sala_id,
            "usuario_id": usuario_id,
            "autor": nombre_autor,
            "contenido": contenido,
            "fecha_hora": fecha_hora,
        }

        # Serializamos el diccionario a un texto JSON para guardarlo en la lista
        mensaje_json = json.dumps(mensaje_dict, ensure_ascii=False)
        clave_lista = self._clave_mensaje_sala(sala_id)

        # Pipeline, agrega al final RPUSH, recorta la lista LTRIM y suma al contador
        tuberia = cliente.pipeline(transaction=True)

        # RPUSH inserta el nuevo mensaje al final (derecha) de la lista, asi queda ordenada por tiempo izquierda (mas viejo) a derecha (mas nuevo)
        tuberia.rpush(clave_lista, mensaje_json)

        # LTRIM recorta la lista para que solo conserve los elementos dentro del rango indicado y luego borre el resto automaticamente
        tuberia.ltrim(clave_lista, -max_historial, -1)
        tuberia.incr(self.CLAVE_CONTADOR_MENSAJES)
        tuberia.execute()

        return mensaje_dict

    # Devuelve los ultimos N mensajes de la sala en orden cronologico
    def obtener_ultimos_mensajes(
            self,
            sala_id: int,
            limite: int = 50
    ) -> List[Dict[str, Any]]:

        clave_lista = self._clave_mensaje_sala(sala_id)

        # LRANGE extrae los elementos de la lista entre dos posiciones, en REDIS -1 es el último elemento, -2 el penúltimo y -50 es el elemento ubicado 50 posiciones antes del final
        mensajes_json = self._cliente.lrange(clave_lista, -limite, -1)

        return [json.loads(msg) for msg in mensajes_json]









