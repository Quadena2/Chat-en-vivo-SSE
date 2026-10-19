

# Punto de entrada e inyeccion de dependencias

import os

from flask import Flask
from config import Configuracion

# Capa 1 - Presentacion
from presentacion.rutas.auth import crear_blueprint_auth
from presentacion.rutas.chat import crear_blueprint_chat

# Capa 2 - Negocio
from negocio.servicio_autenticacion import ServicioAutenticacion
from negocio.servicio_chat import ServicioChat
from negocio.servicio_sala import ServicioSala

# Capa 3 - Datos
from datos.gestor_redis import GestorConexionRedis
from datos.repositorios.repositorio_usuario_redis import RepositorioUsuarioRedis
from datos.repositorios.repositorio_sala_redis import RepositorioSalaRedis
from datos.repositorios.repositorio_mensaje_redis import RepositorioMensajeRedis
from datos.repositorios.bus_eventos_redis import BusEventosRedis

# Indicando a Flask donde se encuentran los templates
def crear_aplicacion() -> Flask:

    ruta_presentacion = os.path.join(os.path.dirname(__file__), "presentacion")
    app = Flask(
        __name__,
        template_folder=os.path.join(ruta_presentacion, "templates"),
        static_folder=os.path.join(ruta_presentacion, "static"),
    )
    app.config.from_object(Configuracion)

    # Instancias el gestor de conexion (Pool unico hacia Redis)
    gestor_redis = GestorConexionRedis(config=Configuracion)

    if not gestor_redis.verificar_conexion():
        raise RuntimeError(
            f"No se pudo conectar a Redis en {Configuracion.REDIS_HOST}:{Configuracion.REDIS_PORT}. "
            "Verifica que Redis este levantado (Docker, WSL2 o servicio MSI de Windows) "
            "y que REDIS_HOST, REDIS_PORT y REDIS_PASSWORD del .env sean correctos"
        )

    # Instanciar Repositorios inyectando el gestor de redis
    repo_usuario = RepositorioUsuarioRedis(gestor_redis)
    repo_sala = RepositorioSalaRedis(gestor_redis, ttl_presencia=Configuracion.PRESENCIA_TTL_SEGUNDOS)
    repo_mensaje = RepositorioMensajeRedis(gestor_redis)
    bus_eventos = BusEventosRedis(gestor_redis)

    # Instanciar servicios (Negocio)
    servicio_auth = ServicioAutenticacion(repo_usuario=repo_usuario)
    servicio_sala = ServicioSala(
        repo_salas=repo_sala,
        repo_usuarios=repo_usuario,
        bus_eventos=bus_eventos,
    )
    servicio_chat = ServicioChat(
        repo_mensajes=repo_mensaje,
        repo_salas=repo_sala,
        repo_usuario=repo_usuario,
        bus_eventos=bus_eventos,
        servicio_sala=servicio_sala,
        max_historial=Configuracion.MAX_MENSAJES_HISTORIAL,
        intervalo_latido=Configuracion.INTERVALO_LATIDO_SEGUNDOS,
    )

    # Crear las salas iniciales ("General")
    servicio_sala.asegurar_salas_iniciales()

    # Registrar Blueprints de Presentacion inyectando los servicios
    app.register_blueprint(crear_blueprint_auth(servicio_auth, servicio_chat))
    app.register_blueprint(crear_blueprint_chat(
        servicio_sala,
        servicio_chat,
        servicio_auth,
        mensajes_por_pagina=Configuracion.MENSAJES_POR_PAGINA,
    ))

    return app

if __name__ == "__main__":

    app_chat = crear_aplicacion()

    # threaded=True es obligatorio: cada conexion SSE abierta ocupa un hilo de Flask
    app_chat.run(
        host=Configuracion.FLASK_HOST,
        port=Configuracion.FLASK_PORT,
        debug=Configuracion.FLASK_DEBUG,
        threaded=True,
    )
