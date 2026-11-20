# mcp-docker

Servidor MCP (Model Context Protocol) para administrar un clúster **Docker Swarm** de forma segura. Exponen herramientas vía HTTP (streamable HTTP) usando [FastMCP](https://github.com/jlowin/fastmcp) + [supergateway](https://github.com/supercorp-ai/supergateway), y se despliega como stack en Swarm.

## Herramientas disponibles

| Herramienta | Tipo | Descripción |
|---|---|---|
| `list_all_containers` | lectura | Lista todos los contenedores (Swarm y Compose) |
| `get_container_stats` | lectura | CPU, RAM, Red e I/O en tiempo real |
| `list_swarm_stacks_and_services` | lectura | Stacks y servicios activos |
| `list_service_tasks` | lectura | Historial de tareas de un servicio |
| `list_nodes` | lectura | Nodos del clúster con rol y estado |
| `get_logs` | lectura | Logs de contenedor o servicio (con timestamps opcionales) |
| `inspect_resource` | lectura | Inspección JSON de contenedor/servicio/red/volumen |
| `list_networks_and_volumes` | lectura | Redes y volúmenes |
| `system_disk_usage` | lectura | Uso de disco (docker system df) |
| `remove_stopped_container` | escritura | Elimina solo contenedores detenidos |
| `prune_all_stopped_containers` | escritura | Limpia contenedores Exited |
| `restart_or_update_service` | escritura | Reinicia/escala servicios (protege críticos) |
| `deploy_stack` | escritura | Despliega stacks con validación de seguridad |

## Seguridad

- **API key obligatoria**: supergateway exige `Authorization: Bearer <key>`
- **Socket read-only**: `/var/run/docker.sock` montado `:ro`
- **Servicios protegidos**: no se puede escalar a 0 `postgres`, `mysql`, `mongo`, `redis`, `caddy`, `traefik`, `mcp`
- **YAML restringido**: `deploy_stack` bloquea `privileged: true`, mounts de `/etc`, `/root`, `docker.sock`, `:/host`
- **Timeouts**: 60s por comando (configurable), salida truncada a 50KB

## Build (local)

```bash
# Construir la imagen
docker build -t mcp-docker:latest .
```

## CI/CD — Build y push automático a GHCR

El workflow [`build-and-push.yml`](.github/workflows/build-and-push.yml) construye la imagen y la publica en **GitHub Container Registry** sin necesidad de secretos adicionales (usa el `GITHUB_TOKEN` integrado).

**Tags generados:**

| Disparador | Tags publicados |
|---|---|
| `push` a `main` | `ghcr.io/miguekos/mcp-docker:main` y `:latest` |
| push de tag `v*.*.*` | `ghcr.io/miguekos/mcp-docker:v1.2.3` |
| cualquier `push` | `ghcr.io/miguekos/mcp-docker:sha-<commit>` |
| `workflow_dispatch` | mismos tags según rama/tag |

**Requisitos en GitHub:**

1. El repositorio debe estar en `github.com/miguekos` (owner usado por el workflow).
2. En *Settings → Packages* verifica que el paquete `mcp-docker` exista tras el primer run.
3. Si el paquete es **private**, el nodo del Swarm debe autenticarse antes del `docker stack deploy`:
   ```bash
   echo "ghp_xxxxxxxxxxxx" | docker login ghcr.io -u miguekos --password-stdin
   ```
   (el token necesita scope `read:packages`).

Uso manual desde la UI: **Actions → Build & Push MCP Docker image → Run workflow**.

## Despliegue en Swarm

1. Configura las variables:
   ```bash
   cp .env.example .env
   # Edita .env con tu API key
   ```

2. Ajusta el dominio en [`stack.yml`](stack.yml) si aplica. La imagen ya apunta a `ghcr.io/miguekos/mcp-docker:latest` (publicada por CI).

3. Despliega:
   ```bash
   docker stack deploy -c stack.yml mcp
   ```

4. Verifica:
   ```bash
   docker service ls | grep mcp
   docker service logs mcp_mcp-docker
   ```

> **Requisito**: la red `traefik` debe existir como red externa en Swarm (`docker network create --driver overlay --attachable traefik` si no existe).

## Conexión desde un cliente MCP

Configura tu cliente (VS Code, Claude Desktop, etc.) con:

```json
{
  "mcpServers": {
    "docker-swarm": {
      "url": "https://mcp.tu-dominio.com/mcp",
      "headers": {
        "Authorization": "Bearer TuClaveSuperSecreta2026"
      }
    }
  }
}
```

## Variables de entorno

| Variable | Default | Descripción |
|---|---|---|
| `SUPERGATEWAY_API_KEY` | — | **Obligatoria**. Clave de acceso HTTP |
| `MCP_CMD_TIMEOUT` | `60` | Timeout de comandos docker (segundos) |
| `MCP_MAX_OUTPUT` | `50000` | Máximo de caracteres de salida |
