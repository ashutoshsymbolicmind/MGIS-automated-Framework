import requests
import json
import time
from pathlib import Path
from typing import Dict, List, Any, Optional, Set, Union, Literal
from datetime import datetime
import logging
from tqdm import tqdm
from copy import deepcopy

logger = logging.getLogger(__name__)

PromptType = Literal['default', 'alternative']

import requests
import json
import time
from pathlib import Path
from typing import Dict, List, Any, Optional, Set, Union, Literal
from datetime import datetime
import logging
from tqdm import tqdm
from copy import deepcopy

logger = logging.getLogger(__name__)

PromptType = Literal['default', 'alternative']

class QAOutputManager:
    """Manages QA outputs for different prompt types."""
    
    def __init__(self, config, prompt_type: PromptType):
        self.config = config
        self.prompt_type = prompt_type
        self.qa_text = {}
        self.qa_json = {}
        self.doc_stats = {} 
        
    def get_output_dir(self) -> Path:
        """Get output directory for current prompt type."""
        return (Path(self.config.output.base_folder) / 
                self.config.output.subfolder_names['qa'] /
                self.config.output.subfolder_names[f'{self.prompt_type}_prompt'])

    def count_text_stats(self, text: str) -> Dict[str, int]:
        """Count words and characters in text."""
        return {
            'characters': len(text),
            'words': len(text.split())
        }
        
    def save_doc_outputs(self, doc_id: str, policy_doc_name: str) -> None:
        """Save individual document outputs."""
        if doc_id not in self.qa_text or not self.qa_text[doc_id]:
            return
            
        output_dir = self.get_output_dir()
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Calculate total stats for this document
        all_text = "\n<EOS>\n".join(self.qa_text[doc_id])
        stats = self.count_text_stats(all_text)
        self.doc_stats[doc_id] = stats
        
        # Save document text file
        txt_path = output_dir / f"{doc_id}_qa.txt"
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(all_text)
        logger.info(f"Saved individual {self.prompt_type} text file: {txt_path}")
        
        # Log statistics
        logger.info(f"Statistics for {doc_id} ({self.prompt_type} prompt):")
        logger.info(f"  - Total characters: {stats['characters']:,}")
        logger.info(f"  - Total words: {stats['words']:,}")
        
        # Save document JSON file
        if policy_doc_name in self.qa_json:
            doc_json = {
                policy_doc_name: self.qa_json[policy_doc_name],
                'statistics': stats
            }
            json_path = output_dir / f"{doc_id}_qa.json"
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(doc_json, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved individual {self.prompt_type} JSON file: {json_path}")
        
    def save_combined_outputs(self) -> None:
        """Save combined outputs for all documents."""
        if not self.qa_json:
            return
            
        output_dir = self.get_output_dir()
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Calculate combined statistics
        total_stats = {
            'characters': sum(stats['characters'] for stats in self.doc_stats.values()),
            'words': sum(stats['words'] for stats in self.doc_stats.values())
        }
        
        # Save combined text file
        all_qa_texts = []
        for doc_texts in self.qa_text.values():
            all_qa_texts.extend(doc_texts)
            
        if all_qa_texts:
            txt_path = output_dir / "combined_qa.txt"
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write("\n<EOS>\n".join(all_qa_texts))
            logger.info(f"Saved combined {self.prompt_type} text file: {txt_path}")
            
        # Log combined statistics
        logger.info(f"\nTotal statistics for {self.prompt_type} prompt:")
        logger.info(f"  - Total characters across all files: {total_stats['characters']:,}")
        logger.info(f"  - Total words across all files: {total_stats['words']:,}")
        
        # Save combined JSON file with statistics
        combined_json = {
            'documents': self.qa_json,
            'statistics': {
                'per_document': self.doc_stats,
                'total': total_stats
            }
        }
        json_path = output_dir / "combined_qa.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(combined_json, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved combined {self.prompt_type} JSON file: {json_path}")

    def add_qa_pair(self, doc_id: str, qa_text: str) -> None:
        """Add a QA pair to the outputs."""
        if doc_id not in self.qa_text:
            self.qa_text[doc_id] = []
        self.qa_text[doc_id].append(qa_text)
        
    def add_keyword_content(self, doc_id: str, policy_doc_name: str, 
                          keyword: str, qa_pairs: List[Dict], 
                          content: List[Dict], original_filename: str) -> None:
        """Add keyword content to JSON output."""
        if policy_doc_name not in self.qa_json:
            self.qa_json[policy_doc_name] = {}
            
        self.qa_json[policy_doc_name][keyword] = {
            'qa_pairs': qa_pairs,
            'content': content,
            'original_filename': original_filename
        }

class QAGenerator:
    """Handles generation of Q&A pairs using Ollama API."""
    
    def __init__(self, config):
        self.config = config
        self.base_url = config.ollama.base_url
        self.model_name = config.ollama.model_name
        self.session = requests.Session()
        self.processed_sections: Set[str] = set()
        
        # Initialize output managers for both prompt types
        self.output_managers = {
            'default': QAOutputManager(config, 'default'),
            'alternative': QAOutputManager(config, 'alternative')
        }

    def generate_prompt(self, policy_doc_name: str, keyword: str, 
                       content: List[Dict], prompt_type: PromptType) -> str:
        """Generate structured prompt for QA generation."""
        pages = set()
        merged_content = []
        
        for occurrence in content:
            if 'location' in occurrence and 'page_number' in occurrence['location']:
                pages.add(occurrence['location']['page_number'])
            
            if 'content' in occurrence:
                selected_text = occurrence['content'].get('selected_text', '').strip()
                full_context = occurrence['content'].get('full_extracted_part', '').strip()
                content_text = full_context if full_context else selected_text
                if content_text:
                    merged_content.append(content_text)
        
        formatted_pages = ", ".join(sorted(pages, key=lambda x: int(str(x)) 
                                  if str(x).isdigit() else x)[:2])
        
        template = self.config.prompts[prompt_type]
        return template.format(
            keyword=keyword,
            policy_doc_name=policy_doc_name,
            formatted_pages=formatted_pages,
            content=' '.join(merged_content)
        )

    def parse_qa_response(self, response_text: str, prompt_type: PromptType) -> List[Dict[str, str]]:
        """Parse QA pairs from model response."""
        qa_pairs = []
        current_q = None
        current_a = None
        
        lines = [line.strip() for line in response_text.split('\n') if line.strip()]
        
        for line in lines:
            if line.startswith('Q:'):
                if current_q and current_a:
                    # Different validation for alternative prompt
                    if prompt_type == 'alternative' or (
                        prompt_type == 'default' and 
                        current_q.endswith('?') and
                        ('based on' in current_q or 'as per' in current_q) and
                        current_a.endswith(')')
                    ):
                        qa_pairs.append({
                            'question': current_q,
                            'answer': current_a
                        })
                current_q = line[2:].strip()
                current_a = None
            elif line.startswith('A:'):
                current_a = line[2:].strip()

        if current_q and current_a:
            # Different validation for alternative prompt
            if prompt_type == 'alternative' or (
                prompt_type == 'default' and 
                current_q.endswith('?') and
                ('based on' in current_q or 'as per' in current_q) and
                current_a.endswith(')')
            ):
                qa_pairs.append({
                    'question': current_q,
                    'answer': current_a
                })
        
        return qa_pairs

    def generate_qa_pairs(self, policy_doc_name: str, keyword: str, 
                         occurrences: List[Dict], prompt_type: PromptType) -> List[Dict[str, str]]:
        """Generate QA pairs using Ollama API."""
        if not occurrences:
            return []
            
        prompt = self.generate_prompt(policy_doc_name, keyword, occurrences, prompt_type)
        
        retries = self.config.ollama.retries
        retry_count = 0
        
        while retry_count < retries:
            try:
                logger.info(f"Attempt {retry_count + 1} for {keyword} ({prompt_type})")
                
                response = self.session.post(
                    f"{self.base_url}/api/generate",
                    json={
                        "model": self.model_name,
                        "prompt": prompt,
                        "temperature": self.config.ollama.temperature,
                        "stream": False
                    },
                    timeout=self.config.ollama.timeout
                )
                
                if response.status_code == 200:
                    qa_text = response.json().get('response', '').strip()
                    if qa_text:
                        qa_pairs = self.parse_qa_response(qa_text, prompt_type)
                        logger.info(f"Generated {len(qa_pairs)} Q&A pairs for {prompt_type} prompt")
                        return qa_pairs
                    else:
                        logger.warning(f"Empty response received for {keyword} ({prompt_type})")
                else:
                    logger.warning(f"HTTP {response.status_code} received for {keyword} ({prompt_type})")
                    
            except requests.exceptions.ReadTimeout:
                logger.warning(f"Timeout occurred on attempt {retry_count + 1} for {keyword} ({prompt_type})")
            except requests.exceptions.ConnectionError:
                logger.warning(f"Connection error on attempt {retry_count + 1} for {keyword} ({prompt_type})")
            except Exception as e:
                logger.error(f"Error on attempt {retry_count + 1} for {keyword} ({prompt_type}): {str(e)}")
            
            retry_count += 1
            if retry_count < retries:
                delay = self.config.ollama.retry_delay * (retry_count + 1)  # Progressive delay
                logger.info(f"Waiting {delay} seconds before retry...")
                time.sleep(delay)
        
        logger.error(f"Failed to generate Q&A pairs for {keyword} ({prompt_type}) after {retries} attempts")
        return []

    def _get_policy_doc_name(self, doc_id: str) -> str:
        """Generate policy document name from doc ID."""
        # Extract number from doc_id (e.g., 'doc_001' -> 1)
        num = int(doc_id.split('_')[1])
        return f"[POLICY_DOC_{num:03d}]"

    def process_document_keywords(self, doc_id: str, findings: Dict, 
                                original_filename: str, prompt_type: PromptType) -> None:
        """Process all keywords for a document with specified prompt type."""
        policy_doc_name = self._get_policy_doc_name(doc_id)
        output_manager = self.output_managers[prompt_type]
        has_content = False
        
        for keyword in self.config.keywords:
            if keyword not in findings:
                continue
            
            checkpoint_key = f"{doc_id}|{keyword}|{prompt_type}"
            if checkpoint_key in self.processed_sections:
                logger.info(f"Skipping already processed: {keyword} ({prompt_type})")
                continue
            
            logger.info(f"Processing keyword: {keyword} ({prompt_type})")
            occurrences = findings[keyword]
            
            if occurrences:
                qa_pairs = self.generate_qa_pairs(policy_doc_name, keyword, 
                                                occurrences, prompt_type)
                
                if qa_pairs:
                    has_content = True
                    # Add to outputs
                    output_manager.add_keyword_content(
                        doc_id, policy_doc_name, keyword, qa_pairs, 
                        occurrences, original_filename
                    )
                    
                    # Add QA pairs to text output
                    for qa in qa_pairs:
                        qa_text = f"Q: {qa['question']}\nA: {qa['answer']}"
                        output_manager.add_qa_pair(doc_id, qa_text)
                    
                    self.processed_sections.add(checkpoint_key)
        
        # Save individual document outputs if we added content
        if has_content:
            output_manager.save_doc_outputs(doc_id, policy_doc_name)
            logger.info(f"Saved outputs for {original_filename} ({prompt_type})")

    def process_content(self, masked_content: Dict) -> None:
        """Process all files with both prompt types."""
        if not masked_content:
            logger.warning("No masked content provided")
            return

        # If it's a single file result (no 'findings' key), wrap it
        if 'findings' not in masked_content and any(k in masked_content for k in self.config.keywords):
            # For single file, use actual filename if available from pdf_processor
            filename = masked_content.get('original_filename', 'single_file.pdf')
            masked_content = {
                'doc_001': {
                    'original_filename': filename,
                    'findings': masked_content
                }
            }

        # Process each document with both prompt types
        total_files = len(masked_content)
        logger.info(f"Processing {total_files} file(s)")
        
        for doc_id, doc_data in tqdm(masked_content.items(), desc="Processing files"):
            findings = doc_data['findings']
            original_filename = doc_data.get('original_filename', f"{doc_id}.pdf")
            
            logger.info(f"\nProcessing file: {original_filename}")
            
            # Process with default prompt
            logger.info("Processing with default prompt")
            self.process_document_keywords(doc_id, findings, original_filename, 'default')
            
            # Process with alternative prompt
            logger.info("Processing with alternative prompt")
            self.process_document_keywords(doc_id, findings, original_filename, 'alternative')
            
            # Log completion of individual file
            logger.info(f"Completed processing {original_filename}")
        
        # Save combined outputs after all files are processed
        logger.info("Processing complete. Creating combined outputs...")
        for prompt_type, output_manager in self.output_managers.items():
            output_manager.save_combined_outputs()
        logger.info("All processing and output generation completed")