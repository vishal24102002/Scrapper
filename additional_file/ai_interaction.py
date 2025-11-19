import os
import sys
import json
import torch
import pandas as pd
from tqdm import tqdm
import docx
import PyPDF2
from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer, AutoModelForCausalLM

# File paths for storing configuration and processed files data
CONFIG_FILE = 'config.json'
PROCESSED_FILES_FILE = 'processed_files.pkl'
EMBEDDINGS_FILE = 'embeddings.pkl'

# Text extraction function
def extract_text_from_file(file_path):
    try:
        if file_path.lower().endswith('.txt'):
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
            return text
        elif file_path.lower().endswith('.docx'):
            doc = docx.Document(file_path)
            text = '\n'.join([para.text for para in doc.paragraphs])
            return text
        elif file_path.lower().endswith('.pdf'):
            text = ''
            with open(file_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    text += page.extract_text()
            return text
        elif file_path.lower().endswith('.xlsx'):
            df = pd.read_excel(file_path)
            text = df.to_string()
            return text
        else:
            return ''
    except Exception as e:
        print(f"Error extracting text from {file_path}: {e}")
        return ''

# Function to recursively find all files with given extensions
def find_files(base_dir, extensions):
    file_paths = []
    for root, _, files in os.walk(base_dir):
        for file in files:
            if any(file.lower().endswith(ext) for ext in extensions):
                file_paths.append(os.path.join(root, file))
    return file_paths

# Function to load or set the base directory
def get_base_directory():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
        base_dir = config.get('base_directory', '')
        if base_dir:
            print(f"Default base directory: {base_dir}")
            use_default = input("Do you want to use the default directory? (y/n): ").strip().lower()
            if use_default == 'y':
                return base_dir
            else:
                base_dir = input("Enter the new base directory to search: ").strip()
                config['base_directory'] = base_dir
                with open(CONFIG_FILE, 'w') as f:
                    json.dump(config, f)
                return base_dir
        else:
            # base_directory is empty, ask user to enter it
            base_dir = input("Enter the base directory to search: ").strip()
            config['base_directory'] = base_dir
            with open(CONFIG_FILE, 'w') as f:
                json.dump(config, f)
            return base_dir
    else:
        # CONFIG_FILE doesn't exist, create it and ask user for base directory
        base_dir = input("Enter the base directory to search: ").strip()
        config = {'base_directory': base_dir}
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f)
        return base_dir

# Load embedding model
embedding_model = SentenceTransformer('all-mpnet-base-v2')

# Load language generation model (using GPT-2 Medium)
tokenizer = AutoTokenizer.from_pretrained("gpt2-medium")
model = AutoModelForCausalLM.from_pretrained("gpt2-medium")
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
model.to(device)

# Build or update embeddings index
def build_embeddings_index(file_paths, processed_files):
    data = []
    new_processed_files = processed_files.copy()
    for file_path in tqdm(file_paths, desc="Processing files"):
        file_modified_time = os.path.getmtime(file_path)
        if file_path in processed_files and processed_files[file_path] == file_modified_time:
            # File has not changed since last processing
            continue
        # Extract text
        text = extract_text_from_file(file_path)
        if text:
            # Add to data for embedding
            data.append({'file_path': file_path, 'text': text})
            # Update processed files info
            new_processed_files[file_path] = file_modified_time
    if data:
        df_new = pd.DataFrame(data)
        print("Generating embeddings for new or updated files...")
        embeddings = embedding_model.encode(df_new['text'].tolist(), show_progress_bar=True, convert_to_tensor=True, batch_size=16)
        df_new['embedding'] = embeddings.cpu().numpy().tolist()
        # If embeddings file exists, load it and append new embeddings
        if os.path.exists(EMBEDDINGS_FILE):
            df_existing = pd.read_pickle(EMBEDDINGS_FILE)
            df_combined = pd.concat([df_existing, df_new], ignore_index=True)
        else:
            df_combined = df_new
        # Save combined embeddings
        df_combined.to_pickle(EMBEDDINGS_FILE)
    else:
        # No new files to process
        if os.path.exists(EMBEDDINGS_FILE):
            df_combined = pd.read_pickle(EMBEDDINGS_FILE)
        else:
            df_combined = pd.DataFrame(columns=['file_path', 'text', 'embedding'])
    # Save updated processed files info
    pd.to_pickle(new_processed_files, PROCESSED_FILES_FILE)
    return df_combined

# Similarity search function
def search_embeddings(df, query, top_k=5):
    query_embedding = embedding_model.encode(query, convert_to_tensor=True)
    corpus_embeddings = torch.stack(df['embedding'].tolist()).to(device)
    query_embedding = query_embedding.to(device)
    with torch.no_grad():
        cos_scores = torch.nn.functional.cosine_similarity(query_embedding, corpus_embeddings)
    top_results = torch.topk(cos_scores, k=min(top_k, len(df)))
    indices = top_results.indices.cpu().numpy()
    scores = top_results.values.cpu().numpy()
    results = df.iloc[indices].copy()
    results['similarity'] = scores
    return results

# Generate response function
def generate_response(prompt):
    inputs = tokenizer.encode(prompt, return_tensors="pt").to(device)
    with torch.no_grad():
        outputs = model.generate(inputs, max_length=512, do_sample=True, temperature=0.7)
    response = tokenizer.decode(outputs[0], skip_special_tokens=True)
    return response

# Main execution
if __name__ == "__main__":
    # Define file extensions to search for
    FILE_EXTENSIONS = ['.txt', '.docx', '.pdf', '.xlsx']

    # Get base directory
    BASE_DIR = get_base_directory()

    # Find all files
    file_paths = find_files(BASE_DIR, FILE_EXTENSIONS)
    print(f"Found {len(file_paths)} files.")

    # Load processed files info
    if os.path.exists(PROCESSED_FILES_FILE):
        processed_files = pd.read_pickle(PROCESSED_FILES_FILE)
    else:
        processed_files = {}

    # Build or update embeddings index
    df = build_embeddings_index(file_paths, processed_files)

    # Main loop for user queries
    while True:
        query = input("\nEnter your query (or 'exit' to quit): ")
        if query.lower() == 'exit':
            break
        print("Searching for relevant information...")
        results = search_embeddings(df, query, top_k=5)
        if results.empty:
            print("No relevant information found.")
            continue
        context = '\n\n'.join(results['text'].tolist())
        prompt = f"Based on the following documents:\n\n{context}\n\nAnswer the following question in a detailed and human-like manner:\n{query}"
        print("Generating response...")
        answer = generate_response(prompt)
        print("\nAnswer:")
        print(answer)
