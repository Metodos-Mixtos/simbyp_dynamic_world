"""
Secrets management module for Dynamic World pipeline.

Supports three loading strategies in order (same as GFW):
1. Environment variables (Cloud Run or pre-injected) - FASTEST
2. .env file (local development)
3. Google Cloud Secret Manager (fallback with API calls)
"""

import os
from pathlib import Path
from typing import Dict, List, Tuple


# Required secrets for the pipeline (only truly sensitive data)
REQUIRED_SECRETS = [
    "GCP_PROJECT",
    "EE_SERVICE_ACCOUNT_KEY",
]


def _check_env_vars() -> Tuple[bool, Dict[str, str], List[str]]:
    """
    Check if all required secrets are available in environment variables.
    
    Returns:
        Tuple of (all_found: bool, secrets_dict: dict, missing_vars: list)
    """
    secrets = {}
    missing = []
    
    for secret_id in REQUIRED_SECRETS:
        value = os.getenv(secret_id)
        if value:
            secrets[secret_id] = value
        else:
            missing.append(secret_id)
    
    # EE_SERVICE_ACCOUNT_KEY might be in GOOGLE_APPLICATION_CREDENTIALS for local dev
    if "EE_SERVICE_ACCOUNT_KEY" not in secrets:
        creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if creds:
            secrets["EE_SERVICE_ACCOUNT_KEY"] = creds
    
    return len(missing) == 0, secrets, missing


def _load_dotenv_file() -> Tuple[bool, Dict[str, str], str]:
    """
    Try to load secrets from .env file.
    
    Returns:
        Tuple of (success: bool, secrets_dict: dict, error_message: str)
    """
    env_path = Path(__file__).parent.parent / ".env"
    
    if not env_path.exists():
        return False, {}, f".env file not found at {env_path}"
    
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path)
        
        secrets = {}
        for secret_id in REQUIRED_SECRETS:
            value = os.getenv(secret_id)
            if value:
                secrets[secret_id] = value
        
        # EE_SERVICE_ACCOUNT_KEY might be in GOOGLE_APPLICATION_CREDENTIALS for local dev
        if "EE_SERVICE_ACCOUNT_KEY" not in secrets:
            creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            if creds:
                secrets["EE_SERVICE_ACCOUNT_KEY"] = creds
        
        if len(secrets) >= len(REQUIRED_SECRETS):
            return True, secrets, ""
        else:
            missing = [s for s in REQUIRED_SECRETS if s not in secrets]
            return False, secrets, f"Incomplete .env file, missing: {', '.join(missing)}"
    
    except Exception as e:
        return False, {}, f"Error reading .env file: {str(e)}"


def _load_secret_manager(project_id: str) -> Tuple[bool, Dict[str, str], str]:
    """
    Try to load secrets from Google Cloud Secret Manager.
    
    Args:
        project_id: GCP project ID
    
    Returns:
        Tuple of (success: bool, secrets_dict: dict, error_message: str)
    """
    try:
        from google.cloud import secretmanager
    except ImportError:
        return False, {}, "google-cloud-secret-manager not installed"
    
    try:
        client = secretmanager.SecretManagerServiceClient()
        secrets = {}
        
        for secret_id in REQUIRED_SECRETS:
            try:
                name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
                response = client.access_secret_version(request={"name": name})
                secrets[secret_id] = response.payload.data.decode("UTF-8")
            except Exception as e:
                return False, {}, f"Failed to access secret '{secret_id}': {str(e)}"
        
        return True, secrets, ""
    
    except Exception as e:
        return False, {}, f"Secret Manager error: {str(e)}"


def load_secrets(project_id: str = "bosques-bogota-416214") -> Dict[str, str]:
    """
    Load secrets using a three-tier fallback strategy (same as GFW).
    
    Only loads truly sensitive data:
    - GCP_PROJECT
    - EE_SERVICE_ACCOUNT_KEY
    
    Strategy (in order):
    1. Environment variables (Cloud Run or pre-injected) - FASTEST
    2. .env file (local development)
    3. Google Cloud Secret Manager (local dev with enhanced security)
    
    Args:
        project_id: GCP project ID (for Secret Manager access)
    
    Returns:
        Dictionary with all required secrets
    
    Raises:
        ValueError: If secrets cannot be loaded from any source
    """
    print("\n🔐 === Secrets Management (Dynamic World) ===")
    
    # Strategy 1: Environment Variables (FASTEST - Cloud Run mounts secrets here)
    print("\n1️⃣  Trying environment variables...")
    env_complete, env_secrets, env_missing = _check_env_vars()
    
    if env_complete:
        print(f"   ✅ Loaded all {len(REQUIRED_SECRETS)} secrets from environment variables")
        print("   📍 Source: Cloud Run / Pre-injected environment")
        return env_secrets
    else:
        if env_secrets:
            print(f"   ⚠️  Partial environment variables (found {len(env_secrets)}/{len(REQUIRED_SECRETS)})")
            print(f"   ⏭️  Missing: {', '.join(env_missing)}")
        else:
            print(f"   ❌ No environment variables found")
    
    # Strategy 2: .env File (Local Development)
    print("\n2️⃣  Trying .env file...")
    dotenv_success, dotenv_secrets, dotenv_error = _load_dotenv_file()
    
    if dotenv_success:
        print(f"   ✅ Loaded all {len(REQUIRED_SECRETS)} secrets from .env file")
        env_path = Path(__file__).parent.parent / ".env"
        print(f"   📍 Source: {env_path}")
        return dotenv_secrets
    else:
        print(f"   ❌ {dotenv_error}")
    
    # Strategy 3: Google Cloud Secret Manager (Fallback)
    print("\n3️⃣  Trying Google Cloud Secret Manager...")
    print(f"   📍 Project: {project_id}")
    
    sm_success, sm_secrets, sm_error = _load_secret_manager(project_id)
    
    if sm_success:
        print(f"   ✅ Loaded all {len(REQUIRED_SECRETS)} secrets from Secret Manager")
        return sm_secrets
    else:
        print(f"   ❌ {sm_error}")
    
    # All strategies failed
    print("\n" + "="*70)
    print("❌ FATAL: Could not load secrets from any source")
    print("="*70)
    
    raise ValueError(
        "No se pudieron cargar los secrets. "
        "Configura: (1) variables de entorno, (2) archivo .env, o (3) Secret Manager"
    )
