FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
ARG REACT_APP_API_URL
ENV REACT_APP_API_URL=${REACT_APP_API_URL}
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/build /usr/share/nginx/html
COPY nginx.frontend.conf /etc/nginx/conf.d/default.conf
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD wget -q --spider http://127.0.0.1:3000/ || exit 1
# 127.0.0.1, not localhost: musl/Alpine resolves "localhost" to ::1 first,
# and nginx here only binds the IPv4 wildcard (0.0.0.0:3000), so the
# healthcheck would flap "unhealthy" against a perfectly healthy server.
