from agents import Agent, Runner
from fastapi import logger
from langdetect import detect
from query_engine import query_agreement
from openai import OpenAI
import json
from models import TicketCategory, TicketPriority

client = OpenAI()

class QueryDetection():

    QUESTION = "question"
    MAINTENANCE = "maintenance"
    STATUS = "status_check"
    OTHER = "other"

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

    language_agents = {
        "es": spanish_agent,
        "hi": hindi_agent,
        "fr": french_agent
    }

    @classmethod
    async def detect_language(cls, text):
        try:
            return detect(text)
        except Exception as e:
            logger.error(f"Language detection failed: {str(e)}")
            return "en"  # Default to English if detection fails

    @classmethod
    async def translate_to_english(cls, text, source_lang):
        """Translate input to English if needed"""
        if source_lang == "en":
            return text
            
        # Create a custom prompt for translation to English
        prompt = f"Translate this text from {source_lang} to English: {text}"
        
        if source_lang == "es":
            runner = Runner()
        elif source_lang == "hi":
            runner = Runner()
        elif source_lang == "fr":
            runner = Runner()
        else:
            return text  # Return original if no matching agent
        
        response = await runner.run(cls.orchestrator_agent, prompt)
        return response

    @classmethod
    async def translate_response(cls, response, target_lang):
        """Translate response to target language"""
        if target_lang == "en":
            return response
            
        tool_map = {
            "es": "translate_to_spanish",
            "hi": "translate_to_hindi",
            "fr": "translate_to_french"
        }
        
        # if target_lang in tool_map:
        #     runner = Runner(cls.orchestrator_agent)
        #     result = await runner.run({
        #         "tool": tool_map[target_lang],
        #         "text": response
        #     })
        #     return result
        # return response
        if target_lang in tool_map:
            runner = Runner()
        # Use direct text input instead of dictionary
            tool_name = tool_map[target_lang]
            prompt = f"Please translate this to {target_lang}: {response}"
            result = await runner.run(cls.orchestrator_agent, prompt)
            
            # Extract text from RunResult
            if hasattr(result, 'content'):
                return result.content
            elif hasattr(result, 'response'):
                return result.response
            else:
                return str(result)
        return response

    @classmethod
    async def synthesize_response(cls, response):
        """Use synthesizer to improve the response"""
        # Convert response object to string if needed
        if not isinstance(response, str):
            if hasattr(response, 'response'):
                text_to_synthesize = response.response
            elif hasattr(response, 'content'):
                text_to_synthesize = response.content
            elif hasattr(response, 'message'):
                text_to_synthesize = response.message
            else:
                text_to_synthesize = str(response)
        else:
            text_to_synthesize = response
            
        runner = Runner()
        try:
            result = await runner.run(cls.synthesizer_agent, text_to_synthesize)
            # Extract text from RunResult
            if hasattr(result, 'content'):
                return result.content
            elif hasattr(result, 'response'):
                return result.response
            else:
                return str(result)
        except Exception as e:
            print(f"Error in synthesize_response: {e}")
            return text_to_synthesize  # Return original text if synthesis fails
            # result = await runner.run(cls.synthesizer_agent, text_to_synthesize)
        # return result

    @classmethod
    async def search_local_documents(cls, question):
        """Search local documents using query engine"""
        response = await query_agreement(question)  
        print("Response from query engine:", response)
        return response
    
    @classmethod
    async def query(cls, question):
        """Process a query from the user"""
        try:
            # Detect language
            source_lang = await cls.detect_language(question)
            print(f"Detected language: {source_lang}")

            # First detect intent
            intent_result = await cls.detect_message_intent(question)
            intent = intent_result.get("intent", "question")
            print(f"Detected intent: {intent}")

            # Handle based on intent
            if intent == "maintenance":
                # For maintenance requests, return the full result without modification
                return intent_result
            
            # For regular questions, proceed with normal flow
            english_question = question
            if source_lang != "en":
                english_question = await cls.translate_to_english(question, source_lang)
            
            response = await cls.search_local_documents(english_question)
            
            # Make sure response is a string
            if not isinstance(response, str):
                if hasattr(response, 'content'):
                    response = response.content
                elif hasattr(response, 'response'):
                    response = response.response
                elif hasattr(response, 'message'):
                    response = response.message
                else:
                    response = str(response)
            
            if source_lang != "en":
                response = await cls.translate_response(response, source_lang)
                
            return response
        except Exception as e:
            print(f"Error in query processing: {e}")
            return f"Sorry, I encountered an error processing your query: {str(e)}"
        
    @classmethod
    async def detect_message_intent(cls, message: str) -> dict:
        """
        Determine if the message is a question about the lease or a maintenance request
        
        Returns:
            dict with keys: 
                - intent (MessageIntent)
                - confidence (float)
                - ticket_data (dict, only for maintenance requests)
        """
        # client = OpenAI()
        
        try:
            response = client.chat.completions.create(
                model="gpt-4-turbo",
                messages=[
                    {"role": "system", "content": 
                        """Analyze the maintenance request and extract detailed information in this format:
                        
                        1. Is this message:
                           - A maintenance request/issue that needs repair
                           - A question about rental agreement/lease terms
                           - A status check request
                           - Something else
                        
                        2. For maintenance requests, analyze and extract:
                           - What is the specific issue (detailed description)
                           - What fixtures/appliances are involved
                           - Location in the apartment
                           - Signs or symptoms of the problem
                           - How urgent is it (emergency/high/normal/low)
                           - Category: plumbing, electrical, hvac, appliance, structural, pest, locksmith, cleaning, other
                        
                        Return a JSON object:
                        {
                            "intent": "maintenance"|"question"|"status_check"|"other",
                            "confidence": 0.0-1.0,
                            "ticket_data": {
                                "description": "Detailed analysis of the issue",
                                "location": "Specific location in unit",
                                "symptoms": "Observable problems",
                                "category": "Category from list above",
                                "priority": "emergency|high|normal|low",
                                "apartment_number": "Unit number if mentioned",
                                "access_instructions": "Any access details provided"
                            }
                        }"""
                    },
                    {"role": "user", "content": message}
                ],
                response_format={"type": "json_object"},
                temperature=0.1
            )
            
            result = json.loads(response.choices[0].message.content)
            
            # For maintenance requests, format a proper description
            if result["intent"] == "maintenance" and "ticket_data" in result:
                ticket_data = result["ticket_data"]
                
                # Create a detailed description
                description_parts = []
                if ticket_data.get("location"):
                    description_parts.append(f"Location: {ticket_data['location']}")
                if ticket_data.get("symptoms"):
                    description_parts.append(f"Issue: {ticket_data['symptoms']}")
                
                # Update the description to be more detailed
                ticket_data["description"] = "\n".join(description_parts) or message
                
                # Validate category and priority
                try:
                    ticket_data["category"] = TicketCategory(ticket_data.get("category", "other").lower())
                except ValueError:
                    ticket_data["category"] = TicketCategory.OTHER
                
                try:
                    ticket_data["priority"] = TicketPriority(ticket_data.get("priority", "normal").lower())
                except ValueError:
                    ticket_data["priority"] = TicketPriority.NORMAL
                
                result["ticket_data"] = ticket_data
            
            return result
            
        except Exception as e:
            print(f"Error in intent detection: {e}")
            return {
                "intent": "question",
                "confidence": 0.5,
            }