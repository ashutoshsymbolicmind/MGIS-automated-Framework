from pathlib import Path
from typing import Dict, List, Optional, Union, Any
from dataclasses import dataclass
import yaml
import logging

logger = logging.getLogger(__name__)

@dataclass
class StorageConfig:
    provider: str
    project_id: Optional[str] = None
    bucket_name: Optional[str] = None
    credentials_path: Optional[str] = None
    connection_string: Optional[str] = None
    container_name: Optional[str] = None
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    region: Optional[str] = None

@dataclass
class InputConfig:
    file_extensions: List[str]

@dataclass
class OutputConfig:
    base_folder: str
    subfolder_names: Dict[str, str]

@dataclass
class ProcessingConfig:
    augmentation_factor: int
    parallel_prompts: bool
    max_workers: int
    checkpointing: bool = True
    checkpoint_file: str = "processing_checkpoint.pkl"

@dataclass
class OllamaConfig:
    model_name: str
    base_url: str
    temperature: float
    timeout: int
    retries: int
    retry_delay: int

class ConfigurationManager:
    def __init__(self, config_path: Union[str, Path]):
        """Initialize configuration manager with path to config file."""
        self.config_path = Path(config_path)
        self.config = self._load_config()
        
        self.storage = self._init_storage_config()
        self.input = self._init_input_config()
        self.output = self._init_output_config()
        self.processing = self._init_processing_config()
        self.ollama = self._init_ollama_config()
        self.keywords = self.config.get('keywords', [])
        self.prompts = self.config.get('prompts', {})

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        try:
            with open(self.config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
            raise

    def _init_storage_config(self) -> StorageConfig:
        """Initialize storage configuration."""
        storage_config = self.config.get('storage', {})
        return StorageConfig(**storage_config)

    def _init_input_config(self) -> InputConfig:
        """Initialize input configuration."""
        input_config = self.config.get('input', {})
        file_extensions = input_config.get('file_extensions', [])
        return InputConfig(file_extensions=file_extensions)

    def _init_output_config(self) -> OutputConfig:
        """Initialize output configuration."""
        output_config = self.config.get('output', {})
        return OutputConfig(
            base_folder=output_config.get('base_folder', 'processed_outputs'),
            subfolder_names=output_config.get('subfolder_names', {
                'masked': 'masked_content',
                'qa': 'qa_outputs'
            })
        )

    def _init_processing_config(self) -> ProcessingConfig:
        """Initialize processing configuration."""
        processing_config = self.config.get('processing', {})
        return ProcessingConfig(**processing_config)

    def _init_ollama_config(self) -> OllamaConfig:
        """Initialize Ollama configuration."""
        ollama_config = self.config.get('ollama', {})
        return OllamaConfig(**ollama_config)

    def get_prompt_template(self, template_name: str = 'default') -> str:
        """Get prompt template by name."""
        return self.prompts.get(template_name, self.prompts.get('default', ''))

    def validate(self) -> bool:
        """Validate configuration completeness and correctness."""
        try:
            if not self.keywords:
                raise ValueError("No keywords defined in configuration")
            
            if not self.prompts.get('default'):
                raise ValueError("Default prompt template is required")
            
            if self.storage.provider not in ['local', 'gcp']:
                raise ValueError(f"Unsupported storage provider: {self.storage.provider}")
            
            if self.storage.provider == 'gcp':
                if not self.storage.project_id or not self.storage.bucket_name:
                    raise ValueError("GCP storage requires project_id and bucket_name")
            
            return True
            
        except Exception as e:
            logger.error(f"Configuration validation failed: {e}")
            return False