# Nginx in Git Deploy: Role and How to Use It

This project currently deploys containers and assigns each app an `internal_port` on the host (for example `10000`, `10001`, etc.).

At the moment, Nginx integration is a **planned improvement**, not fully wired into the deploy/delete flow yet.

## 1) What role Nginx plays here

Nginx acts as a **reverse proxy and traffic router** in front of your deployed app containers.

Without Nginx:
- Every app is reachable only by its host port (for example `http://server-ip:10023`)
- You must expose and manage many ports
- HTTPS and host-based routing are harder to manage centrally

With Nginx:
- You can route `app-1.example.com` -> `127.0.0.1:10001`
- You can route `app-2.example.com` -> `127.0.0.1:10002`
- You expose only ports 80/443 publicly
- TLS/SSL can be terminated in one place (Nginx)

## 2) Why it matches this codebase

- App records already store a generated `subdomain` (`app-{id}`)
- Deployment allocates a host `internal_port`
- Deployed containers bind `internal_port:container_port`

That means all ingredients for Nginx routing already exist: `subdomain` + `internal_port`.

## 3) Minimal Nginx config pattern

Example for one deployed app:

```nginx
server {
    listen 80;
    server_name app-12.example.com;

    location / {
        proxy_pass http://127.0.0.1:10012;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## 4) Practical setup steps

1. Install Nginx on the host machine.
2. Create one site config per deployed app (using app subdomain + internal port).
3. Enable the site (symlink from `sites-available` to `sites-enabled`).
4. Validate config: `nginx -t`.
5. Reload Nginx: `sudo systemctl reload nginx`.
6. Point DNS wildcard/subdomains (`*.example.com`) to your server.

## 5) What should be automated in this repo

A common implementation approach:
- Add `app/services/nginx.py`
  - `write_nginx_config(app)`
  - `enable_nginx_config(app_id)`
  - `remove_nginx_config(app_id)`
  - `reload_nginx()`
- In deploy flow:
  - after successful `docker_run`, write + enable config and reload Nginx
- In delete flow:
  - remove config and reload Nginx

## 6) In short

Nginx is the public entrypoint that maps each app subdomain to the container's internal host port. In this project, Docker deployment is implemented; Nginx routing is the next layer to make deployments production-friendly.
