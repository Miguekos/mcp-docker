"""
MCP Docker Swarm Admin Server
=============================
Servidor MCP (FastMCP) que expone herramientas para administrar un clúster
Docker Swarm de forma segura mediante la CLI de Docker.

Se ejecuta vía stdio y es envuelto por supergateway para exponerlo por HTTP.
"""

import os
import subprocess
import tempfile
from fastmcp import FastMCP

mcp = FastMCP("Docker-Swarm-Admin-Safe")

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

CMD_TIMEOUT = int(os.environ.get("MCP_CMD_TIMEOUT", "60"))  # segundos
MAX_OUTPUT = int(os.environ.get("MCP_MAX_OUTPUT", "50000"))  # caracteres

# Servicios críticos que no pueden escalar a 0
PROTECTED_SERVICES = [
    "postgres", "mysql", "mongo", "redis",
    "caddy", "traefik", "mcp",
]

# Directivas prohibidas en YAML de deploy_stack
FORBIDDEN_DIRECTIVES = [
    "privileged: true",
    "/etc:",
    "/root:",
    "/var/run/docker.sock",
    ":/host",
]


def run_cmd(cmd: list[str], timeout: int | None = None) -> str:
    """Ejecuta un comando de forma segura con timeout y truncado de salida."""
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout or CMD_TIMEOUT,
        )
        output = r.stdout if r.returncode == 0 else f"Error: {r.stderr}"
        if len(output) > MAX_OUTPUT:
            output = output[:MAX_OUTPUT] + f"\n... [salida truncada: {len(output)} chars totales]"
        return output
    except subprocess.TimeoutExpired:
        return f"Error: el comando excedió el timeout de {timeout or CMD_TIMEOUT}s"
    except FileNotFoundError as e:
        return f"Error: comando no encontrado: {e}"


# ---------------------------------------------------------------------------
# Herramientas de lectura
# ---------------------------------------------------------------------------

@mcp.tool()
def list_all_containers(only_running: bool = False) -> str:
    """Lista TODOS los contenedores del servidor (Swarm y Compose) sin filtros."""
    cmd = ["docker", "ps", "--format",
           "table {{.ID}}\t{{.Names}}\t{{.Status}}\t{{.Image}}\t{{.Ports}}"]
    if not only_running:
        cmd.insert(2, "-a")
    return run_cmd(cmd)


@mcp.tool()
def get_container_stats() -> str:
    """Muestra el uso de CPU, RAM, Red e I/O en tiempo real (docker stats --no-stream)."""
    return run_cmd(
        ["docker", "stats", "--no-stream", "--format",
         "table {{.ID}}\t{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.NetIO}}"],
        timeout=120,
    )


@mcp.tool()
def list_swarm_stacks_and_services() -> str:
    """Lista todos los stacks y servicios activos en Docker Swarm."""
    stacks = run_cmd(["docker", "stack", "ls"])
    services = run_cmd(["docker", "service", "ls"])
    return f"=== STACKS ===\n{stacks}\n\n=== SERVICES ===\n{services}"


@mcp.tool()
def list_service_tasks(service_name: str) -> str:
    """Muestra el historial de tareas/contenedores de un servicio de Swarm (docker service ps)."""
    return run_cmd(["docker", "service", "ps", "--no-trunc", service_name])


@mcp.tool()
def list_nodes() -> str:
    """Lista los nodos del clúster Swarm con su rol, estado y disponibilidad."""
    return run_cmd(
        ["docker", "node", "ls", "--format",
         "table {{.ID}}\t{{.Hostname}}\t{{.Role}}\t{{.Availability}}\t{{.Status}}"]
    )


@mcp.tool()
def get_logs(target: str, tail: int = 100, is_swarm_service: bool = False,
             timestamps: bool = False) -> str:
    """Obtiene las últimas líneas de logs de un contenedor o de un servicio de Swarm."""
    kind = "service" if is_swarm_service else "container"
    cmd = ["docker", kind, "logs"]
    if timestamps:
        cmd.append("--timestamps")
    cmd.extend(["--tail", str(min(tail, 500)), target])
    return run_cmd(cmd)


@mcp.tool()
def inspect_resource(target: str) -> str:
    """Inspecciona la configuración detallada (JSON) de un contenedor, servicio, red o volumen."""
    return run_cmd(["docker", "inspect", target])


@mcp.tool()
def list_networks_and_volumes() -> str:
    """Lista todas las redes y volúmenes de Docker."""
    nets = run_cmd(["docker", "network", "ls"])
    vols = run_cmd(["docker", "volume", "ls"])
    return f"=== NETWORKS ===\n{nets}\n\n=== VOLUMES ===\n{vols}"


@mcp.tool()
def system_disk_usage() -> str:
    """Muestra el uso de disco de imágenes, contenedores y volúmenes (docker system df)."""
    return run_cmd(["docker", "system", "df", "-v"])


# ---------------------------------------------------------------------------
# Herramientas de escritura (seguras)
# ---------------------------------------------------------------------------

@mcp.tool()
def remove_stopped_container(container_id_or_name: str) -> str:
    """Elimina UNICAMENTE un contenedor que ya esté detenido (Exited/Dead). Falla si está Running."""
    return run_cmd(["docker", "rm", container_id_or_name])


@mcp.tool()
def prune_all_stopped_containers() -> str:
    """Limpia de forma segura todos los contenedores detenidos (Exited) sin tocar nada activo ni volúmenes."""
    return run_cmd(["docker", "container", "prune", "-f"])


@mcp.tool()
def restart_or_update_service(service_name: str, replicas: int = -1) -> str:
    """Fuerza el reinicio seguro de un servicio Swarm o ajusta sus replicas (bloquea escalar a 0 bases de datos)."""
    if replicas == 0 and any(p in service_name.lower() for p in PROTECTED_SERVICES):
        return "BLOQUEADO POR SEGURIDAD: No se permite escalar a 0 servicios críticos o bases de datos."
    cmd = ["docker", "service", "update", "--force"]
    if replicas >= 0:
        cmd.extend(["--replicas", str(replicas)])
    cmd.append(service_name)
    return run_cmd(cmd)


@mcp.tool()
def deploy_stack(stack_name: str, compose_yaml: str) -> str:
    """Despliega o actualiza un stack en Docker Swarm validando reglas de seguridad."""
    for rule in FORBIDDEN_DIRECTIVES:
        if rule in compose_yaml:
            return f"BLOQUEADO POR SEGURIDAD: El YAML contiene una directiva restringida ({rule})."
    with tempfile.NamedTemporaryFile("w", suffix=".yml", delete=False) as f:
        f.write(compose_yaml)
        tmp_path = f.name
    try:
        return run_cmd(
            ["docker", "stack", "deploy", "--with-registry-auth", "-c", tmp_path, stack_name],
            timeout=300,
        )
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


if __name__ == "__main__":
    mcp.run(transport="stdio")
