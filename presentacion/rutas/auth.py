from flask import Blueprint, session, redirect, url_for, render_template, request, flash

from negocio.servicio_autenticacion import ServicioAutenticacion
from negocio.servicio_chat import ServicioChat


# Capa de presentacion - rutas de autenticacion (Login, Registro, Invitado, Logout y Eliminar Cuenta)
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

    # Cierre de sesion y limpia el perfil en REDIS si era un invitado
    @auth_bp.route("/logout", methods=["POST"])
    def logout():

        usuario_id = session.get("usuario_id")
        era_invitado = session.get("es_invitado", False)
        if usuario_id:
            uid = int(usuario_id)
            # 1. Lo saca de todas las salas y avisa en vivo (antes de borrar su perfil)
            servicio_chat.desconectar_usuario(uid)
            # 2. Si era invitado se borra su perfil, se libera el apodo y sus mensajes pasan a Usuario desconocido
            servicio_auth.cerrar_sesion(uid)
            if era_invitado:
                servicio_chat.anonimizar_mensajes_usuario(uid)
        session.clear()
        flash("Has salido del chat correctamente", "info")

        return redirect(url_for("auth.inicio"))

    # Elimina definitivamente la cuenta (tanto para usuarios registrados como invitados)
    # y cambia el autor de todos sus mensajes enviados a "Usuario desconocido"
    @auth_bp.route("/eliminar-cuenta", methods=["POST"])
    def eliminar_cuenta():

        usuario_id = session.get("usuario_id")
        if usuario_id:
            uid = int(usuario_id)
            # 1. Lo saca de todas las salas en vivo
            servicio_chat.desconectar_usuario(uid)
            # 2. Cambia con LSET el autor de sus mensajes a "Usuario desconocido" y avisa por Pub/Sub
            servicio_chat.anonimizar_mensajes_usuario(uid)
            # 3. Borra usuario:{id}, libera indice:usuario:nombre, SREM usuarios y DECR contador:usuarios
            servicio_auth.eliminar_cuenta(uid)

        session.clear()
        flash("Tu cuenta fue eliminada y tus mensajes pasaron a 'Usuario desconocido'", "info")

        return redirect(url_for("auth.inicio"))

    return auth_bp
