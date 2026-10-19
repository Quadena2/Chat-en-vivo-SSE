from flask import Blueprint, session, redirect, url_for, render_template, request, flash

from negocio.servicio_autenticacion import ServicioAutenticacion
from negocio.servicio_chat import ServicioChat


# Capa de presentacion - rutas de autenticacion (Login, Registro e Invitado)
# Solo se comunica con la capa de negocio

def crear_blueprint_auth(servicio_auth: ServicioAutenticacion, servicio_chat: ServicioChat) -> Blueprint:

    auth_bp = Blueprint('auth', __name__)

    # Si la sesion se encuentra activa en FLask lo redirige directo al chat
    @auth_bp.route("/", methods=["GET"])
    def inicio():

        if "usuario_id" in session:
            return redirect(url_for("chat.vista_principal"))

        return render_template("login.html")

    # Procesa el formulario de inicio de sesion para usuarios registrados
    @auth_bp.route("/login", methods=["POST"])
    def login():

        nombre = request.form.get("nombre", "")
        password = request.form.get("password", "")

        exito, mensaje, usuario = servicio_auth.iniciar_sesion(nombre, password)
        if not exito:
            flash(mensaje, "error")
            return redirect(url_for("auth.inicio"))

        # Guardando datos basicos en la cookie de sesion firmada de Flask
        session["usuario_id"] = int(usuario["id"])
        session["nombre"] = usuario["nombre"]
        session["es_invitado"] = False

        return redirect(url_for("chat.vista_principal"))

    # Procesa el formulario de creacion de cuenta permanente
    @auth_bp.route("/registro", methods=["POST"])
    def registro():

        nombre = request.form.get("nombre", "")
        password = request.form.get("password", "")

        exito, mensaje, nuevo_id = servicio_auth.registrar_usuario(nombre, password)
        if not exito:
            flash(mensaje, "error")
            return redirect(url_for("auth.inicio"))

        session["usuario_id"] = nuevo_id
        session["nombre"] = nombre.strip()
        session["es_invitado"] = False

        return redirect(url_for("chat.vista_principal"))

    # Permitir entrada rapida con un apodo tempóral
    @auth_bp.route("/invitado", methods=["POST"])
    def invitado():

        apodo = request.form.get("apodo", "")

        exito, mensaje, nuevo_id = servicio_auth.entrar_como_invitado(apodo)
        if not exito:
            flash(mensaje, "error")
            return  redirect(url_for("auth.inicio"))

        session["usuario_id"] = nuevo_id
        session["nombre"] = apodo.strip()
        session["es_invitado"] = True

        return redirect(url_for("chat.vista_principal"))

    # Cierre de sesion y limpia el perfil en REDIS si era uun nivitado
    @auth_bp.route("/logout", methods=["POST"])
    def logout():

        usuario_id = session.get("usuario_id")
        if usuario_id:
            # 1. Lo saca de todas las salas y avisa en vivo (antes de borrar su perfil)
            servicio_chat.desconectar_usuario(int(usuario_id))
            # 2. Si era invitado se borra su perfil y se libera el apodo
            servicio_auth.cerrar_sesion(int(usuario_id))
        session.clear()
        flash("Has salido del chat correctamente", "info")

        return redirect(url_for("auth.inicio"))

    return auth_bp
