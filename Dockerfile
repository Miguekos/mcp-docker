# syntax=docker/dockerfile:1

# ===========================================================================
# Stage 1: builder-python — instala FastMCP en un prefijo (venv)
# ===========================================================================
FROM python:3.12-alpine AS builder-python
RUN pip install --no-cache-dir --prefix=/opt/mcp-venv fastmcp

# ===========================================================================
# Stage 2: builder-node — instala supergateway globalmente
# ===========================================================================
FROM node:20-alpine AS builder-node
RUN npm install -g supergateway --no-audit --no-fund

# ===========================================================================
# Stage 3: runtime — Python 3.12 + Docker CLI + Node (supergateway)
# Base python:3.12-alpine para que el venv de FastMCP funcione sin cambios;
# el binario estático de Docker CLI se copia desde la imagen oficial docker:cli
# ===========================================================================
FROM python:3.12-alpine AS runtime

# Docker CLI (binario estático) + librerías para node
COPY --from=docker:cli /usr/local/bin/docker /usr/local/bin/docker
RUN apk add --no-cache coreutils ca-certificates libstdc++

# Node (requerido por supergateway) y sus módulos
COPY --from=builder-node /usr/local/bin/node /usr/local/bin/node
COPY --from=builder-node /usr/local/lib/node_modules /usr/local/lib/node_modules

# FastMCP preinstalado
COPY --from=builder-python /opt/mcp-venv /opt/mcp-venv

ENV PATH="/opt/mcp-venv/bin:/usr/local/bin:$PATH" \
    PYTHONPATH="/opt/mcp-venv/lib/python3.12/site-packages" \
    PYTHONUNBUFFERED=1 \
    MCP_CMD_TIMEOUT=60 \
    MCP_MAX_OUTPUT=50000

WORKDIR /app
COPY server.py /app/server.py

EXPOSE 8000

# supergateway envuelve el servidor stdio de FastMCP y lo expone por HTTP
# Se ejecuta el entrypoint del paquete directamente (el bin global pierde la
# resolución de módulos al ser copiado fuera de node_modules)
ENTRYPOINT ["node", "/usr/local/lib/node_modules/supergateway/dist/index.js"]
CMD ["--stdio", "python3 /app/server.py", \
     "--outputTransport", "streamableHttp", \
     "--port", "8000", \
     "--streamableHttpPath", "/mcp", \
     "--cors"]
