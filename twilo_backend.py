# A backend for Twilio API 

from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from twilio.rest import Client
from twilio.request_validator import RequestValidator
import os
import logging
from dotenv import load_dotenv
from query_engine import query_agreement
import uvicorn
import time

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("twilio-backend")

app = FastAPI(
    title="Rental Agreement Assistant API",
    description="API for querying rental agreements via WhatsApp",
    version="1.0.0"
)
load_dotenv()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Twilio credentials
account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "your_account_sid")
auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "your_auth_token")
twilio_phone_number = os.environ.get("TWILIO_PHONE_NUMBER", "your_twilio_whatsapp_number")

# Initialize Twilio client
client = Client(account_sid, auth_token)
validator = RequestValidator(auth_token)

# Whitelist of approved phone numbers (your society members)
# Read from environment variable if available, otherwise use default
APPROVED_NUMBERS_STR = os.environ.get("APPROVED_WHATSAPP_NUMBERS", "+1 510 954 9624")
APPROVED_NUMBERS = [number.strip() for number in APPROVED_NUMBERS_STR.split(",")]

def normalize_phone_number(phone: str) -> str:
    """Normalize phone number to a standard format by removing spaces and prefixes"""
    # Remove any whatsapp: prefix
    phone = phone.replace("whatsapp:", "")
    # Remove all spaces
    phone = phone.replace(" ", "")
    # If number doesn't have country code but is US number (10 digits), add +1
    if len(phone) == 10 and phone.isdigit():
        phone = "+1" + phone
    # If number starts with 1 but no +, add +
    elif phone.startswith("1") and not phone.startswith("+"):
        phone = "+" + phone
    return phone


# Rate limiting
RATE_LIMIT = {}
MAX_REQUESTS = 10  # Maximum requests per time window
TIME_WINDOW = 60 * 10  # 10 minutes in seconds


def validate_twilio_request(request: Request):
    """Validate that the request is coming from Twilio"""
    signature = request.headers.get("X-Twilio-Signature", "")
    url = str(request.url)
    form_data = request.form()
    
    if not validator.validate(url, form_data, signature):
        logger.warning(f"Invalid Twilio signature from {request.client.host}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid Twilio signature")


def check_rate_limit(phone_number: str):
    """Check if the user has exceeded rate limits"""
    current_time = time.time()
    
    # Clean up old entries
    for num in list(RATE_LIMIT.keys()):
        if current_time - RATE_LIMIT[num]["timestamp"] > TIME_WINDOW:
            del RATE_LIMIT[num]
    
    if phone_number not in RATE_LIMIT:
        RATE_LIMIT[phone_number] = {"count": 10, "timestamp": current_time}
        return
    
    if RATE_LIMIT[phone_number]["count"] >= MAX_REQUESTS:
        logger.warning(f"Rate limit exceeded for {phone_number}")
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded")

    RATE_LIMIT[phone_number]["count"] += 1


@app.get("/health")
async def health_check():
    """Health check endpoint to verify the service is running"""
    return {"status": "healthy", "service": "rental-agreement-assistant"}


@app.get("/approved-numbers")
async def get_approved_numbers():
    """Return list of approved phone numbers (only for debugging)"""
    return {"approved_numbers": APPROVED_NUMBERS}


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all incoming HTTP requests"""
    logger.info(f"Request received: {request.method} {request.url.path}")
    try:
        # Try to log form data for POST requests
        if request.method == "POST" and "application/x-www-form-urlencoded" in request.headers.get("content-type", ""):
            form = await request.form()
            request.state.form_data = form  # store form data for later reuse
            logger.info(f"Form data: {dict(form)}")
    except:
        pass
    response = await call_next(request)
    return response


@app.get("/debug")
async def debug():
    """Test endpoint to verify server is responding"""
    logger.info("Debug endpoint called")
    return {"status": "online", "time": time.time()}


@app.post("/")
async def root_webhook(request: Request) -> PlainTextResponse:
    """Handle webhooks at the root path - Twilio is sending requests here"""
    try:
        # Use previously stored form data if available
        form_data = getattr(request.state, "form_data", None) or await request.form()
        form_dict = dict(form_data)
        
        # Extract message details with better error handling
        message_body = form_dict.get("Body", "").strip() if "Body" in form_dict else ""
        from_number = form_dict.get("From", "") if "From" in form_dict else ""
        
        # Debug log the entire request to see what we're getting
        logger.info(f"Webhook received with form data: {form_dict}")
        
        # Log the incoming message properly - make sure we're not truncating the from_number
        logger.info(f"Received message from '{from_number}': {message_body[:50]}...")
        
        # Note: Authorization check removed for testing
        normalized_from = normalize_phone_number(from_number) if from_number else ""
        logger.info(f"Normalized from: '{normalized_from}'")
        logger.info(f"Proceeding without authorization check")
            
        # Process the query
        try:
            # Pass the user's question to the query_agreement function
            result = await query_agreement(message_body)
            
            if isinstance(result, dict):
                if 'error' in result:
                    logger.error(f"Query engine error: {result['error']}")
                    response_text = "Sorry, I encountered an error while processing your query."
                elif 'answer' in result:
                    response_text = result['answer']
                    logger.info(f"Response generated: {response_text}...")
                else:
                    logger.error(f"Invalid response format: {result}")
                    response_text = "Sorry, I couldn't process your query. Please try again."
            else:
                logger.error(f"Invalid response type: {result}")
                response_text = "Sorry, I couldn't process your query. Please try again."
                
        except Exception as e:
            logger.error(f"Error processing query: {str(e)}")
            response_text = "Sorry, I encountered an error while processing your request."
            
        # Make sure the phone number is valid - more robust check
        if not from_number:
            logger.error("From number is missing in the request")
            return PlainTextResponse("Error: Missing recipient phone number", status_code=400)
            
        # Send WhatsApp response - make sure we have proper phone number format
        whatsapp_to = from_number  # Should already have whatsapp: prefix from Twilio
        whatsapp_from = f"whatsapp:{twilio_phone_number}" if not twilio_phone_number.startswith("whatsapp:") else twilio_phone_number
        
        # Log before sending
        logger.info(f"Sending message to '{whatsapp_to}' from '{whatsapp_from}'")
        
        # For additional debugging
        if not whatsapp_to.startswith("whatsapp:"):
            logger.warning(f"To number '{whatsapp_to}' does not have whatsapp: prefix, adding it")
            whatsapp_to = f"whatsapp:{whatsapp_to}"
            
        message = client.messages.create(
            body=response_text,
            from_=whatsapp_from,
            to=whatsapp_to
        )
        
        logger.info(f"Message sent with SID: {message.sid}")
        return PlainTextResponse(message.body)
    except Exception as e:
        logger.error(f"Root webhook error: {str(e)}", exc_info=True)  # Include full stack trace
        return PlainTextResponse(f"Error: {str(e)}", status_code=500)


if __name__ == "__main__":
    logger.info("Starting Rental Agreement Assistant Server")
    uvicorn.run("twilo_backend:app", host="0.0.0.0", port=8080, reload=True)
