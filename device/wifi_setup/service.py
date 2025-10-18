
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import secrets
import string
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


def default_status_path() -> Path:
    return Path("/mnt/data/config/wifi_setup_status.json")


def _ensure_parent(path: Path) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.warning("Failed to create parent directory for %s: %s", path, exc)


class WifiSetupError(Exception):
    """Raised when Wi-Fi configuration fails."""


def random_password(length: int = 12) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _parse_nmcli_table(output: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = line.split(":")
        if not parts:
            continue
        ssid = parts[0].strip()
        signal = parts[1].strip() if len(parts) > 1 else ""
        security = parts[2].strip() if len(parts) > 2 else ""
        rows.append({"ssid": ssid, "signal": signal, "security": security})
    return rows


@dataclass
class WifiSetupStatus:
    state: str = "idle"
    message: str | None = None
    connected_ssid: str | None = None
    last_error: str | None = None
    networks: List[Dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state,
            "message": self.message,
            "connected_ssid": self.connected_ssid,
            "last_error": self.last_error,
            "networks": self.networks,
        }


class WifiSetupManager:
    def __init__(
        self,
        interface: str,
        hotspot_ssid: str,
        hotspot_password: str,
        status_path: Path,
        dry_run: bool = False,
    ) -> None:
        self.interface = interface
        self.hotspot_ssid = hotspot_ssid
        self.hotspot_password = hotspot_password
        self.status_path = status_path
        self.dry_run = dry_run
        self._status = WifiSetupStatus()
        self._status_lock = threading.Lock()
        self._connected_event = threading.Event()
        _ensure_parent(self.status_path)
        self._write_status()

    # ------------------------------------------------------------------ #
    # nmcli helpers
    # ------------------------------------------------------------------ #
    def _run_nmcli(
        self,
        args: List[str],
        *,
        capture_output: bool = False,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        cmd = ["nmcli", *args]
        logger.debug("Executing: %s", " ".join(cmd))
        if self.dry_run:
            logger.info("[dry-run] nmcli %s", " ".join(args))
            return subprocess.CompletedProcess(cmd, 0, "", "")
        try:
            result = subprocess.run(
                cmd,
                check=check,
                text=True,
                capture_output=capture_output,
            )
            return result
        except FileNotFoundError as exc:
            raise WifiSetupError("nmcli is not installed on this system") from exc
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.strip() if exc.stderr else str(exc)
            raise WifiSetupError(stderr) from exc

    # ------------------------------------------------------------------ #
    # status helpers
    # ------------------------------------------------------------------ #
    def _update_status(self, *, state: str | None = None, **fields: Any) -> None:
        with self._status_lock:
            if state is not None:
                self._status.state = state
            for key, value in fields.items():
                if hasattr(self._status, key):
                    setattr(self._status, key, value)
            self._write_status()

    def _write_status(self) -> None:
        payload = self._status.to_dict()
        if self.dry_run:
            logger.info("[dry-run] status update: %s", payload)
            return
        try:
            with self.status_path.open("w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2)
        except OSError as exc:
            logger.warning("Failed to write status file %s: %s", self.status_path, exc)

    # ------------------------------------------------------------------ #
    # Wi-Fi checks
    # ------------------------------------------------------------------ #
    def is_wifi_connected(self) -> bool:
        try:
            result = self._run_nmcli(
                ["-t", "-f", "DEVICE,TYPE,STATE", "connection", "show", "--active"],
                capture_output=True,
            )
        except WifiSetupError as exc:
            logger.warning("Unable to determine Wi-Fi status: %s", exc)
            return False
        for line in result.stdout.splitlines():
            parts = line.split(":")
            if len(parts) >= 3:
                device, conn_type, state = parts[:3]
                if conn_type == "wifi" and state == "activated" and device == self.interface:
                    logger.debug("Interface %s already connected", self.interface)
                    return True
        return False

    def ensure_hotspot(self) -> None:
        self._update_status(
            state="hotspot",
            message=f"Hotspot SSID {self.hotspot_ssid}",
            connected_ssid=None,
            last_error=None,
        )
        try:
            self._run_nmcli(
                [
                    "device",
                    "wifi",
                    "hotspot",
                    "ifname",
                    self.interface,
                    "ssid",
                    self.hotspot_ssid,
                    "password",
                    self.hotspot_password,
                ],
                capture_output=True,
            )
            logger.info(
                "Hotspot %s started on %s", self.hotspot_ssid, self.interface
            )
        except WifiSetupError as exc:
            self._update_status(
                state="error",
                message="Failed to start hotspot",
                last_error=str(exc),
            )
            raise

    def stop_hotspot(self) -> None:
        try:
            self._run_nmcli(
                ["connection", "down", "Hotspot"],
                capture_output=True,
                check=False,
            )
        except WifiSetupError:
            pass

    def list_networks(self, rescan: bool = False) -> List[Dict[str, str]]:
        if rescan:
            try:
                self._run_nmcli(
                    ["device", "wifi", "rescan", "ifname", self.interface],
                    capture_output=False,
                    check=False,
                )
                time.sleep(1.5)
            except WifiSetupError as exc:
                self._update_status(last_error=str(exc))
        try:
            result = self._run_nmcli(
                ["-t", "-f", "SSID,SIGNAL,SECURITY", "device", "wifi", "list"],
                capture_output=True,
                check=False,
            )
        except WifiSetupError:
            return []
        networks = _parse_nmcli_table(result.stdout)
        self._update_status(networks=networks)
        return networks

    def connect_network(self, ssid: str, password: str | None) -> None:
        self._update_status(
            state="connecting",
            message=f"Connecting to {ssid}",
            connected_ssid=None,
            last_error=None,
        )
        args = [
            "device",
            "wifi",
            "connect",
            ssid,
            "ifname",
            self.interface,
        ]
        if password:
            args.extend(["password", password])
        try:
            result = self._run_nmcli(args, capture_output=True, check=False)
        except WifiSetupError as exc:
            self._update_status(
                state="error",
                message="Connection attempt failed",
                last_error=str(exc),
            )
            raise
        if result.returncode != 0:
            error_message = result.stderr.strip() if result.stderr else "Unknown error"
            self._update_status(
                state="error",
                message="Connection attempt failed",
                last_error=error_message,
            )
            raise WifiSetupError(error_message)
        self._update_status(
            state="connected",
            message="Wi-Fi connection established",
            connected_ssid=ssid,
            last_error=None,
        )
        self.stop_hotspot()
        self._connected_event.set()

    def wait_for_connection(self, timeout: float | None = None) -> bool:
        return self._connected_event.wait(timeout=timeout)

    def get_status(self) -> Dict[str, Any]:
        with self._status_lock:
            return self._status.to_dict()

    def render_index(self) -> str:
        return """
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <title>OK Monitor Wi-Fi Setup</title>
    <style>
      body {
        font-family: Arial, sans-serif;
        background: #0f172a;
        color: #e2e8f0;
        padding: 2rem;
      }
      h1 {
        color: #38bdf8;
      }
      label {
        display: block;
        margin: 0.5rem 0 0.2rem;
      }
      input, select, button {
        width: 100%;
        padding: 0.5rem;
        margin-bottom: 0.75rem;
        border-radius: 4px;
        border: 1px solid #1e293b;
        background: #1e293b;
        color: #e2e8f0;
      }
      button {
        background: #2563eb;
        border: none;
        font-weight: 600;
        cursor: pointer;
      }
      button:hover {
        background: #1d4ed8;
      }
      .status {
        background: #1e293b;
        padding: 1rem;
        border-radius: 8px;
        margin-top: 1rem;
      }
      .networks {
        max-height: 240px;
        overflow-y: auto;
        background: #111827;
        padding: 0.5rem;
        border-radius: 6px;
      }
      .networks button {
        width: auto;
        margin: 0.25rem 0.25rem 0.25rem 0;
      }
    </style>
  </head>
  <body>
    <h1>OK Monitor Wi-Fi Setup</h1>
    <p>Connect to your local Wi-Fi network. The device will automatically reboot once connected.</p>
    <section>
      <label for="ssid">Available networks</label>
      <div class="networks" id="networkList"></div>
      <label for="ssidInput">Selected SSID</label>
      <input id="ssidInput" placeholder="SSID" />
      <label for="passwordInput">Password</label>
      <input id="passwordInput" type="password" placeholder="Password (leave blank for open network)" />
      <button id="connectBtn">Connect</button>
    </section>
    <div class="status" id="statusBox">Waiting for hotspot...</div>
    <script>
      async function fetchStatus() {
        try {
          const res = await fetch('/api/status');
          const data = await res.json();
          const statusBox = document.getElementById('statusBox');
          const stateLabels = {
            idle: 'Idle',
            hotspot: 'Hotspot active',
            connecting: 'Connecting',
            connected: 'Connected',
            error: 'Error'
          };
          const statusHtml = `
            <strong>Status:</strong> ${stateLabels[data.state] || data.state}<br/>
            <strong>Message:</strong> ${(data.message || '&mdash;')}<br/>
            <strong>Connected SSID:</strong> ${(data.connected_ssid || '&mdash;')}<br/>
            <strong>Last error:</strong> ${(data.last_error || '&mdash;')}
          `;
          statusBox.innerHTML = statusHtml;
        } catch (error) {
          console.warn('Failed to fetch status', error);
        }
      }

      async function fetchNetworks() {
        try {
          const res = await fetch('/api/networks?rescan=1');
          const data = await res.json();
          const container = document.getElementById('networkList');
          container.innerHTML = '';
          data.networks.forEach((net) => {
            const btn = document.createElement('button');
            btn.textContent = ${net.ssid || '(hidden)'} - signal ;
            btn.addEventListener('click', () => {
              document.getElementById('ssidInput').value = net.ssid;
            });
            container.appendChild(btn);
          });
        } catch (error) {
          console.warn('Failed to fetch networks', error);
        }
      }

      async function connect() {
        const ssid = document.getElementById('ssidInput').value.trim();
        const password = document.getElementById('passwordInput').value;
        if (!ssid) {
          alert('Please select or enter an SSID.');
          return;
        }
        try {
          const res = await fetch('/api/connect', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ssid, password }),
          });
          const data = await res.json();
          if (!res.ok) {
            throw new Error(data.detail || 'Connection failed');
          }
          alert(data.message || 'Connection attempt started.');
          document.getElementById('passwordInput').value = '';
        } catch (error) {
          alert(error.message);
        }
      }

      document.getElementById('connectBtn').addEventListener('click', connect);
      fetchNetworks();
      fetchStatus();
      setInterval(fetchStatus, 3000);
    </script>
  </body>
</html>
        """


class NetworkRequest(BaseModel):
    ssid: str = Field(..., description="Network SSID")
    password: str | None = Field(
        default=None, description="Network password (optional for open networks)"
    )


def create_app(manager: WifiSetupManager) -> FastAPI:
    app = FastAPI(title="OK Monitor Wi-Fi Setup", docs_url=None, redoc_url=None)

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return manager.render_index()

    @app.get("/api/status")
    def api_status() -> Dict[str, Any]:
        return manager.get_status()

    @app.get("/api/networks")
    def api_networks(rescan: int | None = None) -> Dict[str, Any]:
        networks = manager.list_networks(rescan=bool(rescan))
        return {"networks": networks}

    @app.post("/api/connect")
    def api_connect(request: NetworkRequest) -> Dict[str, Any]:
        try:
            manager.connect_network(request.ssid, request.password)
        except WifiSetupError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"message": f"Connection to {request.ssid} initiated."}

    return app


def run_portal(manager: WifiSetupManager, host: str, port: int, timeout: float | None = None) -> None:
    app = create_app(manager)
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)

    def _runner() -> None:
        asyncio.run(server.serve())

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    logger.info("Captive portal running on http://%s:%d", host, port)
    try:
        connected = manager.wait_for_connection(timeout=timeout)
        if connected:
            logger.info("Wi-Fi credentials applied. Shutting down portal.")
        else:
            logger.info("Portal thread stopping without connection event.")
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OK Monitor Wi-Fi setup helper")
    parser.add_argument(
        "--interface",
        default=os.environ.get("OKM_WIFI_INTERFACE", "wlan0"),
        help="Wi-Fi interface to configure (default: %(default)s)",
    )
    parser.add_argument(
        "--hotspot-ssid",
        default=os.environ.get("OKM_SETUP_SSID", "OKMonitor-Setup"),
        help="SSID to broadcast when in setup mode (default: %(default)s)",
    )
    parser.add_argument(
        "--hotspot-password",
        default=os.environ.get("OKM_SETUP_PASSWORD", "OKMonitor"),
        help="Hotspot password (default: OKMonitor, override via OKM_SETUP_PASSWORD)",
    )
    parser.add_argument(
        "--status-path",
        type=Path,
        default=default_status_path(),
        help="Path to JSON file used to publish setup status",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host interface for the captive portal (default: %(default)s)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=80,
        help="Port for the captive portal (default: %(default)s)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print nmcli commands instead of running them",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        help="Optional timeout (seconds) to wait for connection before exiting",
    )
    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    args = parse_args(argv)

    password = args.hotspot_password or random_password()
    manager = WifiSetupManager(
        interface=args.interface,
        hotspot_ssid=args.hotspot_ssid,
        hotspot_password=password,
        status_path=args.status_path,
        dry_run=args.dry_run,
    )

    if manager.is_wifi_connected():
        logger.info("Wi-Fi already connected on %s; exiting setup helper.", args.interface)
        return

    try:
        manager.ensure_hotspot()
    except WifiSetupError as exc:
        logger.error("Unable to start hotspot: %s", exc)
        return

    try:
        run_portal(manager, host=args.host, port=args.port, timeout=args.timeout)
        if not manager.dry_run and not manager.is_wifi_connected():
            logger.warning(
                "Wi-Fi connection was not established before exiting; hotspot remains available."
            )
    finally:
        if manager.is_wifi_connected():
            manager.stop_hotspot()


if __name__ == "__main__":
    main()
