## Automation of pdf scraping and QnA dataset preparation

## Config.yaml params 
#### All configuration settings changes needs to be made in the Config.yaml file in the main directory
1. Storage provider - could be "local" or "gcp"
2. Input - Currently works for pdf
3. Output - Output directory nanes
4. Processing - Augmentation factor - Controls number of times to generate QA pairs (x3, x10 etc)
5. Ollama model settings
6. Set of all required keywords for which we need parsing
7. Prompts - Two prompts - Default prompt and alternative prompt

### Output 
```bash
processed_outputs/
├── masked_content/
│   └── combined_masked.json #all files parsed with page number, line number, all content from the previous block, current block and next two blocks 
├── qa_outputs/
    ├── default_prompt/
    │   ├── doc_001_qa.txt        #Individual file outputs
    │   ├── doc_001_qa.json
    │   ├── combined_qa.txt       #combined outputs
    │   └── combined_qa.json
    └── alternative_prompt/
        ├── doc_001_qa.txt
        ├── doc_001_qa.json
        ├── combined_qa.txt
        └── combined_qa.json
```
---

## Setup Instructions
- Clone the repo
- Create a virtual environment using ```python -m venv <env_name>```
- ```source <env_name>/bin/activate``` followed by ```pip install -r requirements.txt```
- Run the ```python main.py``` with the following parameters
- Check if ollama is running for the specified model using ```ollama run llama3 or <model_name>```(exit using /bye)

### Process to run entire local directory of pdfs 
```bash
python main.py --config config.yaml --input "<folder with pdfs>"
```

### Process to test for a single pdf file
```bash
python main.py --config config.yaml --input "<folder with pdfs>/<filename>.pdf"
```

### Process to test for a single pdf file and a single keyword
```bash
python main.py --config config.yaml --input "<folder with pdfs>/<filename>.pdf" --single-file --keyword "Waiting Period"
```

---

### Process to run the pdf folders via GCP (input folder of pdfs from GCP bucket and output in GCP bucket)
#### Change the storage provider name in config.yaml to gcp (currently local for local folder processing)

```bash
storage:
  provider: "gcp"
  project_id: "<project_id>"  #say, proud-archery-430400-i1 in our project case
  bucket_name: "<bucket_name>"

then run GCP folder
```python main.py --config config.yaml --input "<gcp folder with pdfs>"```

if want to test single file from gcp folder
python main.py --config config.yaml --input "<gcp folder with pdfs>/<filename>.pdf" --single-file

```



