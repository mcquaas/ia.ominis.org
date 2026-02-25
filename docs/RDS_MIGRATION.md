# Migrar backend de PostgreSQL local a RDS

El backend puede estar usando PostgreSQL **local** en la EC2 (instalado por `17-deploy-haystack-backend.sh`). Para pasar a **RDS** (más robusto y permanente):

## Cómo saber si el backend está usando RDS

**Opción 1 — Health (recomendado)**  
El endpoint `/v1/health` devuelve `"database": "rds"` o `"database": "local"` según la URL configurada en el servidor:

```bash
curl -s http://78.12.33.205:8000/v1/health | jq .
# Si ves "database": "rds" → está usando RDS; si "database": "local" → PostgreSQL local.
```

**Opción 2 — En el servidor**  
Con SSH al backend:

```bash
grep -E '^DATABASE_URL=' /opt/ominis-backend/.env
```

Si el host en la URL es un endpoint tipo `*.rds.amazonaws.com`, usa RDS; si es `127.0.0.1`, usa PostgreSQL local.

---

## 1. Crear RDS (ya hecho si ejecutaste el script)

```bash
./infrastructure/29f-create-rds-postgres.sh
```

Esto crea en AWS (cuenta 9...):

- **RDS PostgreSQL 16.6**, `db.t4g.micro`, 20 GB gp3, cifrado, sin acceso público.
- En la misma VPC que el backend; el security group del backend puede conectar por 5432.
- Credenciales y endpoint en `config/rds.txt` (gitignored).

## 2. Exportar datos desde PostgreSQL local (en el servidor backend)

Con SSH (o EC2 Instance Connect) al backend:

```bash
# En el servidor backend
sudo -u postgres pg_dump -Fc ominis_haystack > /tmp/ominis_haystack.dump
```

Si prefieres SQL plano (por si RDS tiene extensiones distintas):

```bash
sudo -u postgres pg_dump ominis_haystack > /tmp/ominis_haystack.sql
```

## 3. Configurar .env en el backend para RDS

En el servidor, edita `/opt/ominis-backend/.env`. Sustituye las URLs de base de datos por las de RDS (los valores están en `config/rds.txt` en tu máquina local). Puedes generar las líneas con:

```bash
./infrastructure/29g-update-backend-env-rds.sh
```

y copiar las dos líneas que imprime al .env del servidor.

```env
DATABASE_URL=postgresql+asyncpg://ominis_admin:PASSWORD@RDS_ENDPOINT:5432/ominis_haystack
DATABASE_URL_SYNC=postgresql://ominis_admin:PASSWORD@RDS_ENDPOINT:5432/ominis_haystack
```

Sustituye `PASSWORD` por `RDS_MASTER_PASSWORD` y `RDS_ENDPOINT` por el endpoint de `config/rds.txt`.  
O desde tu máquina, si tienes `config/rds.txt`:

```bash
source config/rds.txt
# Escapar '&' y '#' si el password los tiene
echo "DATABASE_URL=postgresql+asyncpg://${RDS_MASTER_USER}:${RDS_MASTER_PASSWORD}@${RDS_ENDPOINT}:${RDS_PORT}/${RDS_DB_NAME}"
echo "DATABASE_URL_SYNC=postgresql://${RDS_MASTER_USER}:${RDS_MASTER_PASSWORD}@${RDS_ENDPOINT}:${RDS_PORT}/${RDS_DB_NAME}"
```

## 4. Restaurar el dump en RDS

RDS ya tiene la base `ominis_haystack` vacía. Desde una máquina que pueda conectar a RDS (por ejemplo el **backend**, una vez que pueda resolver el endpoint):

**Opción A: desde el backend (recomendado)**

En el servidor backend, después de poner el .env con RDS pero **antes** de reiniciar la app:

```bash
# Instalar cliente si no está
sudo apt-get install -y postgresql-client

# Restaurar (sustituir RDS_ENDPOINT y PASSWORD por los de config/rds.txt)
PGPASSWORD='PASSWORD' pg_restore -h RDS_ENDPOINT -U ominis_admin -d ominis_haystack --no-owner --no-acl /tmp/ominis_haystack.dump
```

Si usaste `.sql`:

```bash
PGPASSWORD='PASSWORD' psql -h RDS_ENDPOINT -U ominis_admin -d ominis_haystack -f /tmp/ominis_haystack.sql
```

**Opción B: desde tu máquina**

Solo si tu IP está permitida en el security group de RDS (no es el caso por defecto; el RDS solo permite el backend). Si abres temporalmente tu IP:

```bash
pg_restore -h RDS_ENDPOINT -U ominis_admin -d ominis_haystack --no-owner --no-acl -f /tmp/ominis_haystack.dump
```

## 5. Extensiones en RDS

Si el dump usa extensiones (p. ej. `vector` para pgvector), créalas en RDS antes de restaurar:

```bash
PGPASSWORD='PASSWORD' psql -h RDS_ENDPOINT -U ominis_admin -d ominis_haystack -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

(El backend Haystack usa pgvector; la extensión está disponible en RDS PostgreSQL.)

## 6. Alembic y reinicio

En el servidor, con el .env ya apuntando a RDS:

```bash
cd /opt/ominis-backend && source venv/bin/activate
alembic upgrade head
sudo systemctl restart ominis-backend
```

Comprueba que la API responde y que el dashboard/login funcionan.

## 7. Dejar de usar PostgreSQL local (opcional)

Si todo va bien, puedes deshabilitar el servicio PostgreSQL local para ahorrar recursos:

```bash
sudo systemctl stop postgresql
sudo systemctl disable postgresql
```

No elimines los datos locales hasta tener varios días de uso estable con RDS.

## Resumen

| Paso | Acción |
|------|--------|
| 1 | RDS ya creado con `29f-create-rds-postgres.sh` |
| 2 | En backend: `pg_dump` de `ominis_haystack` → `/tmp/ominis_haystack.dump` |
| 3 | En backend: .env con `DATABASE_URL` y `DATABASE_URL_SYNC` apuntando a RDS |
| 4 | En backend: `pg_restore` (o `psql -f`) hacia RDS; crear extensión `vector` si hace falta |
| 5 | `alembic upgrade head` y `systemctl restart ominis-backend` |
| 6 | Probar API/dashboard; opcionalmente deshabilitar PostgreSQL local |
