import argparse
import logging
from pathlib import Path
from utils.config_manager import ConfigurationManager
from processing.pdf_processor import PDFProcessor
from processing.qa_generator import QAGenerator

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def parse_arguments():
    parser = argparse.ArgumentParser(description='PDF Processing and QA Generation Tool')
    parser.add_argument(
        '--config',
        type=str,
        default='config.yaml',
        help='Path to configuration file'
    )
    parser.add_argument(
        '--input',
        type=str,
        required=True,
        help='Input path (file, directory, or GCS path)'
    )
    parser.add_argument(
        '--single-file',
        action='store_true',
        help='Process a single PDF file'
    )
    parser.add_argument(
        '--keyword',
        type=str,
        help='Process only specific keyword'
    )
    return parser.parse_args()

def main():
    args = parse_arguments()
    
    try:
        config = ConfigurationManager(args.config)
        logger.info(f"Configuration loaded from {args.config}")
        
        pdf_processor = PDFProcessor(config)
        qa_generator = QAGenerator(config)
        
        if args.single_file:
            logger.info(f"Processing single file: {args.input}")
            masked_content = pdf_processor.process_single_pdf(args.input)
            
            if args.keyword:
                logger.info(f"Processing keyword: {args.keyword}")
                qa_generator.process_single_keyword(masked_content, args.keyword)
            else:
                qa_generator.process_content(masked_content)
        else:
            logger.info(f"Processing directory: {args.input}")
            masked_content = pdf_processor.process_directory(args.input)
            qa_generator.process_content(masked_content)
            
        logger.info("Processing completed successfully")
        
    except Exception as e:
        logger.error(f"Error during processing: {e}")
        raise

if __name__ == "__main__":
    main()