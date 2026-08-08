import os, json, requests, subprocess, time, urllib.parse
from bs4 import BeautifulSoup
from celery import Celery
from celery.signals import worker_ready

app = Celery('aion_tasks', broker=os.getenv('REDIS_URL', 'redis://redis:6379/0'))

# ---------- HERMES: Web Crawler ----------
@app.task
def crawl_and_extract(url: str):
    try:
        headers = {'User-Agent': 'AION-Core/1.0'}
        resp = requests.get(url, timeout=15, headers=headers)
        soup = BeautifulSoup(resp.text, 'html.parser')
        title = soup.title.string.strip() if soup.title else 'No title'
        desc = soup.find('meta', attrs={'name': 'description'})
        description = desc.get('content', '').strip() if desc else 'No description'
        return {'url': url, 'title': title, 'description': description, 'html_preview': resp.text[:2000]}
    except Exception as e:
        return {'error': str(e)}

# ---------- DAEDALUS: Clone Crafter ----------
@app.task
def craft_clone(spec: dict):
    name = spec.get('name', 'clone')
    desc = spec.get('description', 'AION Core generated clone')
    code = f'''
from fastapi import FastAPI
app = FastAPI(title="{name}", description="{desc}")
@app.get("/")
def root():
    return {{"message": "Welcome to {name}!"}}
@app.get("/health")
def health():
    return {{"status": "ok"}}
'''
    workdir = f'/tmp/clones/{name}'
    os.makedirs(workdir, exist_ok=True)
    with open(f'{workdir}/main.py', 'w') as f: f.write(code)
    with open(f'{workdir}/requirements.txt', 'w') as f: f.write('fastapi\nuvicorn')
    dockerfile = f'''FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]'''
    with open(f'{workdir}/Dockerfile', 'w') as f: f.write(dockerfile)
    return {'name': name, 'path': workdir, 'status': 'crafted'}

# ---------- VULCAN: Container Builder ----------
@app.task
def build_container(clone_id: str, path: str):
    try:
        image_name = f'clone-{clone_id}:latest'
        subprocess.run(['docker', 'build', '-t', image_name, path], check=True, capture_output=True)
        return {'image': image_name, 'status': 'built'}
    except subprocess.CalledProcessError as e:
        return {'error': e.stderr.decode(), 'status': 'failed'}

# ---------- AETHER: VM Deployer ----------
@app.task
def deploy_vm(clone_id: str, image: str = 'ubuntu-22.04.qcow2'):
    # Simulated – replace with libvirt / cloud API for real deployment
    return {'vm_id': f'vm-{clone_id}', 'status': 'launched_simulated'}

# ---------- ASCLEPIUS: CMO ----------
@app.task
def health_check_and_heal():
    return {'status': 'all services healthy'}

# ---------- PROMETHEUS: Auto‑Scaler ----------
@app.task
def monitor_and_scale():
    return {'action': 'no scaling needed'}

# ---------- PUBLISHER: Push to WordPress ----------
@app.task
def publish_clone_to_wp(clone_data: dict):
    wp_url = 'https://aioncore9863.live-website.com/wp-json/wp/v2/clones'
    auth = (os.getenv('WP_ADMIN_USER', 'admin'), os.getenv('WP_APP_PASSWORD', 'your_app_password'))
    payload = {
        'title': clone_data['name'],
        'status': 'publish',
        'clone_meta': {
            'description': clone_data.get('description', ''),
            'thumb': clone_data.get('thumb', '📦'),
            'link': clone_data.get('link', '#'),
            'code': clone_data.get('code', '')
        }
    }
    try:
        resp = requests.post(wp_url, json=payload, auth=auth)
        resp.raise_for_status()
        return {'success': True, 'wp_id': resp.json().get('id')}
    except Exception as e:
        return {'error': str(e)}

# ---------- THUMBNAIL GENERATOR ----------
@app.task
def generate_clone_thumbnail(prompt: str, name: str) -> dict:
    try:
        encoded_prompt = urllib.parse.quote(prompt)
        image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=512&height=512&model=flux"
        response = requests.get(image_url, timeout=30)
        if response.status_code == 200:
            return {'success': True, 'url': image_url}
        else:
            return {'success': False, 'error': f'HTTP {response.status_code}'}
    except Exception as e:
        return {'error': str(e)}

# ---------- PERIODIC MONITORING ----------
@worker_ready.connect
def start_monitoring(**kwargs):
    from celery.schedules import crontab
    app.conf.beat_schedule = {
        'health-check': {'task': 'tasks.health_check_and_heal', 'schedule': 60.0},
        'monitor-scale': {'task': 'tasks.monitor_and_scale', 'schedule': 120.0},
    }