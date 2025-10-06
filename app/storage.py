# app/storage.py
"""
Cloudflare R2 Storage für PDFs
"""
import os
import uuid
import boto3
from botocore.exceptions import ClientError
from botocore.config import Config
import logging

log = logging.getLogger("uvicorn")

# R2 Configuration
R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID", "")
R2_ACCESS_KEY = os.getenv("R2_ACCESS_KEY", "")
R2_SECRET_KEY = os.getenv("R2_SECRET_KEY", "")
R2_BUCKET = os.getenv("R2_BUCKET", "kindergeld-pdfs")
R2_ENDPOINT = os.getenv("R2_ENDPOINT", "")  # https://abc123.r2.cloudflarestorage.com

# TTL für Pre-Signed URLs (in Sekunden)
PRESIGNED_URL_TTL = int(os.getenv("PDF_URL_TTL_HOURS", "24")) * 3600  # 24h default


def _get_client():
    """Erstellt boto3 S3 Client für R2."""
    if not all([R2_ACCESS_KEY, R2_SECRET_KEY, R2_ENDPOINT]):
        log.warning("R2 credentials missing - storage disabled")
        return None
    
    try:
        client = boto3.client(
            's3',
            endpoint_url=R2_ENDPOINT,
            aws_access_key_id=R2_ACCESS_KEY,
            aws_secret_access_key=R2_SECRET_KEY,
            config=Config(
                signature_version='s3v4',
                retries={'max_attempts': 3, 'mode': 'adaptive'}
            )
        )
        return client
    except Exception as e:
        log.error(f"R2 client creation failed: {e}")
        return None


def upload_pdf(pdf_bytes: bytes, filename: str = None) -> tuple[bool, str]:
    """
    Lädt PDF zu R2 hoch und gibt URL zurück.
    
    Args:
        pdf_bytes: PDF als Bytes
        filename: Optional custom filename
        
    Returns:
        (success, url_or_error_message)
    """
    client = _get_client()
    if not client:
        return False, "R2 storage not configured"
    
    # Eindeutiger Filename
    if not filename:
        filename = f"kg-{uuid.uuid4().hex}.pdf"
    
    # Key (Pfad in Bucket)
    key = f"pdfs/{filename}"
    
    try:
        # Upload
        client.put_object(
            Bucket=R2_BUCKET,
            Key=key,
            Body=pdf_bytes,
            ContentType='application/pdf',
            Metadata={
                'uploaded_by': 'kindergeld-bot',
                'version': '1.0'
            }
        )
        
        # Pre-Signed URL generieren (zeitlich begrenzt)
        url = client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': R2_BUCKET,
                'Key': key
            },
            ExpiresIn=PRESIGNED_URL_TTL
        )
        
        log.info(f"PDF uploaded to R2: {key}")
        return True, url
        
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        log.error(f"R2 upload failed: {error_code} - {e}")
        return False, f"Upload failed: {error_code}"
    except Exception as e:
        log.error(f"R2 upload exception: {e}")
        return False, f"Upload error: {str(e)}"


def delete_pdf(url: str) -> bool:
    """
    Löscht PDF aus R2 (optional, für Cleanup).
    
    Args:
        url: Die URL oder der Key
        
    Returns:
        True wenn erfolgreich gelöscht
    """
    client = _get_client()
    if not client:
        return False
    
    # Extract key from URL
    try:
        # URL format: https://...?X-Amz-Credential=...&key=pdfs/xyz.pdf
        # Oder direkt key übergeben
        if url.startswith("http"):
            # Parse key aus URL (vereinfacht)
            key = url.split("?")[0].split(R2_ENDPOINT)[-1].strip("/")
        else:
            key = url
        
        client.delete_object(Bucket=R2_BUCKET, Key=key)
        log.info(f"PDF deleted from R2: {key}")
        return True
        
    except Exception as e:
        log.error(f"R2 delete failed: {e}")
        return False


def health_check() -> dict:
    """
    Prüft R2-Verbindung.
    
    Returns:
        Status dict
    """
    client = _get_client()
    if not client:
        return {
            "status": "disabled",
            "configured": False,
            "message": "R2 credentials missing"
        }
    
    try:
        # List buckets als Health Check
        response = client.head_bucket(Bucket=R2_BUCKET)
        return {
            "status": "healthy",
            "configured": True,
            "bucket": R2_BUCKET,
            "endpoint": R2_ENDPOINT
        }
    except ClientError as e:
        return {
            "status": "unhealthy",
            "configured": True,
            "error": str(e)
        }
    except Exception as e:
        return {
            "status": "error",
            "configured": True,
            "error": str(e)
        }


# Fallback zu lokalem Storage
def upload_pdf_with_fallback(pdf_bytes: bytes, filename: str = None) -> tuple[bool, str]:
    """
    Versucht R2 Upload, fällt zurück auf lokales /tmp bei Fehler.
    
    Returns:
        (success, url)
    """
    from pathlib import Path
    
    # Versuch R2
    success, result = upload_pdf(pdf_bytes, filename)
    if success:
        return True, result
    
    # Fallback: Lokal speichern
    log.warning("R2 upload failed, using local fallback")
    
    ART_DIR = Path("/tmp/artifacts")
    ART_DIR.mkdir(exist_ok=True)
    
    if not filename:
        filename = f"kg-{uuid.uuid4().hex}.pdf"
    
    local_path = ART_DIR / filename
    local_path.write_bytes(pdf_bytes)
    
    # Lokale URL (funktioniert nur während Service läuft)
    base_url = os.getenv("APP_BASE_URL", "").rstrip("/")
    if not base_url.startswith("http"):
        base_url = "https://" + base_url
    
    local_url = f"{base_url}/artifact/{filename}"
    return True, local_url
