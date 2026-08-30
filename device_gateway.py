from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, Field
from typing import Dict, Optional
import secrets
import time

from device_database import (
    create_device,
    get_device,
    set_connected,
    update_last_seen,
    save_device_token,
    get_device_by_token,
    clear_pairing_code,
)


# ============================================================
# EMMA DEVICE GATEWAY
# ============================================================
#
# ANDROID
#     ↓
# EMMA CLOUD
#     ↓
# DEVICE GATEWAY
#     ↓
# WINDOWS COMPANION
#
# PAIRING FLOW
#
# 1. Windows registers
# 2. Cloud generates:
#       - device ID
#       - pairing code
#       - permanent device token
# 3. Windows displays pairing code
# 4. Android enters pairing code
# 5. Android calls /device/connect
# 6. Windows calls /device/claim-token
# 7. Permanent token is returned to Windows
# 8. Windows saves token locally
# 9. Pairing code is destroyed
# 10. Future starts use /device/token-connect
#
# Pairing code lifetime:
#       30 minutes
#
# The pairing code is also one-time-use.
#
# ============================================================


router = APIRouter(
    prefix="/device",
    tags=["Device Gateway"],
)


# ============================================================
# CONFIGURATION
# ============================================================

PAIRING_CODE_LIFETIME = 30 * 60

ONLINE_TIMEOUT = 30


# ============================================================
# RUNTIME STATE
# ============================================================

# Commands are intentionally kept in memory for the V1 SIH build.
command_queues: Dict[str, list] = {}

# Pairing expiry timestamps are kept in memory.
#
# device_id -> unix timestamp
#
# Example:
#
# {
#     "abc123": 1790000000.0
# }
#
pairing_expiry_times: Dict[str, float] = {}


# ============================================================
# MODELS
# ============================================================

class DeviceRegisterRequest(BaseModel):
    device_name: str
    platform: str = "windows"


class DeviceRegisterResponse(BaseModel):
    device_id: str
    pairing_code: str
    device_name: str
    platform: str
    status: str


class DeviceConnectRequest(BaseModel):
    device_id: str
    pairing_code: str


class DeviceClaimTokenRequest(BaseModel):
    device_id: str
    pairing_code: str


class DeviceTokenConnectRequest(BaseModel):
    device_id: str
    device_token: str


class DeviceCommandRequest(BaseModel):
    device_id: str
    command: str
    payload: dict = Field(default_factory=dict)


# ============================================================
# TOKEN HELPERS
# ============================================================

def generate_pairing_code() -> str:
    """
    Generates a 6-character hexadecimal pairing code.

    Example:
        A2119B
        42B06A
    """
    return secrets.token_hex(3).upper()


def generate_device_token() -> str:
    """
    Generates a long-lived authentication token.
    """
    return secrets.token_urlsafe(32)


# ============================================================
# PAIRING EXPIRY HELPERS
# ============================================================

def set_pairing_expiry(
    device_id: str,
) -> None:

    pairing_expiry_times[
        device_id
    ] = (
        time.time()
        + PAIRING_CODE_LIFETIME
    )


def clear_pairing_expiry(
    device_id: str,
) -> None:

    pairing_expiry_times.pop(
        device_id,
        None,
    )


def check_pairing_code_active(
    device_id: str,
) -> None:
    """
    Checks whether a pairing code is still active.

    Existing devices without an in-memory expiry entry are
    allowed to continue pairing. This keeps the V1 database
    backward-compatible.
    """

    expires_at = pairing_expiry_times.get(
        device_id
    )

    if expires_at is None:
        return

    if time.time() >= expires_at:

        # Destroy expired pairing code.
        clear_pairing_code(
            device_id
        )

        clear_pairing_expiry(
            device_id
        )

        raise HTTPException(
            status_code=410,
            detail=(
                "Pairing code expired. "
                "Generate a new code."
            ),
        )


def get_pairing_seconds_remaining(
    device_id: str,
) -> int:

    expires_at = pairing_expiry_times.get(
        device_id
    )

    if expires_at is None:
        return 0

    remaining = int(
        expires_at - time.time()
    )

    return max(
        0,
        remaining,
    )


# ============================================================
# AUTHENTICATION
# ============================================================

def extract_bearer_token(
    authorization: Optional[str],
) -> Optional[str]:

    if not authorization:
        return None

    parts = authorization.strip().split(
        " ",
        1,
    )

    if len(parts) != 2:
        return None

    if parts[0].lower() != "bearer":
        return None

    token = parts[1].strip()

    return token if token else None


def authenticate_device(
    device_id: str,
    authorization: Optional[str],
    emma_token: Optional[str],
):

    token = extract_bearer_token(
        authorization
    )

    if not token and emma_token:
        token = emma_token.strip()

    if not token:

        raise HTTPException(
            status_code=401,
            detail="Device authentication required.",
        )

    device = get_device(
        device_id
    )

    if device is None:

        raise HTTPException(
            status_code=404,
            detail="Device not found.",
        )

    stored_token = device.get(
        "device_token"
    )

    if not stored_token:

        raise HTTPException(
            status_code=401,
            detail=(
                "Device has not completed "
                "token setup."
            ),
        )

    if not secrets.compare_digest(
        stored_token,
        token,
    ):

        raise HTTPException(
            status_code=401,
            detail="Invalid device token.",
        )

    return device


# ============================================================
# REGISTER DEVICE
# ============================================================

@router.post(
    "/register",
    response_model=DeviceRegisterResponse,
)
def register_device(
    request: DeviceRegisterRequest,
):

    device_id = secrets.token_urlsafe(
        16
    )

    pairing_code = (
        generate_pairing_code()
    )

    device_token = (
        generate_device_token()
    )

    now = time.time()

    # --------------------------------------------------------
    # CREATE DEVICE IN SQLITE
    # --------------------------------------------------------

    create_device(
        device_id=device_id,
        device_name=request.device_name,
        platform=request.platform,
        pairing_code=pairing_code,
        created_at=now,
    )

    # --------------------------------------------------------
    # SAVE PERMANENT TOKEN
    # --------------------------------------------------------

    save_device_token(
        device_id=device_id,
        device_token=device_token,
    )

    # --------------------------------------------------------
    # START 30-MINUTE PAIRING WINDOW
    # --------------------------------------------------------

    set_pairing_expiry(
        device_id
    )

    # --------------------------------------------------------
    # COMMAND QUEUE
    # --------------------------------------------------------

    command_queues[
        device_id
    ] = []

    print("=" * 60)
    print("DEVICE REGISTERED")
    print("Device:", request.device_name)
    print("Platform:", request.platform)
    print("Device ID:", device_id)
    print("Pairing Code:", pairing_code)
    print(
        "Pairing Lifetime:",
        f"{PAIRING_CODE_LIFETIME // 60} minutes",
    )
    print("=" * 60)

    return DeviceRegisterResponse(
        device_id=device_id,
        pairing_code=pairing_code,
        device_name=request.device_name,
        platform=request.platform,
        status="registered",
    )


# ============================================================
# ANDROID FIRST-TIME PAIRING
# ============================================================

@router.post("/connect")
def connect_device(
    request: DeviceConnectRequest,
):

    device = get_device(
        request.device_id
    )

    if device is None:

        raise HTTPException(
            status_code=404,
            detail="Device not found.",
        )

    stored_code = device.get(
        "pairing_code"
    )

    if not stored_code:

        raise HTTPException(
            status_code=410,
            detail=(
                "Pairing code is no longer valid."
            ),
        )

    # --------------------------------------------------------
    # CHECK 30-MINUTE WINDOW
    # --------------------------------------------------------

    check_pairing_code_active(
        request.device_id
    )

    submitted_code = (
        request.pairing_code
        .strip()
        .upper()
    )

    # --------------------------------------------------------
    # VERIFY CODE
    # --------------------------------------------------------

    if not secrets.compare_digest(
        stored_code.upper(),
        submitted_code,
    ):

        raise HTTPException(
            status_code=401,
            detail="Invalid pairing code.",
        )

    now = time.time()

    # --------------------------------------------------------
    # MARK DEVICE CONNECTED
    # --------------------------------------------------------

    set_connected(
        request.device_id,
        True,
        now,
    )

    command_queues.setdefault(
        request.device_id,
        [],
    )

    print("=" * 60)
    print("ANDROID DEVICE PAIRED")
    print("Device:", device["device_name"])
    print("Device ID:", request.device_id)
    print("=" * 60)

    # IMPORTANT:
    #
    # The pairing code is NOT cleared here.
    #
    # Windows still needs it to claim the permanent token.
    #
    return {
        "status": "connected",
        "device_id": device["device_id"],
        "device_name": device["device_name"],
        "device_token": device.get(
            "device_token"
        ),
        "paired": True,
    }


# ============================================================
# WINDOWS AGENT CLAIM TOKEN
# ============================================================

@router.post("/claim-token")
def claim_device_token(
    request: DeviceClaimTokenRequest,
):

    device = get_device(
        request.device_id
    )

    if device is None:

        raise HTTPException(
            status_code=404,
            detail="Device not found.",
        )

    stored_code = device.get(
        "pairing_code"
    )

    if not stored_code:

        raise HTTPException(
            status_code=410,
            detail=(
                "Pairing code is no longer available."
            ),
        )

    # --------------------------------------------------------
    # CHECK EXPIRY
    # --------------------------------------------------------

    check_pairing_code_active(
        request.device_id
    )

    submitted_code = (
        request.pairing_code
        .strip()
        .upper()
    )

    # --------------------------------------------------------
    # VERIFY CODE
    # --------------------------------------------------------

    if not secrets.compare_digest(
        stored_code.upper(),
        submitted_code,
    ):

        raise HTTPException(
            status_code=401,
            detail="Invalid pairing code.",
        )

    # --------------------------------------------------------
    # GET TOKEN
    # --------------------------------------------------------

    device_token = device.get(
        "device_token"
    )

    if not device_token:

        raise HTTPException(
            status_code=500,
            detail="Device token is unavailable.",
        )

    # --------------------------------------------------------
    # MARK DEVICE CONNECTED
    # --------------------------------------------------------

    now = time.time()

    set_connected(
        request.device_id,
        True,
        now,
    )

    # --------------------------------------------------------
    # DESTROY ONE-TIME CODE
    # --------------------------------------------------------

    clear_pairing_code(
        request.device_id
    )

    clear_pairing_expiry(
        request.device_id
    )

    # --------------------------------------------------------
    # COMMAND QUEUE
    # --------------------------------------------------------

    command_queues.setdefault(
        request.device_id,
        [],
    )

    print("=" * 60)
    print(
        "WINDOWS AGENT CLAIMED DEVICE TOKEN"
    )
    print(
        "Device:",
        device["device_name"],
    )
    print(
        "Device ID:",
        request.device_id,
    )
    print(
        "TOKEN CLAIM SUCCESS",
    )
    print("=" * 60)

    return {
        "status": "claimed",
        "device_id": request.device_id,
        "device_name": device["device_name"],
        "device_token": device_token,
        "paired": True,
    }


# ============================================================
# AUTOMATIC TOKEN CONNECTION
# ============================================================

@router.post("/token-connect")
def token_connect(
    request: DeviceTokenConnectRequest,
):

    device = get_device(
        request.device_id
    )

    if device is None:

        raise HTTPException(
            status_code=404,
            detail="Device not found.",
        )

    stored_token = device.get(
        "device_token"
    )

    if not stored_token:

        raise HTTPException(
            status_code=401,
            detail=(
                "Device has no authentication token."
            ),
        )

    if not secrets.compare_digest(
        stored_token,
        request.device_token.strip(),
    ):

        raise HTTPException(
            status_code=401,
            detail="Invalid device token.",
        )

    now = time.time()

    set_connected(
        request.device_id,
        True,
        now,
    )

    command_queues.setdefault(
        request.device_id,
        [],
    )

    print("=" * 60)
    print(
        "WINDOWS AGENT RECONNECTED"
    )
    print(
        "Device:",
        device["device_name"],
    )
    print(
        "Device ID:",
        device["device_id"],
    )
    print("=" * 60)

    return {
        "status": "connected",
        "device_id": device["device_id"],
        "device_name": device["device_name"],
        "authenticated": True,
    }


# ============================================================
# HEARTBEAT
# ============================================================

@router.post(
    "/{device_id}/heartbeat"
)
def device_heartbeat(
    device_id: str,
    authorization: Optional[str] = Header(
        default=None
    ),
    x_emma_token: Optional[str] = Header(
        default=None,
        alias="X-EMMA-Token",
    ),
):

    authenticate_device(
        device_id,
        authorization,
        x_emma_token,
    )

    now = time.time()

    update_last_seen(
        device_id,
        now,
    )

    return {
        "status": "ok",
        "device_id": device_id,
        "connected": True,
        "last_seen": now,
    }


# ============================================================
# STATUS
# ============================================================

@router.get(
    "/{device_id}/status"
)
def device_status(
    device_id: str,
    authorization: Optional[str] = Header(
        default=None
    ),
    x_emma_token: Optional[str] = Header(
        default=None,
        alias="X-EMMA-Token",
    ),
):

    device = authenticate_device(
        device_id,
        authorization,
        x_emma_token,
    )

    last_seen = float(
        device["last_seen"]
    )

    online = (
        time.time() - last_seen
    ) <= ONLINE_TIMEOUT

    return {
        "device_id": device["device_id"],
        "device_name": device["device_name"],
        "platform": device["platform"],
        "connected": bool(
            device["connected"]
        ),
        "online": online,
        "last_seen": last_seen,
    }


# ============================================================
# DEVICE INFO
# ============================================================

@router.get(
    "/{device_id}"
)
def device_info(
    device_id: str,
    authorization: Optional[str] = Header(
        default=None
    ),
    x_emma_token: Optional[str] = Header(
        default=None,
        alias="X-EMMA-Token",
    ),
):

    device = authenticate_device(
        device_id,
        authorization,
        x_emma_token,
    )

    return {
        "device_id": device["device_id"],
        "device_name": device["device_name"],
        "platform": device["platform"],
        "connected": bool(
            device["connected"]
        ),
        "has_token": bool(
            device.get("device_token")
        ),
        "has_pairing_code": bool(
            device.get("pairing_code")
        ),
        "pairing_seconds_remaining": (
            get_pairing_seconds_remaining(
                device_id
            )
        ),
        "last_seen": device["last_seen"],
        "created_at": device["created_at"],
    }


# ============================================================
# SEND COMMAND
# ============================================================

@router.post("/command")
def send_command(
    request: DeviceCommandRequest,
    authorization: Optional[str] = Header(
        default=None
    ),
    x_emma_token: Optional[str] = Header(
        default=None,
        alias="X-EMMA-Token",
    ),
):

    device = authenticate_device(
        request.device_id,
        authorization,
        x_emma_token,
    )

    if not bool(
        device["connected"]
    ):

        raise HTTPException(
            status_code=409,
            detail="Device is not connected.",
        )

    command = {
        "id": secrets.token_urlsafe(12),
        "command": request.command,
        "payload": request.payload,
        "created_at": time.time(),
    }

    command_queues.setdefault(
        request.device_id,
        [],
    )

    command_queues[
        request.device_id
    ].append(
        command
    )

    print("=" * 60)
    print("COMMAND QUEUED")
    print(
        "Device:",
        device["device_name"],
    )
    print(
        "Command:",
        request.command,
    )
    print("=" * 60)

    return {
        "status": "queued",
        "command": command,
    }


# ============================================================
# WINDOWS AGENT — GET COMMANDS
# ============================================================

@router.get(
    "/{device_id}/commands"
)
def get_commands(
    device_id: str,
    authorization: Optional[str] = Header(
        default=None
    ),
    x_emma_token: Optional[str] = Header(
        default=None,
        alias="X-EMMA-Token",
    ),
):

    device = authenticate_device(
        device_id,
        authorization,
        x_emma_token,
    )

    if not bool(
        device["connected"]
    ):

        raise HTTPException(
            status_code=409,
            detail="Device is not connected.",
        )

    commands = command_queues.get(
        device_id,
        [],
    )

    command_queues[
        device_id
    ] = []

    now = time.time()

    update_last_seen(
        device_id,
        now,
    )

    return {
        "device_id": device_id,
        "commands": commands,
    }


# ============================================================
# COMMAND RESULT
# ============================================================

@router.post(
    "/{device_id}/command-result"
)
def command_result(
    device_id: str,
    result: dict,
    authorization: Optional[str] = Header(
        default=None
    ),
    x_emma_token: Optional[str] = Header(
        default=None,
        alias="X-EMMA-Token",
    ),
):

    authenticate_device(
        device_id,
        authorization,
        x_emma_token,
    )

    now = time.time()

    update_last_seen(
        device_id,
        now,
    )

    print("=" * 60)
    print("COMMAND RESULT")
    print(
        "Device:",
        device_id,
    )
    print(
        "Result:",
        result,
    )
    print("=" * 60)

    return {
        "status": "received",
        "device_id": device_id,
    }
