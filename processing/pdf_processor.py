import fitz
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Set, Union
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm
import logging
from num2words import num2words
from utils.storage import StorageProvider, StorageFactory

logger = logging.getLogger(__name__)

class ContentMasker:
    """Handles masking of sensitive information in text."""
    
    def __init__(self):
        self.company_names = ["Unum", "Hartford", "Lincoln"]
        
    def mask_sensitive_info(self, text: str) -> str:
        """Apply all masking rules to text."""
        text = re.sub(r'\b[\w\.-]+@[\w\.-]+\.\w+\b', '[EMAIL]', text)
        text = re.sub(r'\b(\+\d{1,2}\s?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b', '[PHONE]', text)
        text = re.sub(r'\b\d{3}-\d{2}-\d{4}\b', '[SSN]', text)
        text = re.sub(r'\b\d+\s+([A-Za-z0-9\s,.-]+\s+)(Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Court|Ct|Circle|Cir|Way|Parkway|Pkwy|Highway|Hwy|Suite|Ste|Unit|#)\.?\s*,?\s*([A-Za-z\s]+,\s*[A-Z]{2}\s*\d{5}(-\d{4})?)\b', '[ADDRESS]', text, flags=re.IGNORECASE)
        text = re.sub(r'\b\d{5}(-\d{4})?\b', '[ZIP]', text)
        text = re.sub(r'\b\d{5,10}\b', '[POLICY_NUMBER]', text)
        text = re.sub(r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4}\b', '[DATE]', text)
        text = re.sub(r'\b\d{1,2}/\d{1,2}/\d{2,4}\b', '[DATE]', text)
        text = re.sub(r'\b\d+\s*(day|week|month|year)s?\b', '[TIME_PERIOD]', text)
        
        for company in self.company_names:
            text = re.sub(rf'\b{company}\b', '[COMPANY_NAME]', text, flags=re.IGNORECASE)
        
        return text

class PDFProcessor:
    """Handles PDF processing and content extraction."""
    
    def __init__(self, config):
        self.config = config
        self.masker = ContentMasker()
        self.storage = StorageFactory.create_provider(config.storage)
        self.processed_files: Set[str] = set()
        self.combined_results = {}
        self.file_counter = 1
        
    def _generate_doc_id(self) -> str:
        """Generate a unique document ID."""
        doc_id = f"doc_{self.file_counter:03d}"
        self.file_counter += 1
        return doc_id

    def _convert_numbers_to_words(self, text: str) -> str:
        """Convert numeric values to words."""
        words = text.split()
        for i, word in enumerate(words):
            if word.isdigit():
                words[i] = num2words(int(word))
        return ' '.join(words)
        
    def _create_metadata(self, doc_id: str, page: int, line: int, 
                        selected_text: str, full_content: str) -> Dict[str, Any]:
        """Create metadata structure for masked content."""
        masked_selected_text = self.masker.mask_sensitive_info(selected_text)
        masked_full_content = self.masker.mask_sensitive_info(full_content)
        
        return {
            "source_file": doc_id,
            "location": {
                "page_number": self._convert_numbers_to_words(str(page)),
                "line_number": self._convert_numbers_to_words(str(line))
            },
            "content": {
                "selected_text": masked_selected_text,
                "full_extracted_part": masked_full_content
            },
            "extraction_timestamp": datetime.now().isoformat()
        }
        
    def _is_header(self, text: str, spans) -> bool:
        """Identify header sections."""
        if not text:
            return False
        return (text.isupper() or 
                text.rstrip().endswith(':') or
                spans[0].get('size', 0) > 12 or 
                spans[0].get('flags', 0) & 16)
                
    def _get_block_text(self, block: Dict) -> str:
        """Extract complete text from a block."""
        if "lines" not in block:
            return ""
            
        sentences = []
        current_sentence = []
        
        for line in block["lines"]:
            if not line.get("spans"):
                continue
                
            text = " ".join(span["text"] for span in line["spans"]).strip()
            if not text:
                continue
                
            current_sentence.append(text)
            
            if text.rstrip()[-1] in '.!?':
                sentences.append(" ".join(current_sentence))
                current_sentence = []
                
        if current_sentence:
            sentences.append(" ".join(current_sentence))
            
        return " ".join(sentences)

    def _find_keyword_context(self, blocks: List, keyword: str, 
                            current_block_idx: int) -> Optional[str]:
        """Find the complete context around a keyword match."""
        current_block = blocks[current_block_idx]
        current_text = self._get_block_text(current_block)

        if keyword not in current_text:
            return None
            
        content_parts = []
        
        if current_block_idx > 0:
            previous_text = self._get_block_text(blocks[current_block_idx - 1])
            if previous_text:
                content_parts.append(previous_text)
            
        content_parts.append(current_text)
        
        for i in range(1, 4):
            if current_block_idx + i < len(blocks):
                next_block_text = self._get_block_text(blocks[current_block_idx + i])
                if next_block_text:
                    content_parts.append(next_block_text)
                    if self._is_header(next_block_text.split('\n')[0], 
                                    blocks[current_block_idx + i].get("lines", [{}])[0].get("spans", [{}])):
                        break
            
        return " ".join(content_parts)

    def process_single_pdf(self, pdf_path: Union[str, Path]) -> Dict:
        """Process individual PDF file with masked data."""
        pdf_content = self.storage.read_file(str(pdf_path))
        doc = fitz.open(stream=pdf_content, filetype="pdf")
        findings = {}
        doc_id = self._generate_doc_id()
        
        try:
            for page_num, page in enumerate(doc, 1):
                blocks = page.get_text("dict")["blocks"]
                
                for block_num, block in enumerate(blocks):
                    if "lines" not in block:
                        continue
                    
                    for line_num, line in enumerate(block["lines"], 1):
                        if not line.get("spans"):
                            continue
                            
                        text = " ".join(span["text"] for span in line["spans"]).strip()
                        
                        for keyword in self.config.keywords:
                            full_context = self._find_keyword_context(blocks, keyword, block_num)
                            if full_context:
                                if keyword not in findings:
                                    findings[keyword] = []
                                    
                                findings[keyword].append(
                                    self._create_metadata(
                                        doc_id,
                                        page_num,
                                        line_num,
                                        text,
                                        full_context
                                    )
                                )
        finally:
            doc.close()
            
        if findings:
            self.combined_results[doc_id] = {
                'original_filename': str(Path(pdf_path).name),
                'findings': findings
            }
            logger.info(f"Processed: {Path(pdf_path).name} (ID: {doc_id})")
            for keyword, matches in findings.items():
                logger.info(f"Found '{keyword}' in {len(matches)} locations")
            
        return findings

    def process_directory(self, directory_path: str) -> Dict[str, Dict]:
        """Process all PDFs in a directory."""
        pdf_files = self.storage.list_files(directory_path, extension='.pdf')
        
        if not pdf_files:
            raise ValueError(f"No PDF files found in {directory_path}")
        
        pdf_files = sorted(pdf_files)
        
        with ThreadPoolExecutor(max_workers=self.config.processing.max_workers) as executor:
            future_to_path = {
                executor.submit(self.process_single_pdf, pdf_path): pdf_path
                for pdf_path in pdf_files
                if pdf_path not in self.processed_files
            }
            
            for future in tqdm(future_to_path, desc="Processing PDFs"):
                pdf_path = future_to_path[future]
                try:
                    future.result()
                    self.processed_files.add(pdf_path)
                except Exception as e:
                    logger.error(f"Error processing file {pdf_path}: {str(e)}")
        
        if self.combined_results:
            output_path = Path(self.config.output.base_folder) / \
                         self.config.output.subfolder_names['masked'] / \
                         "combined_masked.json"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            self.storage.save_json(self.combined_results, str(output_path))
            logger.info(f"Saved combined results to {output_path}")
            
        return self.combined_results

    def get_processed_files(self) -> Set[str]:
        """Return set of processed file paths."""
        return self.processed_files