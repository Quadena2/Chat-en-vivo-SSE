# Gestor unico de conexion con Redis


import redis
from config import Configuracion

class GestorConexionRedis:

    # Administra el pool de conexion TCP hacia redis
    def __init__(self, config=Configuracion):
        self._pool = redis.ConnectionPool(
            host=config.REDIS_HOST,
            port=config.REDIS_PORT,
            db=config.REDIS_DB,
            password=config.REDIS_PASSWORD,

            # Devuelve str en lugar de bytes
            decode_responses=True,

            # Falla rapido si el contenedor de docker esta apagado
            socket_connect_timeout=5,
            socket_timeout=5,
        )

    # Devuelve un cliente Redis que reutiliza el pool compartido
    def obtener_cliente(self) -> redis.Redis:

        return redis.Redis(connection_pool=self._pool)

    # Ejecuta el "PING", devuelve "True" si el contenedor Redis responde con "PONG"
    def verificar_conexion(self) -> bool:
        try:
            return bool(self.obtener_cliente().ping())
        except redis.exceptions.RedisError:
            return False
