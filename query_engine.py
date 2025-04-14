# Agents to query RAG using OpenAI Agent
import asyncio
from contextlib import contextmanager
import os
from dotenv import load_dotenv

from langchain_openai import OpenAIEmbeddings
# from langchain_community.vectorstores import Chroma
from langchain_chroma import Chroma
from agents import Agent, FunctionTool, Runner, trace

# Load environment variables
load_dotenv()

# Configure translation agents
spanish_agent = Agent(
    name="Spanish Translator",
    instructions="You translate the user message accurately to Spanish. Maintain the professional tone and terminology.",
    handoff_description="An English to Spanish translator",
    model="gpt-4-turbo"
)

hindi_agent = Agent(
    name="Hindi Translator",
    instructions="You translate the user message accurately to Hindi. Maintain the professional tone and terminology.",
    handoff_description="An English to Hindi translator",
    model="gpt-4-turbo"
)

french_agent = Agent(
    name="French Translator",
    instructions="You translate the user message accurately to French. Maintain the professional tone and terminology.",
    handoff_description="An English to French translator",
    model="gpt-4-turbo"
)

orchestrator_agent = Agent(
    name="Translation Orchestrator",
    instructions=(
        "You are a translation agent. You use the tools given to you to translate. "
        "If asked for multiple translations, you call the relevant tools in order. "
        "You never translate on your own, you always use the provided tools."
    ),
    tools=[
        spanish_agent.as_tool(
            tool_name="translate_to_spanish",
            tool_description="Translate the user's message to Spanish"
        ),
        hindi_agent.as_tool(
            tool_name="translate_to_hindi",
            tool_description="Translate the user's message to Hindi"
        ),
        french_agent.as_tool(
            tool_name="translate_to_french",
            tool_description="Translate the user's message to French"
        ),
    ],
    model="gpt-4-turbo"
)

synthesizer_agent = Agent(
    name="Response Synthesizer",
    instructions="You inspect the provided text, correct any errors, and produce a clear, concise final response that maintains all key information.",
    model="gpt-4-turbo"
)


# Function to search embedded documents and return the answer to the user
async def search_local_documents(query: str) -> str:
    """
    Search the local database for the user's query.
    
    Args:
        query (str): The user's query
        
    Returns:
        str: A string containing search results from the vector store
    """
    try:
        # Initialize embedding
        embedding = OpenAIEmbeddings(
            openai_api_key=os.getenv("OPENAI_API_KEY")
        )

        # Load the local vector store
        vector_store = Chroma(
            persist_directory="db",
            embedding_function=embedding
        )

        # Search the vector store for the user's query
        docs = vector_store.similarity_search_with_score(
            query=query,
            k=3
        )

        # Format the results as a string
        formatted_results = []
        for i, (doc, score) in enumerate(docs):
            formatted_results.append(f"Result {i+1} (Relevance: {score:.4f}):\n{doc.page_content}\n")
        
        return "\n".join(formatted_results)
    except Exception as e:
        return f"Error searching documents: {str(e)}"


# Rental Agreement Query Engine
class RentalAgreementQueryEngine:
    def __init__(self):
        """Initialize the Rental Agreement Query Engine"""
        # Create a local search tool
        async def invoke_search(context, args):
            # Handle when args is passed as a string
            if isinstance(args, str):
                query = args
            else:
                query = args.get("query", "")
            return await search_local_documents(query)
            
        self.local_search_tool = FunctionTool(
            "search_rental_agreement",
            "Searches the rental agreement for relevant information",
            {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query about the rental agreement"
                    }
                },
                "required": ["query"],
                "additionalProperties": False
            },
            invoke_search
        )
        
        # Create the rental agreement search agent
        self.rental_agent = Agent(
            name="Rental Agreement Searcher",
            instructions="""You are a helpful assistant for rental agreements.
            When asked a question, use the search_rental_agreement tool to find relevant information,
            then provide a clear, concise answer based on the search results.
            Always cite specific sections of the agreement in your answer.""",
            model="gpt-4-turbo",
            tools=[self.local_search_tool]
        )
    
    @contextmanager
    def trace(self, name):
        """Context manager for tracing execution"""
        try:
            yield
        finally:
            pass
    
    async def query(self, question, translate=False):
        """Process a question about the rental agreement
        
        Args:
            question (str): The question to ask about the rental agreement
            translate (bool): Whether to include translations
            
        Returns:
            dict: Response with original question and answers
        """
        try:
            # Step 1: Query the rental agreement
            with self.trace("rental_agent"):
                result = await Runner.run(self.rental_agent, question)
                rental_response = result.final_output
            
            # Step 2: Synthesize the response
            with self.trace("synthesizer_agent"):
                result = await Runner.run(synthesizer_agent, rental_response)
                synthesized_response = result.final_output
            
            # Store the results
            response_data = {
                "original_question": question,
                "answer": synthesized_response,
                "detailed_response": rental_response
            }
            
            # Step 3: Translate if requested
            if translate:
                translation_request = f"Translate this rental policy: {synthesized_response}"
                with self.trace("orchestrator_agent"):
                    result = await Runner.run(orchestrator_agent, translation_request)
                    translated_response = result.final_output
                response_data["translated_response"] = translated_response
                
            return response_data
            
        except Exception as e:
            print(f"Error in query method: {str(e)}")
            return {"error": str(e)}

# Create a singleton instance
engine = RentalAgreementQueryEngine()

# This function maintains backward compatibility
async def query_agreement(question):
    """Query the rental agreement with a question"""
    return await engine.query(question)

# For direct execution
if __name__ == "__main__":
    async def main():
        question = "What is the Pet Policy mentioned in the rental agreement?"
        result = await query_agreement(question)
        print(f"Question: {question}")
        print(f"\nAnswer: {result.get('answer', 'No answer available')}")
        
    asyncio.run(main())
