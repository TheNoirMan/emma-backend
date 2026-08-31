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
    clear_pairing_code,
)


# ============================================================
# EMMA DEVICE GATEWAY
# ============================================================
#
# FINAL SIH PAIRING ARCHITECTURE
#
# WINDOWS COMPANION
#        |
#        | register
#        v
#     EMMA CLOUD
#        |
#        | device_id + pairing_code
#        v
#   WINDOWS DISPLAY
#
# ANDROID
#        |
#        | device_id + pairing_code
#        v
#     /device/connect
#        |
#        | connected = true
#        v
#     EMMA CLOUD
#
# WINDOWS COMPANION
#        |
#        | /device/claim-token
#        v
#   permanent token
#
#
# IMPORTANT:
#
# Windows MUST NOT consume the pairing code before Android
# successfully pairs.
#
# Flow:
#
# 1. Windows registers
# 2. Cloud creates pairing code
# 3. Android enters code
# 4. Android -> /device/connect
# 5. Cloud marks connected=True
# 6. Windows -> /device/claim-token
# 7. Cloud returns permanent token
# 8. Pairing code is destroyed
#
# Pairing code lifetime:
#     30 minutes
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
# RUNTIME COMMAND QUEUE
# ============================================================
#
# SIH V1:
# Keep commands in memory.
#
# Later:
# Redis / PostgreSQL.
#
# ============================================================

command_queues: Dict[str, list] = {}


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
    payload: dict = Field(
        default_factory=dict
    )


# ============================================================
# GENERATORS
# ============================================================


def generate_pairing_code() -> str:
    """
    Generate a 6-character hexadecimal pairing code.

    Examples:
        A2119B
        3B43C7
        42B06A
    """

    return secrets.token_hex(3).upper()


def generate_device_token() -> str:
    """
    Generate the permanent authentication token.
    """

    return secrets.token_urlsafe(32)


# ============================================================
# PAIRING EXPIRY
# ============================================================
#
# We use the existing created_at column from SQLite.
#
# No database migration required.
#
# ============================================================


def check_pairing_code_active(
    device: dict,
) -> None:
    """
    Check whether the pairing code is still inside
    the 30-minute registration window.
    """

    pairing_code = device.get(
        "pairing_code"
    )

    if not pairing_code:

        raise HTTPException(
            status_code=410,
            detail=(
                "Pairing code is no longer active. "
                "Generate a new code."
            ),
        )

    try:

        created_at = float(
            device.get(
                "created_at",
                0,
            )
        )

    except (
        TypeError,
        ValueError,
    ):

        created_at = 0

    # Older records without valid created_at
    # are allowed to continue.
    if created_at <= 0:
        return

    age = time.time() - created_at

    if age >= PAIRING_CODE_LIFETIME:

        clear_pairing_code(
            device["device_id"]
        )

        raise HTTPException(
            status_code=410,
            detail=(
                "Pairing code expired after 30 minutes. "
                "Generate a new code."
            ),
        )


def get_pairing_seconds_remaining(
    device: dict,
) -> int:
    """
    Return remaining pairing time in seconds.
    """

    pairing_code = device.get(
        "pairing_code"
    )

    if not pairing_code:
        return 0

    try:

        created_at = float(
            device.get(
                "created_at",
                0,
            )
        )

    except (
        TypeError,
        ValueError,
    ):

        return 0

    if created_at <= 0:
        return 0

    remaining = (
        PAIRING_CODE_LIFETIME
        - (time.time() - created_at)
    )

    return max(
        0,
        int(remaining),
    )


# ============================================================
# AUTHENTICATION
# ============================================================


def extract_bearer_token(
    authorization: Optional[str],
) -> Optional[str]:

    if not authorization:
        return None

    parts = (
        authorization
        .strip()
        .split(
            " ",
            1,
        )
    )

    if len(parts) != 2:
        return None

    if parts[0].lower() != "bearer":
        return None

    token = parts[1].strip()

    return (
        token
        if token
        else None
    )


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
            detail=(
                "Device authentication required."
            ),
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
    # CREATE DEVICE
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
    #
    # Token exists in the cloud record from registration.
    # It is only released to Windows after Android pairing.
    #
    # --------------------------------------------------------

    save_device_token(
        device_id=device_id,
        device_token=device_token,
    )

    # --------------------------------------------------------
    # COMMAND QUEUE
    # --------------------------------------------------------

    command_queues[
        device_id
    ] = []

    print("=" * 60)
    print("DEVICE REGISTERED")
    print(
        "Device:",
        request.device_name,
    )
    print(
        "Platform:",
        request.platform,
    )
    print(
        "Device ID:",
        device_id,
    )
    print(
        "Pairing Code:",
        pairing_code,
    )
    print(
        "Pairing Lifetime:",
        "30 minutes",
    )
    print(
        "Connected:",
        False,
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
#
# THIS MUST HAPPEN BEFORE WINDOWS CAN CLAIM THE TOKEN.
#
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

    # --------------------------------------------------------
    # CHECK EXPIRY
    # --------------------------------------------------------

    check_pairing_code_active(
        device
    )

    # --------------------------------------------------------
    # GET STORED CODE
    # --------------------------------------------------------

    stored_code = device.get(
        "pairing_code"
    )

    if not stored_code:

        raise HTTPException(
            status_code=410,
            detail=(
                "Pairing code is no longer active. "
                "Generate a new code."
            ),
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
    # MARK ANDROID PAIRED
    # --------------------------------------------------------

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
    print("ANDROID DEVICE PAIRED")
    print(
        "Device:",
        device["device_name"],
    )
    print(
        "Device ID:",
        request.device_id,
    )
    print(
        "Windows token claim is now allowed.",
    )
    print("=" * 60)

    # --------------------------------------------------------
    # RETURN TOKEN TO ANDROID
    # --------------------------------------------------------
    #
    # Android stores this token.
    #
    # Windows will receive the same token through
    # /claim-token after this endpoint succeeds.
    #
    # --------------------------------------------------------

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
#
# CRITICAL FIX:
#
# Windows cannot claim the token until Android has already
# paired successfully.
#
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

    # --------------------------------------------------------
    # CRITICAL:
    #
    # Android must pair FIRST.
    #
    # This prevents Windows from consuming the pairing code
    # before Android gets a chance to use it.
    #
    # --------------------------------------------------------

    if not bool(
        device.get("connected")
    ):

        raise HTTPException(
            status_code=409,
            detail=(
                "Waiting for Android pairing. "
                "Open EMMA on Android and enter the pairing code."
            ),
        )

    # --------------------------------------------------------
    # CHECK EXPIRY
    # --------------------------------------------------------

    check_pairing_code_active(
        device
    )

    # --------------------------------------------------------
    # GET STORED CODE
    # --------------------------------------------------------

    stored_code = device.get(
        "pairing_code"
    )

    if not stored_code:

        raise HTTPException(
            status_code=410,
            detail=(
                "Pairing code is no longer active."
            ),
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
    # GET PERMANENT TOKEN
    # --------------------------------------------------------

    device_token = device.get(
        "device_token"
    )

    if not device_token:

        raise HTTPException(
            status_code=500,
            detail=(
                "Device token is unavailable."
            ),
        )

    now = time.time()

    # --------------------------------------------------------
    # UPDATE LAST SEEN
    # --------------------------------------------------------

    set_connected(
        request.device_id,
        True,
        now,
    )

    # --------------------------------------------------------
    # DESTROY ONE-TIME PAIRING CODE
    # --------------------------------------------------------

    clear_pairing_code(
        request.device_id
    )

    # --------------------------------------------------------
    # INITIALIZE COMMAND QUEUE
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
    print(
        "Pairing code destroyed.",
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
# DEVICE INFORMATION
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
                device
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
# WINDOWS GET COMMANDS
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