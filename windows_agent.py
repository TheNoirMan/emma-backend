import json
import os
import socket
import sys
import time
import threading

import requests
import pystray
from PIL import Image


# ============================================================
# EMMA WINDOWS AGENT
# ============================================================

# ------------------------------------------------------------
# DEVELOPMENT SERVER
# ------------------------------------------------------------
#
# Local FastAPI server:
#   http://127.0.0.1:8000
#
# Later change this to your public EMMA Cloud URL.
#
SERVER_URL = "http://127.0.0.1:8000"


# ============================================================
# CONFIGURATION
# ============================================================

CONFIG_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "emma_device.json",
)

HEARTBEAT_INTERVAL = 10
RECONNECT_INTERVAL = 5
REQUEST_TIMEOUT = 10


# ============================================================
# GLOBAL STATE
# ============================================================

agent_running = True
agent_status = "Starting"


# ============================================================
# TERMINAL
# ============================================================

def clear_screen():
    os.system(
        "cls" if os.name == "nt" else "clear"
    )


def banner():
    print("=" * 60)
    print("                    EMMA")
    print("               WINDOWS AGENT")
    print("=" * 60)
    print()


# ============================================================
# DEVICE NAME
# ============================================================

def get_device_name():
    return socket.gethostname()


# ============================================================
# CONFIGURATION
# ============================================================

def load_config():

    if not os.path.exists(CONFIG_FILE):
        return None

    try:

        with open(
            CONFIG_FILE,
            "r",
            encoding="utf-8",
        ) as file:

            data = json.load(file)

        if not isinstance(data, dict):
            return None

        return data

    except Exception as error:

        print(
            "Could not read EMMA device configuration."
        )

        print(
            "Error:",
            error,
        )

        return None


def save_config(
    device_id,
    device_token,
    device_name,
):

    data = {
        "device_id": device_id,
        "device_token": device_token,
        "device_name": device_name,
        "platform": "windows",
    }

    try:

        with open(
            CONFIG_FILE,
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                data,
                file,
                indent=4,
            )

        return True

    except Exception as error:

        print(
            "Could not save EMMA device configuration."
        )

        print(
            "Error:",
            error,
        )

        return False


# ============================================================
# CLOUD REQUEST
# ============================================================

def post(
    endpoint,
    payload=None,
):

    url = f"{SERVER_URL}{endpoint}"

    response = requests.post(
        url,
        json=payload or {},
        timeout=REQUEST_TIMEOUT,
    )

    return response


def get(
    endpoint,
):

    url = f"{SERVER_URL}{endpoint}"

    response = requests.get(
        url,
        timeout=REQUEST_TIMEOUT,
    )

    return response


# ============================================================
# REGISTER DEVICE
# ============================================================

def register_device():

    device_name = get_device_name()

    print()
    print(
        "Registering this Windows computer with EMMA..."
    )
    print()
    print(
        "Computer:",
        device_name,
    )
    print()

    try:

        response = post(
            "/device/register",
            {
                "device_name": device_name,
                "platform": "windows",
            },
        )

        if response.status_code != 200:

            print()
            print("Registration failed.")

            print(
                "HTTP:",
                response.status_code,
            )

            print(
                "Response:",
                response.text,
            )

            return None

        data = response.json()

        device_id = data.get("device_id")

        pairing_code = data.get("pairing_code")

        if not device_id or not pairing_code:

            print()
            print(
                "Invalid response from EMMA Cloud."
            )

            print(data)

            return None

        return {
            "device_id": device_id,
            "pairing_code": pairing_code,
            "device_name": device_name,
        }

    except requests.RequestException as error:

        print()
        print(
            "Could not connect to EMMA Cloud."
        )

        print()
        print(
            "Server:",
            SERVER_URL,
        )

        print(
            "Error:",
            error,
        )

        print()

        return None


# ============================================================
# GET DEVICE STATUS
# ============================================================

def get_status(
    device_id,
):

    try:

        response = get(
            f"/device/{device_id}/status"
        )

        if response.status_code != 200:
            return None

        return response.json()

    except requests.RequestException:

        return None


# ============================================================
# GET DEVICE INFORMATION
# ============================================================

def get_device_info(
    device_id,
):

    try:

        response = get(
            f"/device/{device_id}"
        )

        if response.status_code != 200:
            return None

        return response.json()

    except requests.RequestException:

        return None


# ============================================================
# HEARTBEAT
# ============================================================

def heartbeat(
    device_id,
):

    try:

        response = post(
            f"/device/{device_id}/heartbeat",
            {},
        )

        return response.status_code == 200

    except requests.RequestException:

        return False


# ============================================================
# TOKEN RECONNECT
# ============================================================

def reconnect_with_token(
    config,
):

    device_id = config.get(
        "device_id"
    )

    device_token = config.get(
        "device_token"
    )

    if not device_id or not device_token:
        return False

    print()
    print(
        "Existing EMMA device configuration found."
    )

    print()

    print(
        "Device:",
        config.get(
            "device_name",
            get_device_name(),
        ),
    )

    print(
        "Device ID:",
        device_id,
    )

    print()
    print(
        "Connecting to EMMA Cloud..."
    )

    try:

        response = post(
            "/device/token-connect",
            {
                "device_id": device_id,
                "device_token": device_token,
            },
        )

        if response.status_code == 200:

            data = response.json()

            if data.get("status") == "connected":

                print()
                print(
                    "Connection successful."
                )

                print()

                return True

        print(
            "Connection failed."
        )

        print(
            "HTTP:",
            response.status_code,
        )

        print(
            "Response:",
            response.text,
        )

        return False

    except requests.RequestException as error:

        print()
        print(
            "Connection failed."
        )

        print(
            "Error:",
            error,
        )

        print()

        return False


# ============================================================
# WAIT FOR PAIRING
# ============================================================

def wait_for_pairing(
    registration,
):

    device_id = registration[
        "device_id"
    ]

    pairing_code = registration[
        "pairing_code"
    ]

    device_name = registration[
        "device_name"
    ]

    clear_screen()
    banner()

    print(
        "YOUR COMPUTER IS READY TO PAIR"
    )

    print()

    print(
        "Computer:",
        device_name,
    )

    print()

    print(
        "PAIRING CODE"
    )

    print()

    print(
        f"      {pairing_code}"
    )

    print()

    print(
        "Enter this code in the EMMA Android app."
    )

    print()

    print(
        "Waiting for pairing..."
    )

    print()

    while agent_running:

        try:

            status = get_status(
                device_id
            )

            if status:

                if status.get(
                    "connected"
                ) is True:

                    print()
                    print("=" * 60)
                    print(
                        "DEVICE PAIRED SUCCESSFULLY"
                    )
                    print("=" * 60)
                    print()

                    return True

            time.sleep(3)

        except Exception:

            time.sleep(
                RECONNECT_INTERVAL
            )

    return False


# ============================================================
# AUTO RECONNECT LOOP
# ============================================================

def connection_loop(
    config,
):

    global agent_status

    device_id = config[
        "device_id"
    ]

    clear_screen()
    banner()

    print(
        "EMMA WINDOWS AGENT"
    )

    print()

    print(
        "Computer:",
        config.get(
            "device_name",
            get_device_name(),
        ),
    )

    print()

    print(
        "Device ID:",
        device_id,
    )

    print()

    print(
        "Status: CONNECTED"
    )

    print()

    print(
        "EMMA is connected to this computer."
    )

    print()

    print(
        "Heartbeat interval:",
        HEARTBEAT_INTERVAL,
        "seconds",
    )

    print()

    agent_status = "Connected"

    while agent_running:

        success = heartbeat(
            device_id
        )

        if success:

            agent_status = "Connected"

            print(
                "[ONLINE] EMMA connection healthy."
            )

            time.sleep(
                HEARTBEAT_INTERVAL
            )

            continue

        # ----------------------------------------------------
        # CLOUD CONNECTION LOST
        # ----------------------------------------------------

        agent_status = "Offline"

        print()

        print(
            "[OFFLINE] Connection to EMMA Cloud lost."
        )

        print(
            "Attempting automatic reconnection..."
        )

        print()

        while agent_running:

            if reconnect_with_token(
                config
            ):

                agent_status = "Connected"

                print(
                    "Reconnected successfully."
                )

                print()

                break

            agent_status = "Offline"

            print(
                "Retrying in",
                RECONNECT_INTERVAL,
                "seconds...",
            )

            time.sleep(
                RECONNECT_INTERVAL
            )


# ============================================================
# FIRST TIME SETUP
# ============================================================

def first_time_setup():

    global agent_status

    registration = register_device()

    if registration is None:

        agent_status = "Cloud Offline"

        print(
            "EMMA Agent could not register this computer."
        )

        return None

    clear_screen()
    banner()

    print(
        "YOUR COMPUTER IS READY TO PAIR"
    )

    print()

    print(
        "Computer:",
        registration[
            "device_name"
        ],
    )

    print()

    print(
        "PAIRING CODE"
    )

    print()

    print(
        f"      {registration['pairing_code']}"
    )

    print()

    print(
        "Enter this code in the EMMA Android app."
    )

    print()

    print(
        "Waiting for pairing..."
    )

    print()

    agent_status = "Waiting for Pairing"

    device_id = registration[
        "device_id"
    ]

    while agent_running:

        try:

            info = get_device_info(
                device_id
            )

            if info:

                if info.get(
                    "has_token"
                ):

                    print()
                    print(
                        "Pairing completed."
                    )

                    print()

                    print(
                        "Device is now paired."
                    )

                    print()

                    agent_status = "Paired"

                    # ------------------------------------------------
                    # IMPORTANT
                    #
                    # The current gateway only exposes has_token.
                    # It does not provide the actual token here.
                    #
                    # Therefore we cannot save a reconnect token yet.
                    #
                    # Once /device/token or equivalent secure endpoint
                    # exists, this section should retrieve it.
                    # ------------------------------------------------

                    return {
                        "device_id": device_id,
                        "device_name": registration[
                            "device_name"
                        ],
                    }

            time.sleep(3)

        except requests.RequestException:

            agent_status = "Cloud Offline"

            print(
                "Cloud unavailable. Retrying..."
            )

            time.sleep(
                RECONNECT_INTERVAL
            )

    return None


# ============================================================
# MAIN AGENT
# ============================================================

def main():

    global agent_status

    clear_screen()
    banner()

    print(
        "Starting EMMA Windows Agent..."
    )

    print()

    config = load_config()

    # ========================================================
    # EXISTING CONFIGURATION
    # ========================================================

    if config:

        print(
            "Existing EMMA device configuration found."
        )

        print()

        if reconnect_with_token(
            config
        ):

            connection_loop(
                config
            )

            return

        print(
            "Stored device could not be connected."
        )

        print(
            "Starting pairing process..."
        )

        print()

        time.sleep(2)

    # ========================================================
    # FIRST PAIRING
    # ========================================================

    registration = register_device()

    if registration is None:

        agent_status = "Cloud Offline"

        print()
        print(
            "EMMA Agent will continue running."
        )

        print(
            "Waiting for the cloud connection..."
        )

        while agent_running:

            time.sleep(
                RECONNECT_INTERVAL
            )

            registration = register_device()

            if registration:

                break

        if not agent_running:
            return

    # ========================================================
    # SHOW PAIRING INFORMATION
    # ========================================================

    clear_screen()
    banner()

    print(
        "YOUR COMPUTER IS READY TO PAIR"
    )

    print()

    print(
        "Computer:",
        registration[
            "device_name"
        ],
    )

    print()

    print(
        "PAIRING CODE"
    )

    print()

    print(
        f"      {registration['pairing_code']}"
    )

    print()

    print(
        "Enter this code in the EMMA Android app."
    )

    print()

    print(
        "Waiting for pairing..."
    )

    print()

    agent_status = "Waiting for Pairing"

    # ========================================================
    # WAIT FOR ANDROID PAIRING
    # ========================================================

    device_id = registration[
        "device_id"
    ]

    while agent_running:

        try:

            info = get_device_info(
                device_id
            )

            if info:

                if info.get(
                    "has_token"
                ):

                    print()
                    print("=" * 60)
                    print(
                        "PAIRING COMPLETE"
                    )
                    print("=" * 60)
                    print()

                    print(
                        "Android successfully paired"
                        " this computer."
                    )

                    print()

                    print(
                        "The Windows Agent is now ready."
                    )

                    print()

                    agent_status = "Paired"

                    # ------------------------------------------------
                    # CURRENT GATEWAY LIMITATION
                    # ------------------------------------------------
                    #
                    # The current gateway does not expose the actual
                    # device token to the Windows Agent.
                    #
                    # Therefore we cannot create a persistent config
                    # here yet.
                    #
                    # Once the secure token endpoint exists, save:
                    #
                    # save_config(
                    #     device_id,
                    #     device_token,
                    #     registration["device_name"],
                    # )
                    #
                    # ------------------------------------------------

                    break

            time.sleep(3)

        except requests.RequestException:

            agent_status = "Cloud Offline"

            print(
                "Waiting for EMMA Cloud..."
            )

            time.sleep(
                RECONNECT_INTERVAL
            )

    # ========================================================
    # KEEP AGENT RUNNING
    # ========================================================

    if agent_running:

        print()
        print(
            "EMMA Agent is running in background."
        )

        print(
            "System tray is active."
        )

        print()

        # Keep this agent alive.
        #
        # The tray controls application lifetime.

        while agent_running:

            time.sleep(1)


# ============================================================
# SYSTEM TRAY
# ============================================================

def create_tray_image():

    return Image.new(
        "RGB",
        (64, 64),
        (0, 229, 255),
    )


def tray_status(
    icon,
    item,
):

    print()
    print(
        "EMMA Agent Status:",
        agent_status,
    )


def exit_agent(
    icon,
    item,
):

    global agent_running

    print()
    print(
        "Stopping EMMA Agent..."
    )

    agent_running = False

    icon.stop()


def run_tray():

    icon = pystray.Icon(
        "EMMA",
        create_tray_image(),
        "EMMA Agent",
        menu=pystray.Menu(
            pystray.MenuItem(
                "EMMA Agent",
                tray_status,
            ),
            pystray.MenuItem(
                "Exit",
                exit_agent,
            ),
        ),
    )

    icon.run()


# ============================================================
# APPLICATION ENTRY POINT
# ============================================================

if __name__ == "__main__":

    try:

        # --------------------------------------------------------
        # Start EMMA Agent in background thread
        # --------------------------------------------------------

        agent_thread = threading.Thread(
            target=main,
            daemon=True,
        )

        agent_thread.start()

        # --------------------------------------------------------
        # Start system tray
        # --------------------------------------------------------

        run_tray()

        # --------------------------------------------------------
        # Tray has exited
        # --------------------------------------------------------

        agent_running = False

        print()
        print(
            "EMMA Windows Agent stopped."
        )

    except KeyboardInterrupt:

        agent_running = False

        print()
        print(
            "EMMA Windows Agent stopped."
        )

    except Exception as error:

        agent_running = False

        print()
        print("=" * 60)
        print(
            "EMMA AGENT ERROR"
        )
        print("=" * 60)
        print(
            repr(error)
        )
        print("=" * 60)

        sys.exit(1)