"""
AION Core - Worker Tasks
Cloud-init based VM provisioning with autonomous scaling.
"""
import os
import json
import time
import shutil
import subprocess
import tempfile
import urllib.parse

import redis
import libvirt
import requests
import xml.etree.ElementTree as ET

from celery import Celery, chain
from celery.signals import worker_ready
from celery.schedules import crontab

# ---------------------------------------------------------------------------
# Celery + Redis setup
# ---------------------------------------------------------------------------
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

app = Celery("aion_tasks", broker=REDIS_URL)
app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    result_backend=REDIS_URL,
    beat_schedule={
        "health-check": {
            "task": "tasks.health_check_and_heal",
            "schedule": 60.0,
        },
        "monitor-scale": {
            "task": "tasks.monitor_and_scale",
            "schedule": 300.0,
        },
    },
)

r = redis.Redis.from_url(REDIS_URL, decode_responses=True)


def update_status(clone_id: str, status: str, **extra):
    """Persist clone status to Redis."""
    data = {"status": status, **extra}
    r.hset(f"clone:{clone_id}", mapping=data)


# ---------------------------------------------------------------------------
# Libvirt connection
# ---------------------------------------------------------------------------
def get_libvirt_conn():
    uri = os.getenv("LIBVIRT_URI", "qemu:///system")
    return libvirt.open(uri)


# ---------------------------------------------------------------------------
# CRAFT - generate app code
# ---------------------------------------------------------------------------
@app.task(bind=True, max_retries=2)
def craft_clone(self, clone_id: str, spec: dict):
    try:
        name = spec.get("name", "clone")
        desc = spec.get("description", "AION Core generated clone")
        prompt = spec.get("prompt", "")
        update_status(clone_id, "crafting", name=name)

        code = (
            "from fastapi import FastAPI, JSONResponse\n"
            "import urllib.parse\n\n"
            f'app = FastAPI(title="{name}", description="{desc}")\n\n'
            "@app.get('/')\n"
            "def root():\n"
            f'    return {{"message": "Welcome to {name}!", "description": "{desc}"}}\n\n'
            "@app.get('/health')\n"
            "def health():\n"
            '    return {"status": "ok"}\n\n'
            "@app.get('/thumbnail')\n"
            "def thumbnail():\n"
            f'    if "{prompt}":\n'
            f'        url = f"https://image.pollinations.ai/prompt/{{urllib.parse.quote(\'{prompt}\')}}?width=512&height=512&model=flux"\n'
            '        return JSONResponse({"image_url": url})\n'
            '    return {"error": "No prompt"}\n'
        )

        workdir = f"/tmp/clones/{clone_id}"
        os.makedirs(workdir, exist_ok=True)
        with open(f"{workdir}/main.py", "w") as f:
            f.write(code)
        with open(f"{workdir}/requirements.txt", "w") as f:
            f.write("fastapi\nuvicorn\nrequests\n")

        update_status(clone_id, "crafted", path=workdir)
        return {
            "clone_id": clone_id,
            "name": name,
            "path": workdir,
            "status": "crafted",
        }
    except Exception as e:
        update_status(clone_id, "craft_failed", error=str(e))
        self.retry(exc=e, countdown=30)


# ---------------------------------------------------------------------------
# BUILD - create VM disk image with cloud-init
# ---------------------------------------------------------------------------
@app.task(bind=True, max_retries=2)
def build_vm(self, craft_result: dict):
    clone_id = craft_result["clone_id"]
    path = craft_result["path"]
    try:
        update_status(clone_id, "building_image")
        spec = r.hgetall(f"clone:{clone_id}")
        name = spec.get("name", clone_id)

        # Read generated app code
        with open(f"{path}/main.py", "r") as f:
            main_code = f.read()
        with open(f"{path}/requirements.txt", "r") as f:
            reqs = f.read()

        # Build cloud-init user-data using write_files (no heredocs in f-strings)
        systemd_unit = (
            "[Unit]\n"
            "Description=Clone App\n"
            "After=network.target\n"
            "[Service]\n"
            "ExecStart=/usr/bin/uvicorn main:app --host 0.0.0.0 --port 8000\n"
            "WorkingDirectory=/opt/clone\n"
            "Restart=always\n"
            "[Install]\n"
            "WantedBy=multi-user.target\n"
        )

        # Indent content blocks for YAML literal block scalars
        indented_main = "\n".join("      " + line for line in main_code.splitlines())
        indented_reqs = "\n".join("      " + line for line in reqs.splitlines())
        indented_unit = "\n".join("      " + line for line in systemd_unit.splitlines())

        user_data = (
            "#cloud-config\n"
            "package_update: true\n"
            "packages:\n"
            "  - python3-pip\n"
            "write_files:\n"
            "  - path: /opt/clone/main.py\n"
            "    permissions: '0644'\n"
            f"    content: |\n{indented_main}\n"
            "  - path: /opt/clone/requirements.txt\n"
            "    permissions: '0644'\n"
            f"    content: |\n{indented_reqs}\n"
            "  - path: /etc/systemd/system/clone.service\n"
            "    permissions: '0644'\n"
            f"    content: |\n{indented_unit}\n"
            "runcmd:\n"
            "  - pip3 install -r /opt/clone/requirements.txt\n"
            "  - systemctl daemon-reload\n"
            "  - systemctl enable clone.service\n"
            "  - systemctl start clone.service\n"
        )

        meta_data = f"instance-id: {clone_id}\nlocal-hostname: {name}\n"

        # Create cloud-init ISO
        iso_dir = tempfile.mkdtemp(prefix="cloudinit_")
        with open(f"{iso_dir}/user-data", "w") as f:
            f.write(user_data)
        with open(f"{iso_dir}/meta-data", "w") as f:
            f.write(meta_data)

        iso_path = f"/tmp/{clone_id}-cidata.iso"
        subprocess.run(
            ["genisoimage", "-output", iso_path, "-volid", "cidata",
             "-joliet", "-rock", iso_dir],
            check=True,
            capture_output=True,
        )
        shutil.rmtree(iso_dir)

        # Copy base image
        base_image = os.getenv("BASE_VM_IMAGE", "/var/lib/libvirt/images/base.qcow2")
        if not os.path.exists(base_image):
            raise FileNotFoundError(f"Base image {base_image} not found")

        image_dir = "/var/lib/libvirt/images"
        os.makedirs(image_dir, exist_ok=True)
        image_path = f"{image_dir}/{clone_id}.qcow2"
        shutil.copy(base_image, image_path)

        disk_gb = int(spec.get("disk_gb", 10))
        subprocess.run(["qemu-img", "resize", image_path, f"{disk_gb}G"], check=True)

        update_status(clone_id, "image_built", image_path=image_path, iso_path=iso_path)
        return {
            "clone_id": clone_id,
            "image_path": image_path,
            "iso_path": iso_path,
            "status": "image_built",
        }
    except Exception as e:
        update_status(clone_id, "build_failed", error=str(e))
        self.retry(exc=e, countdown=60)


# ---------------------------------------------------------------------------
# DEPLOY - launch VM with cloud-init ISO
# ---------------------------------------------------------------------------
@app.task(bind=True, max_retries=2)
def deploy_vm(self, build_result: dict):
    clone_id = build_result["clone_id"]
    image_path = build_result["image_path"]
    iso_path = build_result["iso_path"]
    try:
        update_status(clone_id, "deploying_vm")
        conn = get_libvirt_conn()
        spec = r.hgetall(f"clone:{clone_id}")
        name = spec.get("name", clone_id)
        vcpus = int(spec.get("vcpus", 2))
        memory = int(spec.get("memory_mb", 2048))

        xml = f"""<domain type='kvm'>
  <name>{clone_id}</name>
  <memory unit='MiB'>{memory}</memory>
  <vcpu placement='static'>{vcpus}</vcpu>
  <os>
    <type arch='x86_64' machine='pc'>hvm</type>
    <boot dev='hd'/>
  </os>
  <features><acpi/></features>
  <devices>
    <disk type='file' device='disk'>
      <driver name='qemu' type='qcow2'/>
      <source file='{image_path}'/>
      <target dev='vda' bus='virtio'/>
    </disk>
    <disk type='file' device='cdrom'>
      <driver name='qemu' type='raw'/>
      <source file='{iso_path}'/>
      <target dev='hdc' bus='ide'/>
      <readonly/>
    </disk>
    <interface type='network'>
      <source network='default'/>
      <model type='virtio'/>
    </interface>
    <console type='pty'/>
  </devices>
</domain>"""

        domain = conn.defineXML(xml)
        domain.create()
        time.sleep(10)

        # Get IP via DHCP leases
        lease_cmd = ["virsh", "net-dhcp-leases", "default"]
        output = subprocess.check_output(lease_cmd, text=True)
        dom_xml = domain.XMLDesc()
        root = ET.fromstring(dom_xml)
        mac_elem = root.find(".//mac")
        mac = mac_elem.get("address") if mac_elem is not None else None

        ip = None
        if mac:
            for line in output.split("\n"):
                if mac in line:
                    parts = line.split()
                    if len(parts) >= 5:
                        ip = parts[4].split("/")[0]
                    break

        update_status(clone_id, "deployed", vm_id=domain.UUIDString(), ip=ip or "unknown")
        return {
            "clone_id": clone_id,
            "vm_id": domain.UUIDString(),
            "ip": ip or "unknown",
            "status": "deployed",
        }
    except Exception as e:
        update_status(clone_id, "deploy_failed", error=str(e))
        self.retry(exc=e, countdown=30)


# ---------------------------------------------------------------------------
# UPGRADE - hot/cold resource scaling
# ---------------------------------------------------------------------------
@app.task(bind=True, max_retries=2)
def upgrade_vm(self, clone_id: str, vcpus: int = None, memory_mb: int = None, disk_gb: int = None):
    try:
        update_status(clone_id, "upgrading")
        conn = get_libvirt_conn()
        domain = conn.lookupByName(clone_id)
        if not domain:
            raise ValueError(f"VM {clone_id} not found")

        was_active = domain.isActive()

        # Disk upgrade requires shutdown (cold)
        if disk_gb:
            if was_active:
                domain.shutdown()
                for _ in range(30):
                    if not domain.isActive():
                        break
                    time.sleep(1)
            xml = domain.XMLDesc()
            root = ET.fromstring(xml)
            disk_elem = root.find(".//disk[@device='disk']/source")
            if disk_elem is not None:
                disk_path = disk_elem.get("file")
                if disk_path:
                    subprocess.run(["qemu-img", "resize", disk_path, f"{disk_gb}G"], check=True)

        # CPU/memory hotplug if active, cold change if not
        if domain.isActive():
            if vcpus:
                domain.setVcpus(vcpus)
            if memory_mb:
                domain.setMemory(memory_mb * 1024)  # KiB
        else:
            xml = domain.XMLDesc()
            root = ET.fromstring(xml)
            if vcpus:
                vcpu_elem = root.find("vcpu")
                if vcpu_elem is not None:
                    vcpu_elem.text = str(vcpus)
                    vcpu_elem.set("placement", "static")
            if memory_mb:
                mem_elem = root.find("memory")
                if mem_elem is not None:
                    mem_elem.text = str(memory_mb)
                    mem_elem.set("unit", "MiB")
            new_xml = ET.tostring(root, encoding="unicode")
            conn.defineXML(new_xml)
            domain = conn.lookupByName(clone_id)
            domain.create()

        if vcpus:
            r.hset(f"clone:{clone_id}", "vcpus", str(vcpus))
        if memory_mb:
            r.hset(f"clone:{clone_id}", "memory_mb", str(memory_mb))
        if disk_gb:
            r.hset(f"clone:{clone_id}", "disk_gb", str(disk_gb))

        update_status(clone_id, "upgraded", vcpus=vcpus, memory_mb=memory_mb, disk_gb=disk_gb)
        return {"clone_id": clone_id, "status": "upgraded",
                "vcpus": vcpus, "memory_mb": memory_mb, "disk_gb": disk_gb}
    except Exception as e:
        update_status(clone_id, "upgrade_failed", error=str(e))
        self.retry(exc=e, countdown=30)


# ---------------------------------------------------------------------------
# PUBLISH to WordPress
# ---------------------------------------------------------------------------
def generate_clone_thumbnail(prompt: str) -> str:
    """Generate a thumbnail image URL via Pollinations."""
    encoded = urllib.parse.quote(prompt)
    return f"https://image.pollinations.ai/prompt/{encoded}?width=512&height=512&model=flux"


def upload_to_wp_media(image_url: str, name: str, wp_creds: dict) -> int:
    """Download image and upload to WordPress media library."""
    resp = requests.get(image_url, timeout=30)
    resp.raise_for_status()
    upload_url = f"{wp_creds['wp_url']}/wp-json/wp/v2/media"
    headers = {
        "Content-Disposition": f'attachment; filename="{name}.png"',
        "Content-Type": "image/png",
    }
    auth = (wp_creds["wp_user"], wp_creds["wp_pass"])
    upload_resp = requests.post(upload_url, headers=headers, auth=auth, data=resp.content)
    upload_resp.raise_for_status()
    return upload_resp.json().get("id")


@app.task(bind=True, max_retries=2)
def publish_clone_to_wp(self, deploy_result: dict, spec: dict):
    clone_id = deploy_result["clone_id"]
    try:
        update_status(clone_id, "publishing")
        wp_creds = {
            "wp_url": os.getenv("WP_URL", ""),
            "wp_user": os.getenv("WP_ADMIN_USER", ""),
            "wp_pass": os.getenv("WP_APP_PASSWORD", ""),
        }
        if not wp_creds["wp_url"]:
            update_status(clone_id, "published", warning="WP_URL not configured, skipping publish")
            return {"clone_id": clone_id, "status": "published", "warning": "no WP config"}

        prompt = spec.get("prompt", "")
        name = spec.get("name", clone_id)
        link = spec.get("link", "#")

        thumbnail_url = generate_clone_thumbnail(prompt) if prompt else ""
        media_id = None
        if thumbnail_url:
            media_id = upload_to_wp_media(thumbnail_url, name, wp_creds)

        clone_post = {
            "title": name,
            "content": spec.get("description", ""),
            "status": "publish",
            "meta": {
                "clone_id": clone_id,
                "clone_ip": deploy_result.get("ip", ""),
                "clone_link": link,
                "clone_thumbnail_id": media_id or "",
            },
        }
        post_url = f"{wp_creds['wp_url']}/wp-json/wp/v2/clones"
        auth = (wp_creds["wp_user"], wp_creds["wp_pass"])
        resp = requests.post(post_url, json=clone_post, auth=auth)
        resp.raise_for_status()

        update_status(clone_id, "published", wp_post_id=resp.json().get("id"))
        return {"clone_id": clone_id, "status": "published", "wp_post_id": resp.json().get("id")}
    except Exception as e:
        update_status(clone_id, "publish_failed", error=str(e))
        self.retry(exc=e, countdown=60)


# ---------------------------------------------------------------------------
# AUTONOMOUS SCALING
# ---------------------------------------------------------------------------
@app.task
def monitor_and_scale():
    """Check all managed VMs and hot-plug resources when load exceeds thresholds."""
    conn = get_libvirt_conn()
    scaled = []

    for dom in conn.listAllDomains():
        clone_id = dom.name()
        if not r.exists(f"clone:{clone_id}"):
            continue

        info = dom.info()
        # info: (state, max_mem_kb, mem_kb, nr_vcpu, cpu_time_ns)
        max_mem_mb = info[1] / 1024
        mem_used_mb = info[2] / 1024
        vcpus = info[3]

        mem_threshold = float(os.getenv("SCALE_MEM_THRESHOLD", "0.90"))

        if max_mem_mb > 0 and mem_used_mb > mem_threshold * max_mem_mb:
            new_mem = int(max_mem_mb * 1.5)
            upgrade_vm.delay(clone_id, memory_mb=new_mem)
            scaled.append({"clone_id": clone_id, "action": "memory_scaled",
                           "from_mb": int(max_mem_mb), "to_mb": new_mem})

    return {"scaled": scaled, "checked": conn.numOfDomains()}


# ---------------------------------------------------------------------------
# HEALTH CHECK
# ---------------------------------------------------------------------------
@app.task
def health_check_and_heal():
    """Ensure all managed VMs are running; restart if down."""
    conn = get_libvirt_conn()
    healed = []

    for dom in conn.listAllDomains():
        clone_id = dom.name()
        if not r.exists(f"clone:{clone_id}"):
            continue
        state = dom.state()[0]
        if state != libvirt.VIR_DOMAIN_RUNNING:
            dom.create()
            healed.append(clone_id)
            update_status(clone_id, "healed", previous_state=str(state))

    return {"healed": healed, "status": "ok"}


# ---------------------------------------------------------------------------
# FULL DEPLOYMENT CHAIN
# ---------------------------------------------------------------------------
@app.task
def full_clone_deployment(clone_id: str, spec: dict):
    """Chain: craft -> build -> deploy -> publish."""
    chain(
        craft_clone.s(clone_id, spec),
        build_vm.s(),
        deploy_vm.s(),
        publish_clone_to_wp.s(spec),
    ).apply_async()
    return {"clone_id": clone_id, "status": "chain_started"}
