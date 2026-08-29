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
# 2. Cloud generates device ID + pairing code + token
# 3. Windows displays pairing code
# 4. Android enters pairing code
# 5. Android calls /device/connect
# 6. Windows claims token
# 7. Token is permanently stored by Windows
# 8. Pairing code is destroyed
# 9. Windows reconnects automatically
#
# IMPORTANT:
# /claim-token also safely completes pairing if Android
# did not call /connect first, as long as the pairing code
# is valid.
#
# ============================================================


router = APIRouter(
    prefix="/device",
    tags=["Device Gateway"],
)


# ============================================================
# RUNTIME COMMAND QUEUE
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
    payload: dict = Field(default_factory=dict)


# ============================================================
# TOKEN HELPERS
# ============================================================

def generate_pairing_code() -> str:
    return secrets.token_hex(3).upper()


def generate_device_token() -> str:
    return secrets.token_urlsafe(32)


# ============================================================
# AUTHENTICATION
# ============================================================

def extract_bearer_token(
    authorization: Optional[str],
) -> Optional[str]:

    if not authorization:
        return None

    parts = authorization.strip().split(" ", 1)

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
            detail="Device has not completed token setup.",
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

    device_id = secrets.token_urlsafe(16)

    pairing_code = generate_pairing_code()

    device_token = generate_device_token()

    now = time.time()

    # --------------------------------------------------------
    # Create device
    # --------------------------------------------------------

    create_device(
        device_id=device_id,
        device_name=request.device_name,
        platform=request.platform,
        pairing_code=pairing_code,
        created_at=now,
    )

    # --------------------------------------------------------
    # Save permanent device token
    # --------------------------------------------------------

    save_device_token(
        device_id=device_id,
        device_token=device_token,
    )

    # --------------------------------------------------------
    # Create command queue
    # --------------------------------------------------------

    command_queues[device_id] = []

    print("=" * 60)
    print("DEVICE REGISTERED")
    print("Device:", request.device_name)
    print("Platform:", request.platform)
    print("Device ID:", device_id)
    print("Pairing Code:", pairing_code)
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
            detail="Pairing code is no longer valid.",
        )

    submitted_code = (
        request.pairing_code
        .strip()
        .upper()
    )

    if not secrets.compare_digest(
        stored_code.upper(),
        submitted_code,
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid pairing code.",
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
    print("ANDROID DEVICE PAIRED")
    print("Device:", device["device_name"])
    print("Device ID:", request.device_id)
    print("=" * 60)

    return {
        "status": "connected",
        "device_id": device["device_id"],
        "device_name": device["device_name"],
        "device_token": device.get("device_token"),
    }


# ============================================================
# WINDOWS AGENT CLAIMS TOKEN
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

    # --------------------------------------------------------
    # Pairing code must still exist
    # --------------------------------------------------------

    if not stored_code:
        raise HTTPException(
            status_code=410,
            detail="Pairing code is no longer available.",
        )

    submitted_code = (
        request.pairing_code
        .strip()
        .upper()
    )

    # --------------------------------------------------------
    # Validate pairing code
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
    # IMPORTANT FIX
    #
    # If Android already called /connect:
    #
    #     connected = 1
    #
    # If Android did NOT call /connect but the correct
    # pairing code is presented here, complete pairing now.
    #
    # This prevents the 409 loop we were seeing.
    # --------------------------------------------------------

    if not bool(device.get("connected")):

        print("=" * 60)
        print("PAIRING FINALIZED THROUGH TOKEN CLAIM")
        print("Device:", device["device_name"])
        print("Device ID:", request.device_id)
        print("=" * 60)

        now = time.time()

        set_connected(
            request.device_id,
            True,
            now,
        )

        # Refresh device from database
        device = get_device(
            request.device_id
        )

    # --------------------------------------------------------
    # Get permanent token
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
    # Destroy one-time pairing code
    # --------------------------------------------------------

    clear_pairing_code(
        request.device_id
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
    print("WINDOWS AGENT CLAIMED DEVICE TOKEN")
    print("Device:", device["device_name"])
    print("Device ID:", request.device_id)
    print("TOKEN CLAIM SUCCESS")
    print("=" * 60)

    return {
        "status": "claimed",
        "device_id": request.device_id,
        "device_name": device["device_name"],
        "device_token": device_token,
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
            detail="Device has no authentication token.",
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
    print("WINDOWS AGENT RECONNECTED")
    print("Device:", device["device_name"])
    print("Device ID:", device["device_id"])
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

@router.post("/{device_id}/heartbeat")
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

@router.get("/{device_id}/status")
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
    ) <= 30

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

@router.get("/{device_id}")
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

    if not bool(device["connected"]):
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
    ].append(command)

    print("=" * 60)
    print("COMMAND QUEUED")
    print("Device:", device["device_name"])
    print("Command:", request.command)
    print("=" * 60)

    return {
        "status": "queued",
        "command": command,
    }


# ============================================================
# WINDOWS AGENT — GET COMMANDS
# ============================================================

@router.get("/{device_id}/commands")
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

    if not bool(device["connected"]):
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

@router.post("/{device_id}/command-result")
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
    print("Device:", device_id)
    print("Result:", result)
    print("=" * 60)

    return {
        "status": "received",
        "device_id": device_id,
    }