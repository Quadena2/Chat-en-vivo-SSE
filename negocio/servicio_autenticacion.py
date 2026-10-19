from datetime import datetime
from typing import Tuple, Optional, Dict

from werkzeug.security import generate_password_hash, check_password_hash

from datos.contratos.i_repositorio_usuario import IRepositorioUsuario


# Capa de Negocio servicio de autenticacion modo hibrido (registrados + invitados)
# Depende unicamente de la abstraccion IRepositorioUsario


class ServicioAutenticacion:

    # Inyeccion de dependencias
    def __init__(self, repo_usuario: IRepositorioUsuario):
        self._repo_usuario = repo_usuario

    # Registra un usuario permanente con contraseña encriptada
    def registrar_usuario(self, nombre: str, password: str) -> Tuple[bool, str, Optional[int]]:

        nombre_limpio = nombre.strip()


        if len(nombre_limpio) < 3 or len(nombre_limpio) > 20:
            return False, "El nombre debe tener entre 3 y 20 caracteres", None

        if len(password) < 4:
            return False, "El password debe tener al menos 4 caracteres", None

        # Encriptando la contraseña antes de ser enviada a la capa de datos
        password_hash = generate_password_hash(password)
        fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        nuevo_id = self._repo_usuario.crear_usuario(
            nombre = nombre_limpio,
            password_hash = password_hash,
            fecha_registro= fecha_actual,
            es_invitado=False

        )

        if nuevo_id is None:
            return False, f"El  nombre '{nombre_limpio}' ya esta en uso", None

        return True, "Usuario registrado con exito", nuevo_id

    # Verifica credenciales de un usuario registrado
    def iniciar_sesion(self, nombre: str, password: str) -> Tuple[bool, str, Optional[Dict[str, str]]]:

        nombre_limpio = nombre.strip()
        usuario_id = self._repo_usuario.buscar_id_por_nombre(nombre_limpio)

        if usuario_id is None:
            return False, "Usuario no encontrado", None

        usuario = self._repo_usuario.obtener_usuario(usuario_id)

        if not usuario:
            return False, "Error al obtener el perfil del usuario", None

        # Modo hibrido, un invitado temporal no tiene contraseña
        if usuario.get("es_invitado") == "1":
            return False, "Ese nombre pertenece a un invitado activo en este momento", None

        # Comparando la contraseña en texto plano contra el hash guardado en REDIS
        if not check_password_hash(usuario["password_hash"], password):
            return False, "Contraseña incorrecta", None

        # Se devuelve el perfil para que la capa de presentacion guarde id y nombre en la sesion
        return True, "Sesion iniciada correctamente", usuario

    # Crea un perfil temporal sin contraseña si el apodo esta disponible
    def entrar_como_invitado(self, apodo: str) -> Tuple[bool, str, Optional[int]]:

        apodo_limpio = apodo.strip()
        if len(apodo_limpio) < 3 or len(apodo_limpio) > 20:
            return False, "El apodo debe tener entre 3 y 20 caracteres", None

        fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        nuevo_id = self._repo_usuario.crear_usuario(
            nombre=apodo_limpio,
            password_hash="",
            fecha_registro=fecha_actual,
            es_invitado=True,
        )

        if nuevo_id is None:
            return False, f"El apodo '{apodo_limpio}' ya se encuentra ocupado por otro usuario", None

        return True, "Bienvenido como invitado", nuevo_id

    # Si el usuario que sale era invitado entonces ordena al repositorio borrar su perfil y liberar su apodo en REDIS
    # Si era registrado la cuenta no se borra
    def cerrar_sesion(self, usuario_id: int) -> None:
        self._repo_usuario.eliminar_invitado(usuario_id)

    # Devuelve los datos del usuario si aun existe en REDIS
    def obtener_perfil(self, usuario_id: int) -> Optional[Dict[str, str]]:
        return self._repo_usuario.obtener_usuario(usuario_id)








