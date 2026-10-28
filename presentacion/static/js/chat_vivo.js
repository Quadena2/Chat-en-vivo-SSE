document.addEventListener("DOMContentLoaded", () => {
    const config = window.CHAT_CONFIG;
    const contenedorMensajes = document.getElementById("contenedor-mensajes");
    const formMensaje = document.getElementById("form-mensaje");
    const inputMensaje = document.getElementById("input-mensaje");
    const listaOnline = document.getElementById("lista-usuarios-online");
    const contadorOnline = document.getElementById("contador-online");
    const estadoConexion = document.getElementById("estado-conexion");
    const listaSalas = document.getElementById("lista-salas");

    const bajarScroll = () => {
        if (contenedorMensajes) {
            contenedorMensajes.scrollTop = contenedorMensajes.scrollHeight;
        }
    };
    bajarScroll();

    const escaparHTML = (texto) => {
        const div = document.createElement("div");
        div.textContent = texto;
        return div.innerHTML;
    };

    const cambiarEstado = (texto, color) => {
        if (!estadoConexion) return;
        estadoConexion.textContent = texto;
        estadoConexion.className = `text-[11px] px-2 py-0.5 rounded-full bg-${color}-500/10 text-${color}-400 border border-${color}-500/20`;
    };

    const agregarMensajeDOM = (msg) => {
        const esMio = Number(msg.usuario_id) === Number(config.usuarioId);
        const wrapper = document.createElement("div");
        wrapper.className = `flex flex-col ${esMio ? "items-end" : "items-start"}`;

        wrapper.innerHTML = `
            <div class="flex items-baseline gap-2 mb-1">
                <span data-autor-uid="${Number(msg.usuario_id)}"
                      class="text-xs font-semibold ${esMio ? "text-indigo-400" : "text-emerald-400"}">
                    ${escaparHTML(msg.autor)}
                </span>
                <span class="text-[10px] text-slate-500">${escaparHTML(msg.fecha_hora)}</span>
            </div>
            <div class="max-w-lg px-3.5 py-2 rounded-2xl text-sm break-words ${
                esMio ? "bg-indigo-600 text-white rounded-br-none" : "bg-slate-800 text-slate-100 rounded-bl-none"
            }">
                ${escaparHTML(msg.contenido)}
            </div>
        `;
        contenedorMensajes.appendChild(wrapper);
        bajarScroll();
    };

    // Evento "usuario_eliminado": cambia en vivo el nombre del autor a "Usuario desconocido" en los mensajes de la pantalla
    const anonimizarMensajesDOM = (datos) => {
        if (!contenedorMensajes) return;
        const etiquetasAutor = contenedorMensajes.querySelectorAll(
            `[data-autor-uid="${Number(datos.usuario_id)}"]`
        );
        etiquetasAutor.forEach((span) => {
            span.textContent = datos.nuevo_autor || "Usuario desconocido";
            span.setAttribute("data-autor-uid", "0");
        });
    };

    // Evento "presencia" (canal:sala:{id}): lista de nombres conectados en ESTA sala
    const actualizarPresenciaDOM = (datos) => {
        // 1. Actualiza contador derecho
        if (contadorOnline) contadorOnline.textContent = datos.total_online;

        // 2. Actualiza lista de nombres conectados a la derecha
        if (listaOnline) {
            listaOnline.innerHTML = "";
            datos.usuarios_online.forEach((nombre) => {
                const li = document.createElement("li");
                li.className = "flex items-center gap-2 px-2 py-1.5 rounded-lg bg-slate-950/50 text-slate-200";
                li.innerHTML = `
                    <span class="w-2 h-2 rounded-full bg-emerald-400"></span>
                    <span class="truncate">${escaparHTML(nombre)}</span>
                `;
                listaOnline.appendChild(li);
            });
        }
    };

    // Crea en el panel izquierdo el enlace de una sala que se creo despues de cargar la pagina
    const crearEnlaceSala = (sala) => {
        const enlace = document.createElement("a");
        enlace.href = `${config.urlChat}/${sala.id}`;
        enlace.className = "flex items-center justify-between px-3 py-2 rounded-lg text-sm transition text-slate-400 hover:bg-slate-800 hover:text-slate-200";
        enlace.innerHTML = `
            <span class="truncate"># ${escaparHTML(sala.nombre)}</span>
            <span id="badge-sala-${sala.id}" class="text-xs px-1.5 py-0.5 rounded bg-slate-800 text-slate-400">0</span>
        `;
        listaSalas.appendChild(enlace);
        return enlace.querySelector(`#badge-sala-${sala.id}`);
    };

    // Evento "salas" (canal:global): numero de conectados de TODAS las salas + salas nuevas
    const actualizarSalasDOM = (salas) => {
        salas.forEach((sala) => {
            let badge = document.getElementById(`badge-sala-${sala.id}`);
            if (!badge && listaSalas) badge = crearEnlaceSala(sala);
            if (badge) badge.textContent = sala.conectados;
        });
    };

    // Conexión SSE hacia Flask -> Redis SUBSCRIBE (canal:sala:{id} + canal:global)
    const fuenteEventos = new EventSource(config.urlStream);

    fuenteEventos.onopen = () => cambiarEstado("En vivo", "emerald");

    fuenteEventos.onmessage = (evento) => {
        const payload = JSON.parse(evento.data);
        if (payload.tipo === "mensaje") {
            agregarMensajeDOM(payload.datos);
        } else if (payload.tipo === "presencia") {
            actualizarPresenciaDOM(payload.datos);
        } else if (payload.tipo === "salas") {
            actualizarSalasDOM(payload.datos);
        } else if (payload.tipo === "usuario_eliminado") {
            anonimizarMensajesDOM(payload.datos);
        }
    };

    fuenteEventos.onerror = () => {
        // CONNECTING = el navegador reintenta solo / CLOSED = el servidor rechazo la conexion (401/404)
        if (fuenteEventos.readyState === EventSource.CLOSED) {
            cambiarEstado("Desconectado", "red");
        } else {
            cambiarEstado("Reconectando...", "amber");
        }
    };

    // Al cerrar la pestaña, recargar o cambiar de sala:
    // 1. sendBeacon avisa al servidor que esta conexion sale (llega aunque la pagina se este cerrando)
    // 2. se cierra el EventSource para liberar el hilo de Flask y la suscripcion de Redis
    let salidaAvisada = false;
    const avisarSalida = () => {
        if (salidaAvisada) return;
        salidaAvisada = true;
        if (navigator.sendBeacon) navigator.sendBeacon(config.urlSalir);
        fuenteEventos.close();
    };
    window.addEventListener("pagehide", avisarSalida);

    // Si el navegador restaura la pagina desde su cache (boton "atras"), se recarga para reconectar
    window.addEventListener("pageshow", (e) => {
        if (e.persisted) window.location.reload();
    });

    // Envío de mensajes por Fetch POST
    if (formMensaje) {
        formMensaje.addEventListener("submit", async (e) => {
            e.preventDefault();
            const texto = inputMensaje.value.trim();
            if (!texto) return;

            inputMensaje.value = "";
            inputMensaje.focus();

            try {
                const respuesta = await fetch(config.urlMensaje, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ contenido: texto }),
                });

                if (respuesta.status === 401) {
                    window.location.href = "/";
                    return;
                }

                if (!respuesta.ok) {
                    const datos = await respuesta.json().catch(() => ({}));
                    // Se devuelve el texto al input para no perder lo escrito
                    inputMensaje.value = texto;
                    alert(datos.error || `Error al enviar mensaje (HTTP ${respuesta.status})`);
                }
                // Si todo salio bien NO se dibuja aqui: el mensaje llega por SSE (PUBLISH) igual que a los demas
            } catch (err) {
                console.error("Error de red:", err);
                inputMensaje.value = texto;
                alert("No se pudo conectar con el servidor");
            }
        });
    }
});
