# Orbital web-static runtime — nginx serving the service volume.
# Built on the unprivileged base so the container needs no capabilities:
# it runs as uid 101 and listens on 8080 instead of the privileged port 80.
FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 8080
