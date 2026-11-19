# Abrir TransportExperience desde otro equipo (túnel para la sustentación)

El MVP corre en el equipo del proyecto (sección 4.5 del plan). Para que el docente lo abra
desde su celular o desde un PC de la universidad, se expone **temporalmente** con
**Cloudflare Tunnel** (modo rápido, gratis, sin cuenta). El túnel entrega una URL pública
`https://...trycloudflare.com` que llega al equipo del proyecto.

Hay que tener en cuenta lo siguiente:

- Funciona **solo mientras el equipo del proyecto esté prendido**, con la API, el frontend
  y los dos túneles corriendo.
- **Las URL cambian cada vez que se reinicia un túnel.** Si se reinicia, hay que repetir
  los pasos 4 y 5.
- Son dos túneles: uno para la API (puerto 8000) y otro para la página (puerto 5173).

## 0. Instalar cloudflared (una sola vez)

En PowerShell:

```powershell
winget install --id Cloudflare.cloudflared
```

Se instala como un programa del sistema, igual que Docker Desktop. Cierra y vuelve a abrir
la terminal, y comprueba con `cloudflared --version`.

## 1. Prender el sistema

Terminal 1, en la carpeta del proyecto:

```powershell
.venv\Scripts\activate
docker compose up -d --wait
uvicorn app.main:app
```

Terminal 2, **dentro de `frontend/`**:

```powershell
cd frontend
python -m http.server 5173
```

> ⚠️ El servidor de archivos **siempre se arranca dentro de `frontend/`**. Si se arranca
> en la raíz del proyecto, el túnel publicaría todo el repositorio, **incluido el `.env`
> con las claves**.

## 2. Túnel de la API

Terminal 3:

```powershell
cloudflared tunnel --url http://127.0.0.1:8000
```

En lo que imprime aparece un recuadro con una URL `https://<palabras>.trycloudflare.com`.
Esa es la **URL de la API**. Compruébala abriendo `<URL de la API>/salud` en el navegador.

## 3. Túnel de la página

Terminal 4:

```powershell
cloudflared tunnel --url http://127.0.0.1:5173
```

Esa es la **URL de la página**, la que se le da al docente.

## 4. Decirle a la página dónde está la API

En la carpeta `frontend/`, copia `config.local.example.js` como `config.local.js` y cambia
la URL por la **URL de la API**, sin `/` al final:

```js
window.TRANSPORT_API_BASE = "https://<palabras-api>.trycloudflare.com";
```

`config.local.js` no se sube al repositorio (está en `.gitignore`).

## 5. Dejar que la página llame a la API (CORS)

En el `.env`, agrega la **URL de la página** al final de `CORS_ORIGENES`, separada por coma
y sin `/` al final:

```
CORS_ORIGENES=http://localhost:5173,http://127.0.0.1:5173,https://<palabras-pagina>.trycloudflare.com
```

Detén la API (`Ctrl + C` en la terminal 1) y vuelve a correr `uvicorn app.main:app`: el
`.env` solo se lee al arrancar.

## 6. Probar desde afuera

Desde un celular **con datos móviles, no con el Wi-Fi de la casa**, abre la URL de la
página y entra a la pantalla de inicio de sesión: en el recuadro "Backend real" debe decir
**"Backend conectado en https://...trycloudflare.com"**.
Si dice "Backend sin conexión", revisa los pasos 4 y 5.

La documentación de la API también queda pública en `<URL de la API>/docs`.

## 7. Al terminar

1. `Ctrl + C` en las terminales de los dos túneles. Las URL dejan de funcionar al instante.
2. **Borra `frontend/config.local.js`**. Si no, la página local seguirá buscando la API en
   el túnel que ya no existe.
3. Quita la URL del túnel de `CORS_ORIGENES` en el `.env`.

## Seguridad

- **Nunca se abre un túnel a Adminer (8080) ni a PostgreSQL (5432).** Solo 8000 y 5173.
- Los usuarios de desarrollo tienen una contraseña conocida (está en el README). Mientras
  el túnel esté abierto, quien tenga la URL puede entrar como administrador. Por eso se
  abre solo durante la demostración y se cierra al terminar.
- Para la demostración, `PAGOS_PROVEEDOR=falso` en el `.env`: no se toca ninguna pasarela.

## Recomendación

Haz un ensayo completo el día anterior desde el celular, con datos móviles. El día de la
sustentación, arranca los túneles con tiempo: las URL son nuevas cada vez.
