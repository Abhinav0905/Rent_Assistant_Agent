from openai import OpenAI

client = OpenAI()


def create_vector_store(pdf_path: str):
    vector_store = client.vector_stores.create(  # Create vector store
        name="Storage Rental Agreement",
    )
    client.vector_stores.files.upload_and_poll(  # Upload file
        vector_store_id=vector_store.id,
        file=open(pdf_path, "rb"),
    )
    print(f"Vector store created with ID: {vector_store.id}")
    return vector_store.id


if __name__ == "__main__":
    # Create a vector store for the rental agreement
    create_vector_store("/Users/kumarabhinav/Documents/My Documents/Stoneridge_lease/lease.pdf")