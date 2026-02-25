# Echar a andar la ingesta sin afectar el backend

La ingesta (pipeline nocturno) consume mucha CPU/RAM. Para que **no afecte el backend** debe correr en un **worker separado**. El backend solo sirve la API y lee FAISS/PostgreSQL; el worker es el que ingesta, chunkea, embebe e indexa.

## Pasos (una sola vez)

### 1. Lanzar el worker EC2

En la misma región/VPC que el backend (y RDS) para que pueda conectar a la base:

```bash
./infrastructure/29e0-launch-pipeline-worker-ec2.sh
```

Al terminar imprime la **IP pública** del worker. Anótala.

### 2. Configurar el worker en el repo

```bash
cp config/pipeline_worker.txt.example config/pipeline_worker.txt
```

Edita `config/pipeline_worker.txt` y pon la IP del paso 1:

```
PIPELINE_WORKER_IP=3.23.45.67
PIPELINE_WORKER_USER=ubuntu
```

### 3. Instalar pipeline y cron en el worker

Sincroniza código, crea venv, copia `.env` desde el backend y añade cron (2:00 AM):

```bash
./infrastructure/29e-setup-pipeline-worker.sh
```

Requisito: el backend debe tener en su `.env` las variables de base de datos (y, si ya migraste, `DATABASE_URL`/`DATABASE_URL_SYNC` apuntando a **RDS**). El script copia esas variables al worker. Si el backend sigue con PostgreSQL local, el worker intentará usar la misma URL (127.0.0.1) y no podrá conectar; en ese caso, después de migrar el backend a RDS, vuelve a ejecutar este paso o edita manualmente el `.env` del worker con el endpoint de RDS (o ejecuta de nuevo `29e-setup-pipeline-worker.sh` para volver a copiar el .env del backend).

### 4. Quitar el pipeline del backend

Para que el backend **no** vuelva a ejecutar el pipeline (y no se sature):

```bash
./infrastructure/29d-remove-pipeline-cron-from-backend.sh
```

Así solo el worker corre la ingesta (por cron de noche o cuando la ejecutes a mano en el worker).

### 5. Primera ejecución manual (opcional)

Para no esperar al cron, ejecuta el pipeline **una vez** en el worker:

```bash
./infrastructure/29h-run-pipeline-on-worker.sh
```

Ese script hace SSH al worker y corre `python -m pipeline.nightly_pipeline --full`. El backend no se usa.

## Verificar

- **Backend:** `curl -s https://api.ominis.org/v1/health` → 200. El backend no debe colgarse.
- **Ingesta:** Tras la primera corrida completa del pipeline en el worker, `curl -s https://api.ominis.org/v1/health-datastore/status` debería mostrar `health_chunks` y `evidence_pack_test_count` > 0.

## Resumen

| Dónde        | Qué corre                         | Efecto en el backend |
|-------------|------------------------------------|------------------------|
| Backend EC2 | Solo API (uvicorn)                | Ninguno                |
| Worker EC2  | Pipeline (cron 2:00 o a mano)     | Ninguno                |

La ingesta queda “echada a andar” en el worker y el backend no se ve afectado.
