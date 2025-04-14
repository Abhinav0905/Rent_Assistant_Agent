import os
import fitz
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
# from langchain_community.vectorstores import Chroma
from langchain_chroma import Chroma
from dotenv import load_dotenv

load_dotenv()


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
pdf_path = "/Users/kumarabhinav/Documents/My Documents/Stoneridge_lease/lease.pdf"  # NOQA E501


# Extract Tetxt form the PDF document
def extract_words_from_pdf(pdf_path) -> list:
    """
    Extract words form the PDF document.
    
    Args:
        pdf_path (str): Path to the PDF file
        
    Returns:
        list: List of words extracted form the PDF
    
    """
    words = []
    with fitz.open(pdf_path) as doc:
        for page_num in range(doc.page_count):
            page = doc[page_num]
            text = page.get_text()
            words.extend(text.split())
    return words


# Split the extracted documents intom manageable chunks
def chunk_text(text: str, chunk_size: int = 500, chunk_overlap: int = 50) -> list:  # NOQA E501
    """
    Split teh extracted text into managebale chunks
 
    Args:
        text (str): Text to be chunked
        chunk_size (int): Size of each chunk
        chunk_overlap (int): Overlap between chunks
     
        Returns:
            list: List of text chunks     
    """
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len
    )
    chunks = text_splitter.split_text(text)
    return chunks


# Generate Embedding of the chunks
def genetate_embedding(chunks: list) -> list:
    """
    Generate embedding of the chunks.
    
    Args:
        chnnks (list): List of text chunks
    Returns:
        list: List of embeddings
    """
    embedding_model = OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY)  # NOQA E501
    embeddings = []
    for chunk in chunks:
        embedding = embedding_model.embed_documents([chunk])
        embeddings.append(embedding)
    return embeddings


# Store the embedding into a vector store
def store_embeding(chunks: list) -> None:
    """
    Store the embedding into a vector store.

    Args:
        embedding (list): List of embeddings
    """
    vector_db = Chroma.from_texts(
        texts=chunks,
        embedding=OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY),
        persist_directory="db"  # Directory to store the vector store
        )
    vector_db.persist()  # Persist the vector store
    return vector_db


# Main function
def main():
    """
    Main function to extract text from PDF, chunk it, generate embeddings, and store them in a vector store.    # NOQA E501
    """
    # Extract words from the PDF document
    words = extract_words_from_pdf(pdf_path)
    
    # Join the words into a single string
    text = " ".join(words)
    
    # Chunk the extracted text into manageable chunks
    chunks = chunk_text(text)
    
    # Generate embeddings for the chunks
    embeddings = genetate_embedding(chunks)

    # Print the number of embeddings
    print(f"Number of embeddings: {len(embeddings)}")

    # Print the number of chunks
    print(f"Number of chunks: {len(chunks)}")

    # Store the embeddings in a vector store

    store_embeding(chunks)
    # Print the number of chunks in the vector store


if __name__ == "__main__":
    main()
