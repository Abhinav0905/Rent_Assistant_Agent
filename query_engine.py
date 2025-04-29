# Agents to query RAG using OpenAI Agent
import asyncio
from contextlib import contextmanager
import os
from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from agents import Agent, FunctionTool, Runner, FileSearchTool
from openai import OpenAI
import sys


client = OpenAI()

# Load environment variables
load_dotenv()


class RentalAgreementQueryEngine:
    def __init__(self):
        pass

    def create_vector_store(self, pdf_path: str):
        vector_store = client.vector_stores.create(  # Create vector store
            name="Storage Rental Agreement",
        )
        client.vector_stores.files.upload_and_poll(  # Upload file
            vector_store_id=vector_store.id,
            file=open("/Users/kumarabhinav/Documents/My Documents/Stoneridge_lease/lease.pdf", "rb"),
        )
        return vector_store

    async def search_local_documents(self, query: str) -> str:
        agent = Agent(
            name="Rental Agreement Searcher",
            instructions=(
                "You are a helpful assistant for rental agreements. "
                "When asked a question, use the search_rental_agreement tool to find relevant information, "
                "then provide a clear, concise answer based on the search results. "
                "Always cite specific sections of the agreement in your answer. "
                "If the user asks for a translation, use the translation agent to translate the response. "
                "If the user asks for a summary, use the synthesizer agent to summarize the response. "
                "If the user asks for a specific section, use the synthesizer agent to extract the relevant section. "
                "If the user asks for a specific clause, use the synthesizer agent to extract the relevant clause. "
                "If the user asks for a specific term, use the synthesizer agent to extract the relevant term. "
                "If the user asks for a specific condition, use the synthesizer agent to extract the relevant condition. "
                "If you are unsure about the answer, ask the user for clarification. "
                "If you cannot find the answer, inform the user that you are unable to find the information."
            ),
            model="gpt-4-turbo",
            tools=[
                FileSearchTool(
                    max_num_results=2,
                    vector_store_ids=["vs_680dc43cbfd4819190bb19a184814410"],
                    include_search_results=True
                ),
            ],
        )
        
        # Use the agent to process the query
        runner = Runner()
        try:
            result = await runner.run(agent, query)
            response_text = None
            print(result)
            # return response
            # Extract text from RunResult object
            if hasattr(result, 'content') and result.content:
                response_text = result.content
            elif hasattr(result, 'response') and result.response:
                response_text = result.response
            elif hasattr(result, 'message') and result.message:
                response_text = result.message
            else:
                response_text = str(result)
                    
                print("Response extracted from agent:", response_text[:100])
                return response_text
                    
        except Exception as e:
            error_msg = f"Error in search_local_documents: {e}"
            print(error_msg)
            return f"Sorry, I encountered an error while searching the rental agreement: {str(e)}"
        
    # async def query(self, question):
    #     """Query the rental agreement with a question"""
    #     return await self.search_local_documents(question)


# Create a singleton instance
engine = RentalAgreementQueryEngine()


# This function maintains backward compatibility
async def query_agreement(question):
    """Query the rental agreement with a question"""
    return await engine.search_local_documents(question)

rentalagreementqueryengine = RentalAgreementQueryEngine()

# # For direct execution
# if __name__ == "__main__":
#     question = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "What is the notice period?"
#     # Add language detection capability

#     async def query_agreement(question):
#         """Query the rental agreement with a question"""
#         return await engine.query(question)

#     # For direct execution
#     if __name__ == "__main__":
#         question = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "What is the notice period?"
#         asyncio.run(engine.query(question))

#     # Updated RentalAgreementQueryEngine with language detection
    