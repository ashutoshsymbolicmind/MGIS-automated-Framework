from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Union, BinaryIO, Optional, Any
import os
from google.cloud import storage
from google.oauth2 import service_account
import logging
import json
import pickle

logger = logging.getLogger(__name__)

class StorageProvider(ABC):
    """Abstract base class for storage providers."""
    
    @abstractmethod
    def list_files(self, path: str, extension: Optional[str] = None) -> List[str]:
        """List all files in the specified path."""
        pass
    
    @abstractmethod
    def read_file(self, path: str) -> bytes:
        """Read file content as bytes."""
        pass
    
    @abstractmethod
    def write_file(self, path: str, content: Union[str, bytes, BinaryIO]) -> None:
        """Write content to file."""
        pass
    
    @abstractmethod
    def exists(self, path: str) -> bool:
        """Check if path exists."""
        pass

    def save_json(self, data: Any, filepath: str) -> None:
        """Save data as JSON."""
        content = json.dumps(data, indent=2, ensure_ascii=False)
        self.write_file(filepath, content)

    def load_json(self, filepath: str) -> Any:
        """Load JSON data."""
        content = self.read_file(filepath)
        return json.loads(content)

    def save_checkpoint(self, data: Any, filepath: str) -> None:
        """Save checkpoint data."""
        content = pickle.dumps(data)
        self.write_file(filepath, content)

    def load_checkpoint(self, filepath: str) -> Any:
        """Load checkpoint data."""
        if not self.exists(filepath):
            return None
        content = self.read_file(filepath)
        return pickle.loads(content)

class LocalStorageProvider(StorageProvider):
    """Implementation for local file system storage."""
    
    def list_files(self, path: str, extension: Optional[str] = None) -> List[str]:
        path = Path(path)
        if not path.exists():
            return []
            
        if extension:
            files = path.glob(f"*{extension}")
        else:
            files = path.glob("*")
            
        return [str(f) for f in files if f.is_file()]
    
    def read_file(self, path: str) -> bytes:
        with open(path, 'rb') as f:
            return f.read()
    
    def write_file(self, path: str, content: Union[str, bytes, BinaryIO]) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        mode = 'wb' if isinstance(content, bytes) else 'w'
        encoding = None if isinstance(content, bytes) else 'utf-8'
        
        with open(path, mode, encoding=encoding) as f:
            if isinstance(content, (str, bytes)):
                f.write(content)
            else:
                content.seek(0)
                f.write(content.read())
    
    def exists(self, path: str) -> bool:
        return Path(path).exists()

class GCPStorageProvider(StorageProvider):
    """Implementation for Google Cloud Storage."""
    
    def __init__(self, project_id: str, bucket_name: str, 
                 credentials_path: Optional[str] = None):
        self.project_id = project_id
        self.bucket_name = bucket_name
        
        if credentials_path:
            credentials = service_account.Credentials.from_service_account_file(
                credentials_path)
            self.client = storage.Client(
                credentials=credentials,
                project=project_id
            )
        else:
            self.client = storage.Client(project=project_id)
            
        self.bucket = self.client.bucket(bucket_name)
    
    def list_files(self, path: str, extension: Optional[str] = None) -> List[str]:
        blobs = self.client.list_blobs(
            self.bucket_name,
            prefix=path
        )
        
        files = []
        for blob in blobs:
            if extension:
                if blob.name.endswith(extension):
                    files.append(blob.name)
            else:
                files.append(blob.name)
                
        return files
    
    def read_file(self, path: str) -> bytes:
        blob = self.bucket.blob(path)
        return blob.download_as_bytes()
    
    def write_file(self, path: str, content: Union[str, bytes, BinaryIO]) -> None:
        blob = self.bucket.blob(path)
        
        if isinstance(content, str):
            blob.upload_from_string(content, content_type='text/plain')
        elif isinstance(content, bytes):
            blob.upload_from_string(content, content_type='application/octet-stream')
        else:
            content.seek(0)
            blob.upload_from_file(content)
    
    def exists(self, path: str) -> bool:
        blob = self.bucket.blob(path)
        return blob.exists()

class StorageFactory:
    """Factory for creating storage provider instances."""
    
    @staticmethod
    def create_provider(config: 'StorageConfig') -> StorageProvider:
        provider = config.provider.lower()
        
        if provider == 'local':
            return LocalStorageProvider()
        elif provider == 'gcp':
            if not config.project_id or not config.bucket_name:
                raise ValueError("GCP storage requires project_id and bucket_name")
            return GCPStorageProvider(
                project_id=config.project_id,
                bucket_name=config.bucket_name,
                credentials_path=config.credentials_path
            )
        else:
            raise ValueError(f"Unsupported storage provider: {provider}")