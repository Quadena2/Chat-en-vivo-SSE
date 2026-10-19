import re
import uuid

from flask import Blueprint, redirect, url_for, render_template, session, request, jsonify, Response, flash

from negocio.servicio_autenticacion import ServicioAutenticacion
from negocio.servicio_chat import ServicioChat
from negocio.servicio_sala import ServicioSala
from presentacion.rutas.decoradores import crear_decorador_login


# Capa de Presentacion - Rutas del chat en vivo y server-sent events (SSE)

# Solo letras, numeros y guiones (evita que inyecten ":" u otros caracteres en la clave de Redis)
PATRON_CONEXION_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


# Devuelve el ID de conexion enviado por el navegador o genera uno nuevo si no es valido
def _leer_conexion_id() -> str:
    conexion_id = request.args.get("conexion", "")
    if PATRON_CONEXION_ID.match(conexion_id):
        return conexion_id
    return uuid.uuid4().hex


def crear_blueprint_chat(
        servicio_sala: ServicioSala,
        servicio_chat: ServicioChat,
        servicio_auth: ServicioAutenticacion,
        mensajes_por_pagina: int = 50,
) -> Blueprint:
    chat_bp = Blueprint("chat", __name__)
    login_requerido = crear_decorador_login(servicio_auth)

    @chat_bp.route("/chat")
    @chat_bp.route("/chat/<int:sala_id>")
    @login_requerido
    def vista_principal(sala_id: int = 1):
        salas = servicio_sala.listar_salas_con_conectados()
        if not salas:
            servicio_sala.asegurar_salas_iniciales()
            salas = servicio_sala.listar_salas_con_conectados()

        sala_actual = servicio_sala.obtener_sala_detallada(sala_id)
        if not sala_actual:
            return redirect(url_for("chat.vista_principal", sala_id=salas[0]["id"]))

        historial = servicio_chat.obtener_historial_sala(sala_id, limite=mensajes_por_pagina)

        return render_template(
            "chat.html",
            salas=salas,
            sala_actual=sala_actual,
            historial=historial,
            # ID unico de esta pestaña: identifica su conexion SSE en el Sorted Set de presencia
            conexion_id=uuid.uuid4().hex,
            usuario_actual={
                "id": session["usuario_id"],
                "nombre": session["nombre"],
                "es_invitado": session.get("es_invitado", False),
            },
        )

    @chat_bp.route("/salas/crear", methods=["POST"])
    @login_requerido
    def crear_sala():
        nombre = request.form.get("nombre", "")
        descripcion = request.form.get("descripcion", "")
        creador_id = int(session["usuario_id"])

        exito, mensaje, nueva_sala_id = servicio_sala.crear_nueva_sala(
            nombre, descripcion, creador_id
        )
        if not exito:
            flash(mensaje, "error")
            return redirect(url_for("chat.vista_principal"))

        return redirect(url_for("chat.vista_principal", sala_id=nueva_sala_id))

    # Recibe el mensaje en JSON desde fetch() -> lo guarda (RPUSH) y lo publica (PUBLISH)
    @chat_bp.route("/api/salas/<int:sala_id>/mensaje", methods=["POST"])
    @login_requerido
    def enviar_mensaje(sala_id: int):
        datos = request.get_json(silent=True) or {}
        contenido = datos.get("contenido", "")
        usuario_id = int(session["usuario_id"])

        exito, mensaje, msg_guardado = servicio_chat.enviar_mensaje(
            sala_id=sala_id,
            usuario_id=usuario_id,
            contenido=contenido,
        )
        if not exito:
            return jsonify({"ok": False, "error": mensaje}), 400

        return jsonify({"ok": True, "mensaje": msg_guardado}), 201

    # Aviso de salida enviado por navigator.sendBeacon al cerrar o cambiar de pestaña
    @chat_bp.route("/api/salas/<int:sala_id>/salir", methods=["POST"])
    @login_requerido
    def salir_sala(sala_id: int):
        servicio_chat.salir_de_sala(
            sala_id=sala_id,
            usuario_id=int(session["usuario_id"]),
            conexion_id=_leer_conexion_id(),
        )
        return "", 204

    # Conexion SSE (Server-Sent Events): el navegador la mantiene abierta y recibe los eventos de Redis Pub/Sub
    @chat_bp.route("/api/salas/<int:sala_id>/stream")
    @login_requerido
    def stream_sala(sala_id: int):
        if not servicio_sala.existe_sala(sala_id):
            return jsonify({"ok": False, "error": "Sala no encontrada"}), 404

        # Se leen session y request AQUI, el generador corre fuera del contexto de la peticion
        usuario_id = int(session["usuario_id"])
        conexion_id = _leer_conexion_id()

        generador = servicio_chat.suscribir_flujo_sala(
            sala_id=sala_id,
            usuario_id=usuario_id,
            conexion_id=conexion_id,
        )

        return Response(
            generador,
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            }
        )

    return chat_bp