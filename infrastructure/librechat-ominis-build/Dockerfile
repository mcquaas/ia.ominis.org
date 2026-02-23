# Ominis-themed LibreChat: official image + CSS overrides and logo
# Built assets live in /app/client/dist (Vite output); we inject our CSS and logo.
FROM ghcr.io/danny-avila/librechat:latest

# Copy overrides into the served dist (backend serves from client/dist)
COPY overrides/ominis-overrides.css /app/client/dist/ominis-overrides.css
COPY overrides/ominis-footer.js /app/client/dist/ominis-footer.js
COPY overrides/logo.svg /app/client/dist/logo.svg
COPY overrides/background-light.png /app/client/dist/background-light.png
RUN mkdir -p /app/client/dist/images && cp /app/client/dist/logo.svg /app/client/dist/images/logo.svg

# Replace meta description with Ominis; inject favicon, overrides CSS and footer script before </body>
RUN set -e; \
  F="/app/client/dist/index.html"; \
  if [ -f "$F" ]; then \
    sed -i 's|LibreChat - An open source chat application with support for multiple AI models|Asistente de IA para investigadores en salud. Accede a fuentes de datos, estudios y documentación sobre el sistema de salud en México.|g' "$F"; \
    if grep -q '</head>' "$F"; then \
      sed -i 's|</head>|<link rel="icon" href="/logo.svg" type="image/svg+xml"></head>|' "$F"; \
    fi; \
    if grep -q '</body>' "$F"; then \
      sed -i 's|</body>|<link rel="stylesheet" href="/ominis-overrides.css"><script src="/ominis-footer.js"></script></body>|' "$F"; \
    else \
      sed -i 's|</head>|<link rel="stylesheet" href="/ominis-overrides.css"><script src="/ominis-footer.js"></script></head>|' "$F"; \
    fi; \
  fi

# Keep same entrypoint (npm run backend)
# No USER change: keep image default
