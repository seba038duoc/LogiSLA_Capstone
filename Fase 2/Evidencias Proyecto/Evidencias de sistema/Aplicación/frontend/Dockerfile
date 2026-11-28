# Imagen del frontend de LogiSLA (Next.js).
#
# La dirección del backend queda fija al compilar (las variables
# NEXT_PUBLIC_* de Next.js se incorporan al código del navegador), por eso
# se pasa como argumento de compilación:
#   docker build --build-arg NEXT_PUBLIC_API_URL=https://... -t logisla-frontend .

# --- Etapa 1: instalar dependencias y compilar ---
FROM node:22-slim AS compilacion
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1

COPY package.json package-lock.json* ./
RUN npm install --no-audit --no-fund

COPY . .
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm run build

# --- Etapa 2: imagen final, solo con lo necesario para ejecutar ---
FROM node:22-slim
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000

COPY --from=compilacion /app/package.json ./
COPY --from=compilacion /app/node_modules ./node_modules
COPY --from=compilacion /app/.next ./.next
COPY --from=compilacion /app/public ./public
COPY --from=compilacion /app/next.config.ts ./

# Usuario sin privilegios (la imagen de Node ya trae el usuario "node").
USER node
EXPOSE 3000

# next start escucha en el puerto de la variable PORT (Cloud Run usa 8080).
CMD ["sh", "-c", "npx next start -H 0.0.0.0 -p ${PORT}"]
