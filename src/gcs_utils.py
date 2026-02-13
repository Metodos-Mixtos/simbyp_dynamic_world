#!/usr/bin/env python3
"""Utilidades para manejo de Google Cloud Storage"""
import os
import base64
from pathlib import Path
from google.cloud import storage
from src.aux_utils import log

def get_storage_client():
    """Inicializa y retorna cliente de GCS"""
    return storage.Client()

def upload_file_to_gcs(local_path, bucket_name, blob_name):
    """
    Sube un archivo local a GCS
    
    Args:
        local_path: Ruta del archivo local
        bucket_name: Nombre del bucket (sin gs://)
        blob_name: Ruta dentro del bucket (ej: "2025_1/paramo_sumapaz/mapas/mapa.html")
    
    Returns:
        str: URL pública del archivo o ruta gs://
    """
    try:
        client = get_storage_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        
        blob.upload_from_filename(local_path)
        
        gcs_path = f"gs://{bucket_name}/{blob_name}"
        log(f"✓ Subido: {os.path.basename(local_path)} → {gcs_path}", "success")
        return gcs_path
    except Exception as e:
        log(f"✗ Error al subir {local_path}: {str(e)}", "error")
        raise

def upload_directory_to_gcs(local_dir, bucket_name, gcs_prefix):
    """
    Sube un directorio completo a GCS manteniendo la estructura
    
    Args:
        local_dir: Directorio local a subir
        bucket_name: Nombre del bucket
        gcs_prefix: Prefijo en GCS (ej: "2025_1/paramo_sumapaz")
    
    Returns:
        dict: Mapeo de archivos locales a rutas GCS
    """
    uploaded_files = {}
    local_path = Path(local_dir)
    
    if not local_path.exists():
        log(f"⚠ Directorio no existe: {local_dir}", "warning")
        return uploaded_files
    
    for file_path in local_path.rglob("*"):
        if file_path.is_file():
            # Calcular ruta relativa
            rel_path = file_path.relative_to(local_path)
            blob_name = f"{gcs_prefix}/{rel_path}".replace("\\", "/")
            
            gcs_path = upload_file_to_gcs(str(file_path), bucket_name, blob_name)
            uploaded_files[str(file_path)] = gcs_path
    
    return uploaded_files

def check_blob_exists(bucket_name, blob_name):
    """Verifica si un blob existe en GCS"""
    try:
        client = get_storage_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        return blob.exists()
    except Exception as e:
        log(f"Error al verificar blob: {str(e)}", "error")
        return False

def make_blob_public(bucket_name, blob_name):
    """Hace público un blob en GCS"""
    try:
        client = get_storage_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.make_public()
        return blob.public_url
    except Exception as e:
        log(f"Error al hacer público el blob: {str(e)}", "error")
        return None

def get_public_url(bucket_name, blob_name):
    """Obtiene URL pública de un blob (sin hacer autenticación)"""
    return f"https://storage.googleapis.com/{bucket_name}/{blob_name}"

def image_to_base64(image_path):
    """
    Convierte una imagen (local o GCS) a base64 data URI
    
    Args:
        image_path: Ruta local o gs:// para GCS
    
    Returns:
        str: Data URI en formato data:image/png;base64,...
    """
    try:
        if image_path.startswith("gs://"):
            # Leer desde GCS
            path_parts = image_path.replace("gs://", "").split("/", 1)
            bucket_name = path_parts[0]
            blob_name = path_parts[1]
            
            client = get_storage_client()
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(blob_name)
            
            image_bytes = blob.download_as_bytes()
        else:
            # Leer desde archivo local
            with open(image_path, "rb") as f:
                image_bytes = f.read()
        
        # Detectar tipo de imagen por extensión
        ext = Path(image_path).suffix.lower()
        mime_type = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".svg": "image/svg+xml"
        }.get(ext, "image/png")
        
        # Convertir a base64
        base64_data = base64.b64encode(image_bytes).decode("utf-8")
        return f"data:{mime_type};base64,{base64_data}"
    
    except Exception as e:
        log(f"Error al convertir imagen a base64: {str(e)}", "error")
        return ""
