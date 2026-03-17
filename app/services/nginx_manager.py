"""
Nginx config manager — automatically writes/removes per-app server blocks.

On every successful deployment:
  → writes /etc/nginx/gitdeploy.d/app-{id}.conf
On every app deletion:
  → removes /etc/nginx/gitdeploy.d/app-{id}.conf

If NGINX_AUTO_RELOAD=true, runs `nginx -s reload` after each change.

All operations fail silently (log warning) so a missing Nginx installation
never breaks a deployment.
"""
import asyncio
import logging
import subprocess
from pathlib import Path

from app.config import Config

logger = logging.getLogger(__name__)

_CONF_TEMPLATE = """\
# gitDeploy — app-{app_id}
# subdomain: {subdomain}.{domain}
# auto-generated — do not edit manually
server {{
    listen 80;
    server_name {subdomain}.{domain};

    location / {{
        proxy_pass         http://127.0.0.1:{internal_port};
        proxy_http_version 1.1;
        proxy_set_header   Upgrade $http_upgrade;
        proxy_set_header   Connection "upgrade";
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;
    }}
}}
"""


def _write_conf(app_id: int, subdomain: str, internal_port: int) -> None:
    conf_dir = Path(Config.NGINX_CONF_DIR)
    conf_dir.mkdir(parents=True, exist_ok=True)

    content = _CONF_TEMPLATE.format(
        app_id=app_id,
        subdomain=subdomain,
        domain=Config.APP_DOMAIN,
        internal_port=internal_port,
    )

    conf_file = conf_dir / f"app-{app_id}.conf"
    conf_file.write_text(content)
    logger.info("Nginx config written: %s", conf_file)

    if Config.NGINX_AUTO_RELOAD:
        _reload_nginx()


def _remove_conf(app_id: int) -> None:
    conf_file = Path(Config.NGINX_CONF_DIR) / f"app-{app_id}.conf"
    if conf_file.exists():
        conf_file.unlink()
        logger.info("Nginx config removed: %s", conf_file)
    else:
        logger.debug("Nginx config not found (already removed?): %s", conf_file)

    if Config.NGINX_AUTO_RELOAD:
        _reload_nginx()


def _reload_nginx() -> None:
    try:
        result = subprocess.run(
            ["nginx", "-s", "reload"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            logger.info("Nginx reloaded successfully.")
        else:
            logger.warning("Nginx reload returned non-zero: %s", result.stderr.strip())
    except FileNotFoundError:
        logger.warning("nginx binary not found — skipping reload.")
    except Exception as e:
        logger.warning("Nginx reload failed: %s", e)


# ── Async wrappers ────────────────────────────────────────────────────────────

async def write_app_conf(app_id: int, subdomain: str, internal_port: int) -> None:
    """Write Nginx config for a deployed app. Never raises."""
    if not Config.NGINX_ENABLED:
        return
    try:
        await asyncio.to_thread(_write_conf, app_id, subdomain, internal_port)
    except Exception as e:
        logger.warning("Failed to write Nginx config for app %s: %s", app_id, e)


async def remove_app_conf(app_id: int) -> None:
    """Remove Nginx config for a deleted app. Never raises."""
    if not Config.NGINX_ENABLED:
        return
    try:
        await asyncio.to_thread(_remove_conf, app_id)
    except Exception as e:
        logger.warning("Failed to remove Nginx config for app %s: %s", app_id, e)
