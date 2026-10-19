from functools import wraps

from flask import session, redirect, url_for, request, jsonify

from negocio.servicio_autenticacion import ServicioAutenticacion


# Middlewares - proteccioon de rutas en Flask

# Devuevel el decorador @login_requerido inyectado con el servicio de autenticacion
# Verifica que exista una sesion en Flask y que el usuario siga existiendo en REDIS
def crear_decorador_login(servicio_auth: ServicioAutenticacion):

    def login_requerido(f):

        @wraps(f)
        def decorada(*args, **kwargs):
            usuario_id = session.get('usuario_id')
            if not usuario_id or not servicio_auth.obtener_perfil(int(usuario_id)):
                session.clear()

                # Las rutas /api/ son llamadas por JavaScript (fetch / EventSource):
                # se responde JSON 401 en vez de redirigir a una pagina HTML
                if request.path.startswith("/api/"):
                    return jsonify({"ok": False, "error": "Sesion expirada, vuelve a iniciar sesion"}), 401

                return redirect(url_for("auth.inicio"))
            return f(*args, **kwargs)

        return decorada

    return login_requerido