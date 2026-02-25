# Backend (api.ominis.org) – SSH no funciona desde tu red

## Qué se comprobó

- **EC2:** Instancia `i-04464c8355e364211` en **mx-central-1**, estado `running`, IP pública **78.12.33.205**.
- **Security group** `ominis-haystack-sg`: SSH (22), 80, 443, 8000 desde `0.0.0.0/0`.
- **NACL:** Permite tráfico entrante.
- **Elastic IP:** Asociada a la instancia.
- **Ruta por defecto:** VPC con IGW (subred con salida a internet).
- **EC2 Instance Connect:** `send-ssh-public-key` responde **Success** (AWS llega a la instancia).

Conclusión: el bloqueo no está en la instancia ni en la VPC; está **entre tu red (MacBook/ISP) y el puerto 22** de 78.12.33.205 (timeout antes de conectar).

---

## Si tampoco conecta desde EC2 Instance Connect (consola AWS)

Si al usar **Conectar → EC2 Instance Connect** en la consola sale *"Failed to connect to your instance"*, la conexión va por **proxy de AWS** (no desde tu navegador). Ese fallo suele indicar un problema **en la instancia**:

- **sshd** no está corriendo o se colgó (reiniciar la instancia suele arreglarlo).
- **ec2-instance-connect** (agente que pone la clave temporal) no está activo o falla.
- Disco lleno, OOM u otro error que deja el sistema en mal estado.

**Qué hacer sin SSH:**

1. **Reiniciar la instancia** desde la consola: EC2 → Instancias → seleccionar `ominis-haystack-backend` → Acciones → Estado de la instancia → **Reiniciar**. O desde tu repo:
   ```bash
   ./infrastructure/33-reboot-backend-instance.sh
   ```
2. Esperar 1–2 minutos y volver a intentar **Conectar → EC2 Instance Connect**.
3. (Opcional) Revisar **Salida del sistema** (Actions → Monitorización y solución de problemas → Obtener salida del sistema) para ver errores de arranque o sshd.

---

## Opciones para acceder sin depender de tu SSH directo

### 1. AWS CloudShell (rápido, sin cambiar la instancia)

CloudShell corre en la red de AWS, así que puede conectar a la instancia aunque tu red bloquee el 22.

1. Entra a **AWS Console** → región **mx-central-1**.
2. Abre **CloudShell** (icono de terminal en la barra superior).
3. En CloudShell:

```bash
# Instalar/clonar solo si necesitas el repo; para solo reiniciar el backend:
ssh -i config/ominis-ollama-key.pem -o StrictHostKeyChecking=no ubuntu@78.12.33.205 \
  'sudo systemctl status ominis-backend; sudo systemctl restart ominis-backend; sleep 2; curl -s http://127.0.0.1:8000/v1/health'
```

Para usar el script del repo desde CloudShell tendrías que subir la key y el script o clonar el repo (si tienes acceso por git).

### 2. Otra red (móvil / otra oficina)

Probar desde **otra red** (por ejemplo 4G/5G en el móvil con tethering, o otra WiFi):

```bash
ssh -i config/ominis-ollama-key.pem -o ConnectTimeout=10 ubuntu@78.12.33.205
```

Si desde esa red SSH funciona, el bloqueo es de tu red actual (firewall, ISP, política de salida al puerto 22).

### 3. Session Manager (SSM) – sin abrir puerto 22

Si das a la instancia un **IAM role** con política de SSM, puedes entrar por **Session Manager** desde la consola (no usa puerto 22).

Pasos resumidos:

1. **Crear IAM role** para EC2 con la política administrada `AmazonSSMManagedInstanceCore`.
2. **Asociar el role** a la instancia `i-04464c8355e364211`.
3. **Instalar/activar el agente SSM** en la instancia (en Ubuntu suele venir; si no, habría que hacerlo en un momento en que sí tengas SSH, p. ej. desde CloudShell).
4. En la consola: **EC2 → Instancias → seleccionar la instancia → Conectar → Session Manager**.

Así puedes abrir una shell y, por ejemplo, reiniciar el backend sin depender de que tu red permita SSH al 22.

---

## Comandos útiles (cuando tengas acceso)

Desde cualquier sitio donde SSH o SSM funcione:

```bash
# Estado y logs del backend
sudo systemctl status ominis-backend
sudo journalctl -u ominis-backend -n 80 --no-pager

# Reiniciar
sudo systemctl restart ominis-backend

# Health local
curl -s http://127.0.0.1:8000/v1/health
```

Si quieres, el siguiente paso puede ser un script pequeño que, desde CloudShell, use la key que subas y ejecute estos comandos (o el `32-backend-diagnose-and-restart.sh`) para no tener que teclearlos a mano.
