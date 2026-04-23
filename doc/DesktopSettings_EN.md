## Desktop Client Settings Guide

The MamboChat desktop client provides a dedicated settings window for managing runtime mode, backend service, and other configurations. Below is a guide for each feature.

---

### Opening the Settings Window

You can open it from the tray menu in the main application interface.

![Desktop Client Settings Window](img/桌面端.png)

---

### 1. Choose Runtime Mode

At the top of the page, you will see the current runtime mode with two options available:

| Mode | Description |
|------|-------------|
| **Local Mode** | Uses the embedded Python environment to automatically start the backend service locally. Data is stored locally — no additional installation needed, works out of the box |
| **Remote Mode** | Connects to a MamboChat backend running on a remote server. Ideal for multi-device sharing or server deployment scenarios |

![Desktop - Local Mode](img/桌面端_本地模式.png)

![Desktop - Remote Mode](img/桌面端_远程模式.png)

---

### 2. Local Mode Configuration

After selecting **Local Mode**, you can configure the following options:

**Basic Settings**

- **Host (Address)**: Backend listening address, defaults to `127.0.0.1` (localhost only)
- **Port Range**: Defaults to `8000 — 8010`. If the starting port is occupied, the system automatically tries the next port
- **Python Path**: Path to the embedded Python interpreter; usually no need to change this

**External Access (Optional)**

If you want other devices on your local network to be able to access your MamboChat, enable **Allow External Access**:

- Once enabled, the backend and frontend gateway bind to `0.0.0.0`
- The page shows your machine's LAN address — other devices can use it to connect
- You can also customize the gateway port (defaults to `5173`)

> **Security Note**: When external access is enabled, any device on the same network can reach your MamboChat instance. Make sure you are in a trusted network.

---

### 3. Remote Mode Configuration

After selecting **Remote Mode**, only one field is required:

- **Server URL**: The full URL of the remote backend, formatted as `http://<IP or domain>:<port>`, e.g., `http://192.168.1.100:8000`

After filling in the URL, click the **Test Connection** button to verify that the address is reachable.

---

### 4. Backend Service Management (Local Mode)

In Local Mode, the bottom section provides controls for managing the backend process:

| Status | Description |
|--------|-------------|
| ● Running | Backend is running normally; displays the actual port and process ID |
| ○ Stopped | Backend is not running |
| ● Starting... | Startup in progress, please wait |
| ● Error | An error occurred during startup or execution; details are shown |

**Control Buttons:**

- **▶ Start**: Launches the backend service with the current configuration
- **■ Stop**: Stops a running backend service
- **↻ Restart**: Stops then restarts (recommended after changing settings to apply new config)

> When switching to Remote Mode, the local backend stops automatically. When switching back to Local Mode, you must manually click **Start**.

---

### 5. Save Configuration

After completing all configuration changes, click **Save Configuration**. Your settings will be persisted, and if necessary, the backend or gateway service will restart automatically to apply the new configuration.
