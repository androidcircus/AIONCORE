#!/usr/bin/env python3
"""
AION Core - Deployment Script
Deploys all 15 clones via the orchestrator API.
"""
import os
import sys
import time
import getpass

import requests

ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://localhost:8000")
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASSWORD") or getpass.getpass("Enter admin password: ")

if not ADMIN_PASS:
    sys.exit("Password required")

# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------
try:
    login_resp = requests.post(
        f"{ORCHESTRATOR_URL}/api/login",
        json={"username": ADMIN_USER, "password": ADMIN_PASS},
        timeout=10,
    )
    login_resp.raise_for_status()
    token = login_resp.json()["access_token"]
except requests.RequestException as e:
    sys.exit(f"Login failed: {e}")

headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json",
}

# ---------------------------------------------------------------------------
# Check existing clones
# ---------------------------------------------------------------------------
try:
    existing = requests.get(
        f"{ORCHESTRATOR_URL}/api/clones", headers=headers, timeout=10
    ).json()
    existing_names = [c.get("name") for c in existing]
except Exception:
    existing_names = []

# ---------------------------------------------------------------------------
# All 15 clones with VM resource specs
# ---------------------------------------------------------------------------
CLONES = [
    {
        "name": "Notewave",
        "description": "AI notepad for meetings",
        "prompt": "A futuristic, glowing waveform shaped like a fountain pen, dark background, electric blue and neon purple.",
        "link": "#",
        "vcpus": 2, "memory_mb": 2048, "disk_gb": 10,
    },
    {
        "name": "AdVivid",
        "description": "AI video ad generator",
        "prompt": "A vibrant, abstract explosion of color shaped like a play button, cyberpunk palette, neon pink and cyan.",
        "link": "#",
        "vcpus": 2, "memory_mb": 2048, "disk_gb": 10,
    },
    {
        "name": "ScribeBridge",
        "description": "Chrome extension for notebook exports",
        "prompt": "A stylized bridge made of glowing data streams connecting a notebook to a cloud, tech-blue and white.",
        "link": "#",
        "vcpus": 2, "memory_mb": 2048, "disk_gb": 10,
    },
    {
        "name": "Autonomo",
        "description": "AI agent builder",
        "prompt": "A geometric, robotic eye, metallic gold and dark steel, futuristic.",
        "link": "#",
        "vcpus": 2, "memory_mb": 2048, "disk_gb": 10,
    },
    {
        "name": "CaptureCraft",
        "description": "UI screenshot capture",
        "prompt": "A perfect, digital square with a stylized camera lens, soft gradients, UI/UX design.",
        "link": "#",
        "vcpus": 2, "memory_mb": 2048, "disk_gb": 10,
    },
    {
        "name": "FusionGate",
        "description": "OpenRouter-style aggregator",
        "prompt": "An interdimensional, glowing portal made of interconnected nodes, cosmic purple and teal.",
        "link": "#",
        "vcpus": 2, "memory_mb": 2048, "disk_gb": 10,
    },
    {
        "name": "RouteMind",
        "description": "LLM router",
        "prompt": "A stylized, glowing brain with branching neon pathways, green and blue matrix.",
        "link": "#",
        "vcpus": 2, "memory_mb": 2048, "disk_gb": 10,
    },
    {
        "name": "ZeroLink",
        "description": "Zero-cost LLM router",
        "prompt": "A minimalist, glowing zero symbol with a chain link inside, bright green and black.",
        "link": "#",
        "vcpus": 2, "memory_mb": 2048, "disk_gb": 10,
    },
    {
        "name": "ClipForge",
        "description": "Short-video generator",
        "prompt": "An anvil with a spark of energy striking it, orange and dark industrial.",
        "link": "#",
        "vcpus": 2, "memory_mb": 2048, "disk_gb": 10,
    },
    {
        "name": "VidCraft",
        "description": "Automated YouTube shorts",
        "prompt": "A stylized film reel transforming into a rocket, gold and deep red.",
        "link": "#",
        "vcpus": 2, "memory_mb": 2048, "disk_gb": 10,
    },
    {
        "name": "Lumina",
        "description": "Open-source GLM inference",
        "prompt": "A glowing, central core of light with rings of data orbiting it, bright ethereal gold and white.",
        "link": "#",
        "vcpus": 4, "memory_mb": 4096, "disk_gb": 20,
    },
    {
        "name": "CodeForge",
        "description": "OpenCode coding agent",
        "prompt": "A glowing, stylized hammer and code brackets, neon blue and dark slate.",
        "link": "#",
        "vcpus": 2, "memory_mb": 2048, "disk_gb": 10,
    },
    {
        "name": "Piece Logic Copy",
        "description": "A tool for logic-based copy and content generation.",
        "prompt": "A digital logic board with glowing connections, cyberpunk style, neon blue and purple, futuristic interface.",
        "link": "https://piece-logic-copy-c0882f22.base44.app",
        "vcpus": 2, "memory_mb": 2048, "disk_gb": 10,
    },
    {
        "name": "Manifest AI",
        "description": "Transform your stories into cinematic long-form videos with AI-powered scene generation, memory-linked continuity, and professional editing tools.",
        "prompt": "A cinematic film reel transforming into glowing AI neural networks, cyberpunk style, neon blue and purple, dark background, professional video editing vibe.",
        "link": "https://manifest-video-flow.base44.app",
        "vcpus": 4, "memory_mb": 4096, "disk_gb": 20,
    },
    {
        "name": "AuraVision (Copy)",
        "description": "Discover and visualize the hidden energy frequencies around you. AuraVision uses your device's camera and microphone to provide a mesmerizing, real-time interpretation of a person's aura and energetic vibrations.",
        "prompt": "A glowing human aura with vibrant colorful energy waves, cyberpunk style, dark background, mystical energy visualization.",
        "link": "https://aura-vision-copy-6da627db.base44.app",
        "vcpus": 2, "memory_mb": 2048, "disk_gb": 10,
    },
]

# ---------------------------------------------------------------------------
# Deploy
# ---------------------------------------------------------------------------
print(f"\nAION Core - Deploying {len(CLONES)} clones to {ORCHESTRATOR_URL}\n")
queued = 0
skipped = 0
failed = 0

for clone in CLONES:
    if clone["name"] in existing_names:
        print(f"  SKIP  {clone['name']} (already exists)")
        skipped += 1
        continue

    payload = {"command": "deploy_clone", "params": clone}
    try:
        resp = requests.post(
            f"{ORCHESTRATOR_URL}/api/command",
            json=payload,
            headers=headers,
            timeout=10,
        )
        if resp.ok:
            data = resp.json()
            print(f"  OK    {clone['name']:<25} clone_id={data.get('clone_id')}")
            queued += 1
        else:
            print(f"  FAIL  {clone['name']}: {resp.text}")
            failed += 1
    except Exception as e:
        print(f"  FAIL  {clone['name']}: {e}")
        failed += 1

    time.sleep(0.5)

print(f"\nDone. Queued: {queued}  Skipped: {skipped}  Failed: {failed}")
