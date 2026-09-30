# Cloud Deployment Guide: Google Cloud & Linux Production Setup

This guide details the complete production deployment procedure for **TechBuilt Open School (TBOS) Automation** on a Linux server (Google Cloud Platform Compute Engine, Debian 12, or Ubuntu 24.04 LTS).

The deployment adheres strictly to our foundational principles:
- **Zero Software Cost**: Leverages free tiers and open-source tools (Cloudflare Tunnel, Google Drive via rclone, standard library SMTP, official platform APIs).
- **Zero Open Inbound Ports**: No internal application ports (8080, 5678, 5432) are exposed to the public internet. Ingress is handled exclusively through an encrypted Cloudflare Tunnel.
- **Human-in-the-Loop Approval**: Reviewers approve content via the web dashboard at `https://dashboard.yourdomain.com/dashboard` before publishing.

```mermaid
flowchart TD
    subgraph PublicInternet [Public Internet / Reviewers]
        Reviewer[Editorial Reviewer / Mobile]
        Reviewer -->|HTTPS with SSO / PIN| CF[Cloudflare Edge Network]
    end

    subgraph GCP_VM [GCP Compute Engine VM - No Open Ports]
        subgraph DockerNetwork [Docker Network: tbos_edge & tbos_private]
            CF_Tunnel[cloudflared container / daemon]
            API[renderer-api:8080\nFastAPI Dashboard]
            N8N[n8n:5678\nWorkflow Engine]
            PG[(PostgreSQL 17\nInternal Private)]
            Storage[storage/ renders & media]

            CF_Tunnel -->|outbound tunnel| CF
            CF_Tunnel -->|HTTP :8080| API
            CF_Tunnel -->|HTTP :5678| N8N
            API --> PG
            N8N --> PG
            API <--> Storage
            N8N <--> Storage
        end

        Cron[Cron / Systemd Timer\n02:00 AM Daily]
        Rclone[rclone CLI Engine]
        Cron --> Rclone
        Rclone -->|Encrypted Backup| GDrive[(Google Drive\n15 GB Free Storage)]
    end
```

---

## 1. VM Specifications & Host Sizing

### Recommended GCP Compute Engine Spec
| Component | Minimum Specification | Recommended Production Spec | Notes |
|---|---|---|---|
| **Machine Type** | `e2-medium` (2 vCPU, 4 GB RAM) | `e2-standard-2` (2 vCPU, 8 GB RAM) | `e2-medium` is budget-friendly; 4 GB RAM is sufficient with swap enabled. |
| **Operating System** | Ubuntu 24.04 LTS (x86_64) | Debian 12 (Bookworm) / Ubuntu 24.04 LTS | Both have first-party Docker support. |
| **Boot Disk** | 30 GB Balanced Persistent Disk | 50 GB `pd-balanced` | Provides sufficient IOPS and capacity for rendered video and database logs. |
| **Network / VPC** | Default VPC | Default VPC | **Firewall rules: Deny all ingress** except SSH (port 22). |

> [!TIP]
> **GCP IAP (Identity-Aware Proxy) SSH**: For maximum security, configure Google Cloud IAP so SSH access is restricted to authenticated Google accounts with zero public IP exposure (`gcloud compute ssh --tunnel-through-iap`).

---

## 2. Linux Host Initialization

Connect to your Linux VM via SSH and execute the following commands.

### 2.1 Update System and Configure Swap
Video compositing with FFmpeg and Pillow image rendering requires temporary memory headroom. Configure a 4 GB swap file to prevent Out-Of-Memory (OOM) killer incidents:

```bash
# Update package repositories
sudo apt-get update && sudo apt-get upgrade -y

# Install essential system utilities
sudo apt-get install -y curl git ca-certificates gnupg lsb-release tar rclone jq

# Create and enable 4GB swap space
if [ ! -f /swapfile ]; then
    sudo fallocate -l 4G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
fi
```

### 2.2 Install Docker Engine & Docker Compose Plugin
Install the official Docker repository packages:

```bash
# Add Docker official GPG key
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# Add Docker apt repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker packages
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Enable Docker on startup and allow current user non-root access
sudo systemctl enable --now docker
sudo usermod -aG docker $USER

# Apply group changes without logging out
newgrp docker
```

Verify Docker installation:
```bash
docker compose version
```

---

## 3. Clone Repository & Production Environment Setup

### 3.1 Clone the Project
```bash
sudo mkdir -p /opt/tbos
sudo chown -R $USER:$USER /opt/tbos
git clone https://github.com/your-org/TBOS_Automation.git /opt/tbos
cd /opt/tbos

# Ensure storage directories exist with appropriate permissions
mkdir -p storage/renders storage/handoff backups
chmod 0750 storage backups
```

### 3.2 Configure `.env` for Production
Create the `.env` configuration file from the template:

```bash
cp .env.example .env
nano .env
```

Generate secure random secrets:
```bash
openssl rand -hex 32  # Run this for POSTGRES_PASSWORD, APP_DB_PASSWORD, N8N_DB_PASSWORD, N8N_ENCRYPTION_KEY, INTERNAL_API_KEY
```

Configure key production variables in `.env`:
```dotenv
APP_ENV=production
APP_LOG_LEVEL=INFO
APP_OPENAPI_ENABLED=false
APP_TIMEZONE=Asia/Karachi

# Generated passwords
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_strong_postgres_password
APP_DB_NAME=tbos_content
APP_DB_USER=tbos_app
APP_DB_PASSWORD=your_strong_app_db_password
DATABASE_URL=postgresql+psycopg://tbos_app:your_strong_app_db_password@postgres:5432/tbos_content

N8N_DB_NAME=n8n
N8N_DB_USER=n8n_app
N8N_DB_PASSWORD=your_strong_n8n_password
N8N_ENCRYPTION_KEY=your_strong_encryption_key_32_chars

INTERNAL_API_KEY=your_strong_internal_api_key_32_chars

# Domain & Ingress Settings
N8N_DOMAIN=n8n.yourdomain.com
DASHBOARD_DOMAIN=dashboard.yourdomain.com
DASHBOARD_PUBLIC_URL=https://dashboard.yourdomain.com/dashboard

# Email Notifications (Gmail / SMTP)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=editorial@yourdomain.com
SMTP_PASSWORD=your_gmail_app_password
SMTP_FROM=TechBuilt Open School <editorial@yourdomain.com>
NOTIFICATION_EMAIL=reviewer@yourdomain.com
FEATURE_EMAIL_NOTIFICATIONS_ENABLED=true

# AI Provider (Google Gemini API)
GEMINI_API_KEY=your_google_gemini_api_key
GEMINI_MODEL=gemini-2.5-flash

# Cloudflare Tunnel Token (from Cloudflare Zero Trust)
CLOUDFLARE_TUNNEL_TOKEN=eyJh...your_token_here

# Offsite Backup
RCLONE_REMOTE=gdrive:TBOS_Backups
LOCAL_RETENTION_DAYS=7
CLOUD_RETENTION_DAYS=30
```

---

## 4. Cloudflare Tunnel Configuration (Zero-Trust Ingress)

Cloudflare Tunnel creates an encrypted outbound-only connection to Cloudflare edge nodes. This allows your dashboard and n8n webhooks to be reached securely over HTTPS without opening ports on your GCP VM firewall.

### 4.1 Create Tunnel in Cloudflare Dashboard
1. Log in to [Cloudflare One / Zero Trust](https://one.dash.cloudflare.com/).
2. Navigate to **Networks** -> **Tunnels** -> **Create a tunnel**.
3. Select **Cloudflared** connector -> Name it `tbos-production`.
4. Copy the generated **Tunnel Token**.
5. Set `CLOUDFLARE_TUNNEL_TOKEN` in `/opt/tbos/.env`.

### 4.2 Configure Public Hostnames
In the Cloudflare Tunnel configuration, add two public hostnames:

| Public Hostname | Service Type | URL | Purpose |
|---|---|---|---|
| `dashboard.yourdomain.com` | `HTTP` | `renderer-api:8080` (or `localhost:8080`) | Content Approval Dashboard & Media Serving |
| `n8n.yourdomain.com` | `HTTP` | `n8n:5678` (or `localhost:5678`) | n8n Automation Engine & Webhook Receiver |

> [!IMPORTANT]
> **Cloudflare Access (Zero Trust Authentication)**:
> In the Cloudflare Zero Trust dashboard under **Access** -> **Applications**, add a policy to protect `dashboard.yourdomain.com` and `n8n.yourdomain.com` with email One-Time PIN (OTP) or Google Workspace authentication. This ensures only designated reviewers can view the dashboard.

---

## 5. Deploying and Running the Stack

We use the production overlay (`docker-compose.prod.yml`) which binds all ports to `127.0.0.1`, enforces `APP_ENV=production`, disables Swagger docs, and manages the `cloudflared` container:

```bash
cd /opt/tbos

# Build container images
docker compose -f compose.yaml -f docker-compose.prod.yml build

# Start services with Cloudflare Tunnel profile
docker compose -f compose.yaml -f docker-compose.prod.yml --profile cloudflare up -d

# Verify all containers are healthy
docker compose ps
```

### Initial Database Migrations & Seeds
Run Alembic migrations and database seed inside the running container:
```bash
docker compose exec -T renderer-api python -m alembic -c database/alembic.ini upgrade head
docker compose exec -T postgres psql -U postgres -d tbos_content -f /docker-entrypoint-initdb.d/02_seed.sql
```

Test internal endpoint health:
```bash
curl -s http://127.0.0.1:8080/api/v1/config/public | jq
```

---

## 6. Automated Backup Strategy (Google Drive via rclone)

To safeguard rendered media and database states at zero software cost, we use `rclone` with Google Drive (15 GB free personal or workspace storage).

### 6.1 Configure rclone for Google Drive
Run `rclone config` on your local workstation with a browser:
```bash
rclone config
# n) New remote
# name: gdrive
# Storage: drive (Google Drive)
# client_id: (leave blank or use custom GCP OAuth client)
# scope: 1 (Full access)
# Use auto config: Y
```
Once authenticated, copy the generated configuration block from `~/.config/rclone/rclone.conf` on your local machine to `/root/.config/rclone/rclone.conf` or `~/.config/rclone/rclone.conf` on the GCP VM.

Test the connection on the VM:
```bash
rclone lsd gdrive:
```

### 6.2 Test Backup Script
Run the automated backup script manually:
```bash
bash /opt/tbos/scripts/backup-cloud.sh
```
Verify the output confirms:
- PostgreSQL dump created: `tbos-app.dump`
- n8n configuration archived: `n8n-data.tar.gz`
- Rendered media archived: `storage-media.tar.gz`
- Files uploaded to `gdrive:TBOS_Backups/<timestamp>`

### 6.3 Setup Automated Daily Cron Job
Open root crontab:
```bash
sudo crontab -e
```

Add the daily backup schedule to run at 02:00 AM (server local time):
```cron
# TBOS Daily Automated Backup to Google Drive (02:00 AM)
0 2 * * * /opt/tbos/scripts/backup-cloud.sh >> /var/log/tbos-backup.log 2>&1
```

---

## 7. Operations & Maintenance Runbook

### Viewing Service Logs
```bash
# View live API logs
docker compose logs -f renderer-api

# View n8n automation logs
docker compose logs -f n8n

# View Cloudflare Tunnel logs
docker compose logs -f cloudflared
```

### Applying Code Updates
```bash
cd /opt/tbos
git pull origin main
docker compose -f compose.yaml -f docker-compose.prod.yml build renderer-api
docker compose -f compose.yaml -f docker-compose.prod.yml --profile cloudflare up -d
docker compose exec -T renderer-api python -m alembic -c database/alembic.ini upgrade head
```

### Restoring from a Backup
```bash
# Locate latest backup directory
cd /opt/tbos/backups/YYYYMMDD-HHMMSS

# 1. Restore PostgreSQL
docker compose exec -T postgres sh -c 'pg_restore -U "$POSTGRES_USER" -d "$APP_DB_NAME" --clean /tmp/tbos-app.dump' < tbos-app.dump

# 2. Restore n8n data
docker compose stop n8n
tar -xzf n8n-data.tar.gz -C $(docker volume inspect tbos_automation_n8n_data --format '{{.Mountpoint}}')
docker compose start n8n

# 3. Restore media assets
tar -xzf storage-media.tar.gz -C /opt/tbos
```
