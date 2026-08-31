import atexit
import json
import os
import platform
import secrets
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional

import psutil
import pystray
import requests
import uvicorn

from fastapi import FastAPI, Header, HTTPException
from PIL import Image, ImageDraw, ImageGrab
from pydantic import BaseModel
from zeroconf import ServiceInfo, Zeroconf


# ============================================================
# EMMA WINDOWS COMPANION AGENT
# ============================================================
#
# Android EMMA
#       ↓
#   EMMA CLOUD
#       ↓
# DEVICE GATEWAY
#       ↓
# WINDOWS COMPANION
#       ↓
#    WINDOWS
#
# Features:
#   - Cloud registration
#   - One-time pairing
#   - Permanent device token
#   - Persistent credentials
#   - Automatic reconnect
#   - Heartbeat
#   - Command polling
#   - Command execution
#   - Command result reporting
#   - mDNS discovery
#   - Local FastAPI API
#   - System tray
#
# ============================================================


# ============================================================
# CONFIGURATION
# ============================================================

APP_NAME = "EMMA Windows Companion"
APP_VERSION = "2.0.0"

# Development backend.
#
# When your backend moves to Render / production:
#
#   set EMMA_CLOUD_URL=https://your-domain.com
#
CLOUD_URL = os.getenv(
    "CLOUD_URL",
    "https://emma-backend-yzur.onrender.com"
).rstrip("/")


# ============================================================
# LOCAL AGENT
# ============================================================

LOCAL_AGENT_HOST = "0.0.0.0"
LOCAL_AGENT_PORT = 8765

EMMA_SERVICE_TYPE = "_emma._tcp.local."


# ============================================================
# TIMING
# ============================================================

HEARTBEAT_INTERVAL = 10
COMMAND_POLL_INTERVAL = 2
RECONNECT_INTERVAL = 5
PAIRING_CHECK_INTERVAL = 3
REQUEST_TIMEOUT = 10


# ============================================================
# GLOBAL STATE
# ============================================================

running_event = threading.Event()
running_event.set()

state_lock = threading.Lock()

agent_status = "Starting"
cloud_status = "Offline"
last_cloud_error = ""

cloud_device_id: Optional[str] = None
cloud_device_token: Optional[str] = None
cloud_pairing_code: Optional[str] = None

zeroconf_instance: Optional[Zeroconf] = None
service_info: Optional[ServiceInfo] = None


# ============================================================
# LOCAL STORAGE
# ============================================================

APP_DATA_DIR = (
    Path(
        os.getenv(
            "APPDATA",
            str(Path.home()),
        )
    )
    / "EMMA"
)

APP_DATA_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

DEVICE_FILE = APP_DATA_DIR / "device.json"


# ============================================================
# LOCAL IDENTITY
# ============================================================

def generate_local_device_id() -> str:
    return secrets.token_hex(16)


def generate_local_device_token() -> str:
    return secrets.token_urlsafe(32)


def get_device_name() -> str:
    return platform.node()


def load_local_config() -> dict:
    if not DEVICE_FILE.exists():
        return {}

    try:
        with DEVICE_FILE.open(
            "r",
            encoding="utf-8",
        ) as file:
            data = json.load(file)

        if isinstance(data, dict):
            return data

    except Exception as error:
        print(
            "EMMA CONFIG READ ERROR:",
            error,
        )

    return {}


def save_local_config(
    data: dict,
) -> bool:

    try:
        temp_file = DEVICE_FILE.with_suffix(
            ".tmp"
        )

        with temp_file.open(
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                data,
                file,
                indent=2,
            )

        temp_file.replace(
            DEVICE_FILE
        )

        return True

    except Exception as error:

        print(
            "EMMA CONFIG SAVE ERROR:",
            error,
        )

        return False


def ensure_local_identity() -> dict:

    config = load_local_config()

    changed = False

    if not config.get("local_device_id"):
        config["local_device_id"] = (
            generate_local_device_id()
        )
        changed = True

    if not config.get("local_device_token"):
        config["local_device_token"] = (
            generate_local_device_token()
        )
        changed = True

    if not config.get("device_name"):
        config["device_name"] = (
            get_device_name()
        )
        changed = True

    config["platform"] = "windows"
    config["agent_version"] = APP_VERSION

    if changed:
        save_local_config(config)

    return config


LOCAL_CONFIG = ensure_local_identity()

LOCAL_DEVICE_ID = LOCAL_CONFIG[
    "local_device_id"
]

LOCAL_DEVICE_TOKEN = LOCAL_CONFIG[
    "local_device_token"
]

DEVICE_NAME = LOCAL_CONFIG[
    "device_name"
]


# ============================================================
# FASTAPI
# ============================================================

app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
)


# ============================================================
# REQUEST MODELS
# ============================================================

class ActionRequest(BaseModel):
    action: str


class PairRequest(BaseModel):
    code: str


# ============================================================
# STATE HELPERS
# ============================================================

def set_status(
    status: str,
) -> None:

    global agent_status

    with state_lock:
        agent_status = status


def set_cloud_status(
    status: str,
    error: str = "",
) -> None:

    global cloud_status
    global last_cloud_error

    with state_lock:
        cloud_status = status
        last_cloud_error = error


# ============================================================
# CLOUD URL
# ============================================================

def cloud_url(
    endpoint: str,
) -> str:

    return f"{CLOUD_URL}{endpoint}"


# ============================================================
# CLOUD HTTP
# ============================================================

def cloud_get(
    endpoint: str,
    headers: Optional[dict] = None,
):

    return requests.get(
        cloud_url(endpoint),
        headers=headers or {},
        timeout=REQUEST_TIMEOUT,
    )


def cloud_post(
    endpoint: str,
    payload: Optional[dict] = None,
    headers: Optional[dict] = None,
):

    return requests.post(
        cloud_url(endpoint),
        json=payload or {},
        headers=headers or {},
        timeout=REQUEST_TIMEOUT,
    )


# ============================================================
# TOKEN HEADERS
# ============================================================

def token_headers() -> dict:

    if not cloud_device_token:
        return {
            "Accept": "application/json",
        }

    return {
        "Accept": "application/json",
        "Authorization": (
            f"Bearer {cloud_device_token}"
        ),
        "X-EMMA-Token": cloud_device_token,
    }


# ============================================================
# LOAD CLOUD CREDENTIALS
# ============================================================

def load_cloud_credentials() -> None:

    global cloud_device_id
    global cloud_device_token
    global cloud_pairing_code

    config = load_local_config()

    cloud_device_id = config.get(
        "cloud_device_id"
    )

    cloud_device_token = config.get(
        "cloud_device_token"
    )

    cloud_pairing_code = config.get(
        "pairing_code"
    )


# ============================================================
# SAVE PENDING PAIRING
# ============================================================

def save_pending_cloud_pairing(
    device_id: str,
    pairing_code: str,
) -> None:

    global cloud_device_id
    global cloud_pairing_code

    cloud_device_id = device_id
    cloud_pairing_code = pairing_code

    config = load_local_config()

    config["cloud_device_id"] = device_id
    config["pairing_code"] = pairing_code
    config["paired"] = False

    # Do not leave an old token attached to a
    # newly-created pending registration.
    config.pop(
        "cloud_device_token",
        None,
    )

    save_local_config(config)


# ============================================================
# REGISTER WINDOWS COMPUTER WITH CLOUD
# ============================================================

def register_cloud_device() -> Optional[dict]:

    try:

        print(
            "Registering",
            DEVICE_NAME,
            "with EMMA Cloud...",
        )

        response = cloud_post(
            "/device/register",
            {
                "device_name": DEVICE_NAME,
                "platform": "windows",
            },
        )

        if response.status_code != 200:

            print(
                "EMMA CLOUD REGISTER ERROR:",
                response.status_code,
            )

            print(
                response.text
            )

            return None

        data = response.json()

        device_id = data.get(
            "device_id"
        )

        pairing_code = data.get(
            "pairing_code"
        )

        if not device_id or not pairing_code:

            print(
                "Invalid registration response."
            )

            return None

        return {
            "device_id": device_id,
            "pairing_code": pairing_code,
            "device_name": DEVICE_NAME,
        }

    except requests.RequestException as error:

        set_cloud_status(
            "Offline",
            str(error),
        )

        return None

    except Exception as error:

        print(
            "EMMA REGISTER ERROR:",
            error,
        )

        return None


# ============================================================
# CLAIM PERMANENT TOKEN
# ============================================================

def claim_cloud_token() -> bool:

    global cloud_device_token
    global cloud_pairing_code

    if not cloud_device_id:
        return False

    if not cloud_pairing_code:
        return False

    try:

        response = cloud_post(
            "/device/claim-token",
            {
                "device_id": cloud_device_id,
                "pairing_code": cloud_pairing_code,
            },
        )

        # Android has not completed pairing yet.
        if response.status_code == 409:
            return False

        if response.status_code == 401:

            print(
                "EMMA TOKEN CLAIM: Invalid pairing code."
            )

            return False

        if response.status_code != 200:

            print(
                "EMMA TOKEN CLAIM ERROR:",
                response.status_code,
                response.text,
            )

            return False

        data = response.json()

        token = data.get(
            "device_token"
        )

        if not token:

            print(
                "EMMA TOKEN CLAIM: No token returned."
            )

            return False

        cloud_device_token = token

        config = load_local_config()

        config[
            "cloud_device_id"
        ] = cloud_device_id

        config[
            "cloud_device_token"
        ] = token

        config[
            "device_name"
        ] = DEVICE_NAME

        config[
            "platform"
        ] = "windows"

        config[
            "agent_version"
        ] = APP_VERSION

        config[
            "paired"
        ] = True

        # One-time pairing code is no longer needed.
        config.pop(
            "pairing_code",
            None,
        )

        save_local_config(
            config
        )

        cloud_pairing_code = None

        print(
            "EMMA: Permanent device token saved."
        )

        return True

    except requests.RequestException as error:

        set_cloud_status(
            "Offline",
            str(error),
        )

        return False

    except Exception as error:

        print(
            "EMMA TOKEN CLAIM ERROR:",
            error,
        )

        return False


# ============================================================
# TOKEN RECONNECT
# ============================================================

def connect_with_token() -> bool:

    if not cloud_device_id:
        return False

    if not cloud_device_token:
        return False

    try:

        response = cloud_post(
            "/device/token-connect",
            {
                "device_id": cloud_device_id,
                "device_token": cloud_device_token,
            },
        )

        if response.status_code == 200:

            set_cloud_status(
                "Connected"
            )

            set_status(
                "Connected"
            )

            return True

        if response.status_code == 401:

            print(
                "EMMA: Saved token was rejected."
            )

            return False

        print(
            "EMMA TOKEN CONNECT ERROR:",
            response.status_code,
            response.text,
        )

        return False

    except requests.RequestException as error:

        set_cloud_status(
            "Offline",
            str(error),
        )

        return False


# ============================================================
# HEARTBEAT
# ============================================================

def send_heartbeat() -> bool:

    if not cloud_device_id:
        return False

    if not cloud_device_token:
        return False

    try:

        response = cloud_post(
            f"/device/{cloud_device_id}/heartbeat",
            {},
            headers=token_headers(),
        )

        if response.status_code == 200:

            set_cloud_status(
                "Connected"
            )

            return True

        return False

    except requests.RequestException as error:

        set_cloud_status(
            "Offline",
            str(error),
        )

        return False


# ============================================================
# GET COMMANDS
# ============================================================

def get_cloud_commands() -> list:

    if not cloud_device_id:
        return []

    if not cloud_device_token:
        return []

    try:

        response = cloud_get(
            f"/device/{cloud_device_id}/commands",
            headers=token_headers(),
        )

        if response.status_code == 401:

            print(
                "EMMA: Command authentication failed."
            )

            return []

        if response.status_code != 200:
            return []

        data = response.json()

        commands = data.get(
            "commands",
            [],
        )

        if isinstance(
            commands,
            list,
        ):
            return commands

        return []

    except requests.RequestException:
        return []

    except Exception as error:

        print(
            "EMMA COMMAND POLL ERROR:",
            error,
        )

        return []


# ============================================================
# SEND COMMAND RESULT
# ============================================================

def send_command_result(
    result: dict,
) -> None:

    if not cloud_device_id:
        return

    if not cloud_device_token:
        return

    try:

        response = cloud_post(
            f"/device/{cloud_device_id}/command-result",
            result,
            headers=token_headers(),
        )

        if response.status_code != 200:

            print(
                "EMMA COMMAND RESULT ERROR:",
                response.status_code,
                response.text,
            )

    except requests.RequestException as error:

        print(
            "EMMA COMMAND RESULT ERROR:",
            error,
        )


# ============================================================
# WINDOWS MEDIA KEY
# ============================================================

def media_key(
    key_code: int,
) -> None:

    import ctypes

    ctypes.windll.user32.keybd_event(
        key_code,
        0,
        0,
        0,
    )

    ctypes.windll.user32.keybd_event(
        key_code,
        0,
        2,
        0,
    )


# ============================================================
# WINDOWS COMMAND EXECUTOR
# ============================================================

def execute_action(
    action_name: str,
) -> dict:

    action_name = (
        action_name
        .lower()
        .strip()
    )

    # ========================================================
    # APPLICATIONS
    # ========================================================

    if action_name == "open vscode":

        try:

            subprocess.Popen(
                ["code"],
                shell=True,
            )

            return {
                "success": True,
                "message": "VS Code opened.",
            }

        except Exception as error:

            return {
                "success": False,
                "message": (
                    f"Could not open VS Code: {error}"
                ),
            }


    if action_name == "open chrome":

        try:

            subprocess.Popen(
                [
                    "cmd",
                    "/c",
                    "start",
                    "",
                    "chrome",
                ],
                shell=True,
            )

            return {
                "success": True,
                "message": "Chrome opened.",
            }

        except Exception as error:

            return {
                "success": False,
                "message": (
                    f"Could not open Chrome: {error}"
                ),
            }


    if action_name == "open notepad":

        try:

            subprocess.Popen(
                ["notepad.exe"]
            )

            return {
                "success": True,
                "message": "Notepad opened.",
            }

        except Exception as error:

            return {
                "success": False,
                "message": (
                    f"Could not open Notepad: {error}"
                ),
            }


    if action_name == "open calculator":

        try:

            subprocess.Popen(
                ["calc.exe"]
            )

            return {
                "success": True,
                "message": "Calculator opened.",
            }

        except Exception as error:

            return {
                "success": False,
                "message": (
                    f"Could not open Calculator: {error}"
                ),
            }


    # ========================================================
    # WINDOWS
    # ========================================================

    if action_name == "open file explorer":

        try:

            subprocess.Popen(
                ["explorer.exe"]
            )

            return {
                "success": True,
                "message": "File Explorer opened.",
            }

        except Exception as error:

            return {
                "success": False,
                "message": (
                    f"Could not open File Explorer: {error}"
                ),
            }


    if action_name == "open task manager":

        try:

            subprocess.Popen(
                ["taskmgr.exe"]
            )

            return {
                "success": True,
                "message": "Task Manager opened.",
            }

        except Exception as error:

            return {
                "success": False,
                "message": (
                    f"Could not open Task Manager: {error}"
                ),
            }


    if action_name == "open settings":

        try:

            subprocess.Popen(
                [
                    "cmd",
                    "/c",
                    "start",
                    "",
                    "ms-settings:",
                ],
                shell=True,
            )

            return {
                "success": True,
                "message": "Windows Settings opened.",
            }

        except Exception as error:

            return {
                "success": False,
                "message": (
                    f"Could not open Windows Settings: {error}"
                ),
            }


    # ========================================================
    # FOLDERS
    # ========================================================

    if action_name == "open desktop":

        try:

            subprocess.Popen(
                [
                    "explorer.exe",
                    os.path.expanduser(
                        "~/Desktop"
                    ),
                ]
            )

            return {
                "success": True,
                "message": "Desktop opened.",
            }

        except Exception as error:

            return {
                "success": False,
                "message": (
                    f"Could not open Desktop: {error}"
                ),
            }


    if action_name == "open downloads":

        try:

            subprocess.Popen(
                [
                    "explorer.exe",
                    os.path.expanduser(
                        "~/Downloads"
                    ),
                ]
            )

            return {
                "success": True,
                "message": "Downloads opened.",
            }

        except Exception as error:

            return {
                "success": False,
                "message": (
                    f"Could not open Downloads: {error}"
                ),
            }


    if action_name == "open documents":

        try:

            subprocess.Popen(
                [
                    "explorer.exe",
                    os.path.expanduser(
                        "~/Documents"
                    ),
                ]
            )

            return {
                "success": True,
                "message": "Documents opened.",
            }

        except Exception as error:

            return {
                "success": False,
                "message": (
                    f"Could not open Documents: {error}"
                ),
            }


    # ========================================================
    # VOLUME
    # ========================================================

    if action_name == "volume up":

        for _ in range(3):
            media_key(0xAF)

        return {
            "success": True,
            "message": "Volume increased.",
        }


    if action_name == "volume down":

        for _ in range(3):
            media_key(0xAE)

        return {
            "success": True,
            "message": "Volume decreased.",
        }


    if action_name == "mute":

        media_key(0xAD)

        return {
            "success": True,
            "message": "Volume muted.",
        }


    # ========================================================
    # MEDIA
    # ========================================================

    if action_name == "play pause":

        media_key(0xB3)

        return {
            "success": True,
            "message": "Play/pause command sent.",
        }


    if action_name == "next track":

        media_key(0xB0)

        return {
            "success": True,
            "message": "Next track command sent.",
        }


    if action_name == "previous track":

        media_key(0xB1)

        return {
            "success": True,
            "message": "Previous track command sent.",
        }


    # ========================================================
    # BATTERY
    # ========================================================

    if action_name == "battery status":

        battery = psutil.sensors_battery()

        if battery is None:

            return {
                "success": True,
                "message": (
                    "Battery information is unavailable."
                ),
            }

        state = (
            "charging"
            if battery.power_plugged
            else "on battery"
        )

        return {
            "success": True,
            "message": (
                f"Laptop battery is "
                f"{battery.percent:.0f}% "
                f"and {state}."
            ),
        }


    # ========================================================
    # SYSTEM
    # ========================================================

    if action_name == "system status":

        cpu = psutil.cpu_percent(
            interval=1
        )

        ram = psutil.virtual_memory()

        return {
            "success": True,
            "message": (
                f"CPU usage is {cpu:.0f}%. "
                f"RAM usage is {ram.percent:.0f}%."
            ),
        }


    # ========================================================
    # SCREENSHOT
    # ========================================================

    if action_name == "take screenshot":

        screenshot_dir = (
            Path.home()
            / "Pictures"
            / "EMMA"
        )

        screenshot_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        screenshot = ImageGrab.grab()

        filename = (
            screenshot_dir
            / f"emma_{int(time.time())}.png"
        )

        screenshot.save(
            filename
        )

        return {
            "success": True,
            "message": (
                f"Screenshot saved to {filename}"
            ),
            "path": str(filename),
        }


    # ========================================================
    # LOCK
    # ========================================================

    if action_name == "lock laptop":

        subprocess.run(
            [
                "rundll32.exe",
                "user32.dll,LockWorkStation",
            ],
            check=False,
        )

        return {
            "success": True,
            "message": "Laptop locked.",
        }


    # ========================================================
    # UNKNOWN
    # ========================================================

    return {
        "success": False,
        "message": (
            "EMMA does not support "
            "that device command."
        ),
    }


# ============================================================
# LOCAL DEVICE INFORMATION
# ============================================================

def device_information() -> dict:

    return {
        "agent": APP_NAME,
        "version": APP_VERSION,
        "status": agent_status,
        "cloud_status": cloud_status,
        "device_id": (
            cloud_device_id
            or LOCAL_DEVICE_ID
        ),
        "device_name": DEVICE_NAME,
        "platform": "Windows",
    }


# ============================================================
# LOCAL AUTHENTICATION
# ============================================================

def check_local_token(
    token: Optional[str],
) -> None:

    if token != LOCAL_DEVICE_TOKEN:

        raise HTTPException(
            status_code=401,
            detail="Unauthorized device.",
        )


# ============================================================
# LOCAL ROOT
# ============================================================

@app.get("/")
def local_home():

    return device_information()


# ============================================================
# LOCAL DEVICE
# ============================================================

@app.get("/device")
def local_device():

    return device_information()


# ============================================================
# LOCAL PAIRING INFO
# ============================================================

@app.get("/pair")
def local_pairing_info():

    config = load_local_config()

    code = (
        cloud_pairing_code
        or config.get(
            "pairing_code",
            "",
        )
    )

    return {
        "device_id": (
            cloud_device_id
            or LOCAL_DEVICE_ID
        ),
        "device_name": DEVICE_NAME,
        "pairing_code": code,
        "expires_in": 0,
        "paired": bool(
            cloud_device_token
        ),
    }


# ============================================================
# LOCAL PAIR
# ============================================================

@app.post("/pair")
def local_pair(
    request: PairRequest,
):

    submitted = (
        request.code
        .strip()
        .upper()
    )

    config = load_local_config()

    current = (
        cloud_pairing_code
        or config.get(
            "pairing_code",
            "",
        )
    )

    if not current:

        raise HTTPException(
            status_code=410,
            detail="No active pairing code.",
        )

    if not secrets.compare_digest(
        submitted,
        current.upper(),
    ):

        raise HTTPException(
            status_code=401,
            detail="Invalid pairing code.",
        )

    # The cloud must complete the actual pairing.
    if not cloud_device_token:

        if not claim_cloud_token():

            raise HTTPException(
                status_code=503,
                detail=(
                    "Pairing accepted locally, "
                    "but cloud token setup is not complete."
                ),
            )

    return {
        "success": True,
        "message": "Device paired successfully.",
        "device_id": (
            cloud_device_id
            or LOCAL_DEVICE_ID
        ),
        "device_name": DEVICE_NAME,
    }


# ============================================================
# LOCAL ACTION
# ============================================================

@app.post("/action")
def local_action(
    request: ActionRequest,
    x_emma_token: Optional[str] = Header(
        default=None,
        alias="X-EMMA-Token",
    ),
):

    check_local_token(
        x_emma_token
    )

    return execute_action(
        request.action
    )


# ============================================================
# mDNS DISCOVERY
# ============================================================

def get_local_ip() -> str:

    candidates = []

    for _, addresses in (
        psutil.net_if_addrs()
    ).items():

        for address in addresses:

            if address.family != socket.AF_INET:
                continue

            ip = address.address

            if ip.startswith("127."):
                continue

            if ip.startswith("169.254."):
                continue

            is_private = (
                ip.startswith("192.168.")
                or ip.startswith("10.")
                or any(
                    ip.startswith(
                        f"172.{value}."
                    )
                    for value in range(
                        16,
                        32,
                    )
                )
            )

            if is_private:

                candidates.append(
                    ip
                )

    if candidates:

        for ip in candidates:

            if ip.startswith(
                "192.168."
            ):
                return ip

        return candidates[0]

    return "127.0.0.1"


def start_mdns_discovery():

    global zeroconf_instance
    global service_info

    try:

        stop_mdns_discovery()

        local_ip = get_local_ip()

        if local_ip == "127.0.0.1":

            print(
                "EMMA mDNS: No LAN address found."
            )

            return

        advertised_device_id = (
            cloud_device_id
            or LOCAL_DEVICE_ID
        )

        service_name = (
            f"EMMA-{DEVICE_NAME}."
            f"{EMMA_SERVICE_TYPE}"
        )

        properties = {
            b"device_id": (
                advertised_device_id.encode(
                    "utf-8"
                )
            ),
            b"device_name": (
                DEVICE_NAME.encode(
                    "utf-8"
                )
            ),
            b"version": (
                APP_VERSION.encode(
                    "utf-8"
                )
            ),
            b"agent": (
                b"EMMA Windows Companion"
            ),
        }

        service_info = ServiceInfo(
            type_=EMMA_SERVICE_TYPE,
            name=service_name,
            addresses=[
                socket.inet_aton(
                    local_ip
                )
            ],
            port=LOCAL_AGENT_PORT,
            properties=properties,
            server=(
                f"{DEVICE_NAME}.local."
            ),
        )

        zeroconf_instance = Zeroconf()

        zeroconf_instance.register_service(
            service_info
        )

        print(
            "EMMA mDNS: Service advertised."
        )

        print(
            f"EMMA mDNS: "
            f"{local_ip}:{LOCAL_AGENT_PORT}"
        )

        print(
            f"EMMA mDNS: "
            f"Device ID = "
            f"{advertised_device_id}"
        )

    except Exception as error:

        print(
            "EMMA mDNS ERROR:",
            error,
        )


def stop_mdns_discovery():

    global zeroconf_instance
    global service_info

    try:

        if zeroconf_instance is not None:

            if service_info is not None:

                zeroconf_instance.unregister_service(
                    service_info
                )

            zeroconf_instance.close()

    except Exception as error:

        print(
            "EMMA mDNS STOP ERROR:",
            error,
        )

    finally:

        zeroconf_instance = None
        service_info = None


# ============================================================
# CLOUD WORKER
# ============================================================

def cloud_worker():

    global cloud_device_id
    global cloud_device_token
    global cloud_pairing_code

    load_cloud_credentials()

    # ========================================================
    # EXISTING TOKEN
    # ========================================================

    if (
        cloud_device_id
        and cloud_device_token
    ):

        print(
            "EMMA: Saved device configuration found."
        )

        print(
            "Device ID:",
            cloud_device_id,
        )

        set_status(
            "Connecting"
        )

        while running_event.is_set():

            if connect_with_token():

                print(
                    "EMMA: Cloud connection established."
                )

                start_mdns_discovery()

                break

            print(
                "EMMA: Reconnecting in",
                RECONNECT_INTERVAL,
                "seconds...",
            )

            set_status(
                "Reconnecting"
            )

            time.sleep(
                RECONNECT_INTERVAL
            )

    # ========================================================
    # EXISTING PENDING PAIRING
    # ========================================================

    elif (
        cloud_device_id
        and cloud_pairing_code
        and not cloud_device_token
    ):

        print("=" * 60)
        print(
            "EMMA COMPUTER READY TO PAIR"
        )
        print("=" * 60)
        print()

        print(
            "Computer:",
            DEVICE_NAME,
        )

        print()

        print(
            "Device ID:",
            cloud_device_id,
        )

        print()

        print(
            "PAIRING CODE:",
            cloud_pairing_code,
        )

        print()

        print(
            "Enter this code in the EMMA Android app."
        )

        print()

        set_status(
            "Waiting for Pairing"
        )

        start_mdns_discovery()

    # ========================================================
    # NEW REGISTRATION
    # ========================================================

    else:

        set_status(
            "Registering"
        )

        registration = None

        while (
            running_event.is_set()
            and registration is None
        ):

            registration = (
                register_cloud_device()
            )

            if registration is None:

                set_status(
                    "Cloud Offline"
                )

                print(
                    "EMMA Cloud unavailable."
                )

                print(
                    "Retrying in",
                    RECONNECT_INTERVAL,
                    "seconds...",
                )

                time.sleep(
                    RECONNECT_INTERVAL
                )

        if not running_event.is_set():
            return

        save_pending_cloud_pairing(
            registration["device_id"],
            registration["pairing_code"],
        )

        print("=" * 60)
        print(
            "EMMA COMPUTER READY TO PAIR"
        )
        print("=" * 60)
        print()

        print(
            "Computer:",
            DEVICE_NAME,
        )

        print()

        print(
            "Device ID:",
            registration["device_id"],
        )

        print()

        print(
            "PAIRING CODE:",
            registration["pairing_code"],
        )

        print()

        print(
            "Enter this code in the EMMA Android app."
        )

        print(
            "=" * 60
        )

        set_status(
            "Waiting for Pairing"
        )

        start_mdns_discovery()

    # ========================================================
    # MAIN CLOUD LOOP
    # ========================================================

    last_heartbeat = 0.0

    while running_event.is_set():

        # ====================================================
        # WAITING FOR ANDROID PAIRING
        # ====================================================

        if (
            cloud_device_id
            and cloud_pairing_code
            and not cloud_device_token
        ):

            set_status(
                "Waiting for Pairing"
            )

            # The gateway returns:
            #
            # 409 -> not paired yet
            # 200 -> token available

            if claim_cloud_token():

                print()
                print(
                    "EMMA: Android pairing completed."
                )

                print(
                    "EMMA: Permanent token saved."
                )

                set_cloud_status(
                    "Connected"
                )

                set_status(
                    "Connected"
                )

                start_mdns_discovery()

                continue

            time.sleep(
                PAIRING_CHECK_INTERVAL
            )

            continue

        # ====================================================
        # AUTHENTICATED DEVICE
        # ====================================================

        if (
            cloud_device_id
            and cloud_device_token
        ):

            # ------------------------------------------------
            # RECONNECT
            # ------------------------------------------------

            if cloud_status != "Connected":

                set_status(
                    "Connecting"
                )

                if not connect_with_token():

                    set_status(
                        "Offline"
                    )

                    time.sleep(
                        RECONNECT_INTERVAL
                    )

                    continue

            # ------------------------------------------------
            # HEARTBEAT
            # ------------------------------------------------

            now = time.time()

            if (
                now - last_heartbeat
                >= HEARTBEAT_INTERVAL
            ):

                if send_heartbeat():

                    last_heartbeat = now

                else:

                    set_cloud_status(
                        "Offline"
                    )

                    set_status(
                        "Reconnecting"
                    )

                    time.sleep(
                        RECONNECT_INTERVAL
                    )

                    continue

            # ------------------------------------------------
            # COMMANDS
            # ------------------------------------------------

            commands = (
                get_cloud_commands()
            )

            for command in commands:

                if not isinstance(
                    command,
                    dict,
                ):
                    continue

                action = command.get(
                    "command"
                )

                command_id = command.get(
                    "id"
                )

                if not action:
                    continue

                print(
                    "EMMA COMMAND:",
                    action,
                )

                try:

                    result = execute_action(
                        str(action)
                    )

                    result[
                        "command_id"
                    ] = command_id

                    send_command_result(
                        result
                    )

                except Exception as error:

                    send_command_result(
                        {
                            "success": False,
                            "command_id": command_id,
                            "message": str(error),
                        }
                    )

            time.sleep(
                COMMAND_POLL_INTERVAL
            )

            continue

        # ----------------------------------------------------
        # SAFETY FALLBACK
        # ----------------------------------------------------

        time.sleep(
            RECONNECT_INTERVAL
        )


# ============================================================
# SYSTEM TRAY
# ============================================================

def create_tray_image():

    image = Image.new(
        "RGB",
        (64, 64),
        (7, 19, 28),
    )

    draw = ImageDraw.Draw(
        image
    )

    draw.ellipse(
        (8, 8, 56, 56),
        fill=(0, 229, 255),
    )

    draw.ellipse(
        (20, 20, 44, 44),
        fill=(7, 19, 28),
    )

    return image


def tray_open(
    icon,
    item,
):

    print()
    print(
        "EMMA is running in the background."
    )

    print(
        "Computer:",
        DEVICE_NAME,
    )

    print(
        "Agent:",
        agent_status,
    )

    print(
        "Cloud:",
        cloud_status,
    )

    if cloud_device_id:

        print(
            "Device ID:",
            cloud_device_id,
        )


def tray_status(
    icon,
    item,
):

    print()
    print(
        "========== EMMA STATUS =========="
    )

    print(
        "Agent:",
        agent_status,
    )

    print(
        "Cloud:",
        cloud_status,
    )

    print(
        "Computer:",
        DEVICE_NAME,
    )

    print(
        "Device ID:",
        cloud_device_id
        or LOCAL_DEVICE_ID,
    )

    if last_cloud_error:

        print(
            "Last error:",
            last_cloud_error,
        )

    print(
        "================================="
    )


def tray_exit(
    icon,
    item,
):

    print(
        "Stopping EMMA..."
    )

    running_event.clear()

    stop_mdns_discovery()

    icon.stop()


def run_tray():

    icon = pystray.Icon(
        "EMMA",
        create_tray_image(),
        "EMMA",
        pystray.Menu(
            pystray.MenuItem(
                "Open EMMA",
                tray_open,
            ),
            pystray.MenuItem(
                "Status",
                tray_status,
            ),
            pystray.MenuItem(
                "Exit",
                tray_exit,
            ),
        ),
    )

    icon.run()


# ============================================================
# LOCAL SERVER
# ============================================================

def run_local_server():

    uvicorn.run(
        app,
        host=LOCAL_AGENT_HOST,
        port=LOCAL_AGENT_PORT,
        log_level="warning",
    )


# ============================================================
# CLEANUP
# ============================================================

def cleanup():

    running_event.clear()

    stop_mdns_discovery()


atexit.register(
    cleanup
)


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 60)
    print(
        "          EMMA WINDOWS COMPANION"
    )
    print("=" * 60)

    print()

    print(
        "Computer:",
        DEVICE_NAME,
    )

    print(
        "Version:",
        APP_VERSION,
    )

    print(
        "Cloud:",
        CLOUD_URL,
    )

    print(
        "Local Agent:",
        f"http://127.0.0.1:{LOCAL_AGENT_PORT}",
    )

    print()

    # --------------------------------------------------------
    # mDNS
    # --------------------------------------------------------

    start_mdns_discovery()

    # --------------------------------------------------------
    # Local HTTP server
    # --------------------------------------------------------

    server_thread = threading.Thread(
        target=run_local_server,
        daemon=True,
        name="EMMA-Local-Server",
    )

    server_thread.start()

    # --------------------------------------------------------
    # Cloud worker
    # --------------------------------------------------------

    cloud_thread = threading.Thread(
        target=cloud_worker,
        daemon=True,
        name="EMMA-Cloud-Worker",
    )

    cloud_thread.start()

    set_status(
        "Running"
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    try:

        main()

        # System tray keeps the application alive.
        run_tray()

    except KeyboardInterrupt:

        running_event.clear()

        print(
            "EMMA stopped."
        )

    except Exception as error:

        running_event.clear()

        print("=" * 60)
        print(
            "EMMA STARTUP ERROR"
        )
        print("=" * 60)

        print(
            repr(error)
        )

        print("=" * 60)

        stop_mdns_discovery()
