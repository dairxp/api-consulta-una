# Manual de Despliegue en VPS (Ubuntu/Linux ARM64)

Este documento detalla paso a paso cómo se configuró y desplegó el backend de la Consulta Electoral UNAP en un VPS (como Oracle Cloud) usando `uv`, `pm2` y `cloudflared` (Cloudflare Tunnels).

## 1. Preparación del Entorno (Instalar `uv`)

Si es un servidor nuevo, primero debes instalar `uv`, que es nuestro gestor ultrarrápido para Python.

```bash
# Instalar uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Recargar variables de entorno para que el comando uv funcione
source $HOME/.local/bin/env
```

## 2. Iniciar el Backend con PM2

Para que el servidor de FastAPI corra siempre en segundo plano, usamos PM2.

```bash
# 1. Ir a la carpeta del backend
cd /opt/proyectos/consulta-electoral-unap/backend

# 2. Sincronizar dependencias modernas con uv
uv sync
uv add gunicorn

# 3. Iniciar el backend con PM2 y Gunicorn (Entorno Profesional)
# Gunicorn permite crear múltiples "trabajadores" para aprovechar todos los núcleos del CPU
pm2 start uv --name "backend-consulta-unap" -- run gunicorn app.main:app --workers 3 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

*Nota: Para ver los logs del backend o reiniciarlo, puedes usar:*
- `pm2 logs backend-consulta-unap`
- `pm2 logs backend-consulta-unap --lines 200`
- `pm2 restart backend-consulta-unap`

## 3. Optimización con PgBouncer (Nivel Enterprise)
Para evitar que la base de datos se sature bajo ataques o picos masivos de tráfico, usamos PgBouncer como administrador de conexiones.

### Paso 3.1: Instalar y Configurar PgBouncer
1. Instalar PgBouncer:
   `sudo apt update && sudo apt install pgbouncer -y`
2. Configurar usuarios (`sudo nano /etc/pgbouncer/userlist.txt`):
   Añadir el usuario y contraseña de la BD (exactamente como en tu `.env`):
   `"usuario_postgres" "clave_postgres"`
3. Configurar PgBouncer (`sudo nano /etc/pgbouncer/pgbouncer.ini`):
   ```ini
   [databases]
   * = host=127.0.0.1 port=5432

   [pgbouncer]
   listen_addr = 127.0.0.1
   listen_port = 6432
   auth_type = plain
   auth_file = /etc/pgbouncer/userlist.txt
   pool_mode = transaction
   max_client_conn = 5000
   default_pool_size = 200
   ```
4. Reiniciar: `sudo systemctl restart pgbouncer && sudo systemctl enable pgbouncer`
5. En el archivo `.env` del backend, cambiar el puerto de `5432` a `6432`.

## 4. Exponer el puerto a Internet de forma Profesional (Cloudflare Zero Trust Tunnel)

Ahora que tienes tu dominio oficial `unap.dev`, ya no usamos el túnel temporal. Creamos un túnel permanente y seguro (Zero Trust) que se instala como un servicio de Linux (`systemd`), no en PM2.

### Paso 4.1: Crear el Túnel en Cloudflare
1. Entra a tu cuenta de Cloudflare y ve al menú izquierdo a **Zero Trust**.
2. Ve a **Networks** -> **Connectors** y dale al botón **Create a tunnel**.
3. Elige **Cloudflared**, ponle un nombre (ej. `Backend-UNAP`) y dale a Save.

### Paso 3.2: Instalar el Túnel en el VPS
Copia el comando para Debian/Ubuntu ARM64 (si usas Oracle Cloud Ampere), pégalo en la consola de tu VPS y ejecútalo. Se instalará como un servicio de sistema.
```bash
sudo cloudflared service install eyJhTuTokenSecreto...
```

### Paso 3.3: Configurar la Ruta Pública (Public Hostname)
1. En Cloudflare, dale a **Next**.
2. Configura tu ruta así:
   - Subdomain: `api-dondevoto`
   - Domain: `unap.dev`
   - Service Type: `HTTP`
   - URL: `localhost:8000` (el puerto de tu backend)
3. Dale a **Save hostname**. ¡Tu backend ahora es público en `https://api-dondevoto.unap.dev`!

---

## 4. Mantenimiento y Actualizaciones (Logs y Cambios de Código)

Como un administrador de sistemas profesional, estas son las herramientas que usarás en tu día a día:

### A. ¿Cómo ver los logs del backend para detectar errores?
Para ver en tiempo real quién se conecta a tu API o si hay algún error de base de datos, ejecuta:
```bash
# Ver los logs en tiempo real (puedes usar el ID '0' o el nombre completo)
pm2 logs 0
```
*(Para salir de la vista de logs, presiona `Ctrl + C`)*

### B. ¿Cómo aplicar cambios en el código de producción?
Si modificas tu código en tu computadora y haces un `git push`, en tu VPS debes hacer lo siguiente:
```bash
# 1. Entrar a la carpeta
cd /opt/proyectos/consulta-electoral-unap/backend

# 2. Bajar los nuevos cambios de GitHub
git pull origin main  # (o la rama que uses, ej. dev)

# 3. (Opcional) Si agregaste nuevas librerías, sincronízalas
uv sync

# 4. Reiniciar el servicio para que tome los cambios
pm2 restart 0
```

### C. Comandos Útiles de PM2 para control total
```bash
# Apagar el backend temporalmente
pm2 stop 0

# Encender el backend
pm2 start 0

# Ver el estado de uso de RAM y CPU en tiempo real
pm2 monit

# Guardar la configuración actual (¡Súper importante si agregas un nuevo proyecto a PM2!)
pm2 save
```

### D. ¿Y qué pasa con Cloudflared (el Túnel)?
El túnel funciona de forma independiente a PM2 gracias a `systemd`. Si por algún motivo necesitas revisarlo:
```bash
# Ver el estado del túnel
sudo systemctl status cloudflared

# Reiniciar el túnel (rara vez es necesario)
sudo systemctl restart cloudflared
```

### log ultimos

```bash
pm2 logs 0 --lines 200
```



