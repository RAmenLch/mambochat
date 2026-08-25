## Desktop Client Settings Guide

The MamboChat desktop client provides a dedicated settings window for managing runtime mode, backend service, and other configurations. Below is a guide for each feature.

---

### Opening the Settings Window

You can open it from the tray menu in the main application interface.

![Desktop Client Settings Window](img/桌面端.png)

> **First Launch Note**: When starting Local Mode for the first time, the system needs to extract the embedded Python runtime environment (several hundred MB). This process may take a few minutes — please be patient. Once extraction is complete, subsequent launches will use the extracted environment directly and will not repeat this process.

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
- **Data Directory**: Storage location for the databases and uploads. Defaults to `%AppData%\mambochat-desktop\data` (usually on the C: drive). Because the databases can grow quite large, we recommend pointing this to a drive with plenty of free space to avoid filling up the system drive.

**When changing the data directory:**

1. Click **Browse…** or type a path manually (leave empty to restore the default location)
2. Click **Save & Apply**. The backend stops first, and depending on the **state of the target directory** you are asked how to proceed:

**① Target directory is empty or does not exist (most common)**

| Option | Description |
|--------|-------------|
| **Migrate & delete old data** | Copies `DB` and `uploads` completely into the new directory, then removes the old one to free disk space (recommended — but only after a successful copy) |
| **Migrate only** | Copies data to the new directory; the old directory is kept |
| **Cancel** | Aborts the change; the data directory stays unchanged |

**② Target directory already contains MamboChat data (`DB/mambo.dat` detected)**

| Option | Description |
|--------|-------------|
| **Use existing data in target** | No migration — switch directly to the dataset already present in the target (useful for switching between multiple datasets) |
| **Migrate & delete old data** | Overwrites the target with the current data, then deletes the old directory |
| **Migrate only** | Overwrites the target with the current data; the old directory is kept |
| **Cancel** | Aborts the change |

> ⚠️ Choosing "Migrate" **overwrites** the MamboChat data already present in the target directory. Proceed with caution.

**③ Target directory is non-empty but has no MamboChat data**

Allowed, with a note: only `DB/` and `uploads/` subdirectories will be created inside it; existing unrelated files are left untouched.

3. After migration, the backend restarts automatically using the new directory. Chat history and uploaded files are unaffected.

> **Note**: Migration copies potentially large amounts of data depending on database size — do not close the app during the process. It is recommended to stop the backend first (or let the save flow do it automatically).

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
