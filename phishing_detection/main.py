from huggingface_hub import InferenceClient
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
load_dotenv()

class PhishingRequest(BaseModel):
    text: str

class PhishingResponse(BaseModel):
    text: str
    label: str
    confidence: float
    is_phishing: bool
    message: str

app = FastAPI(
    title="Phishing Detection API",
    description="API for detecting phishing attempts in text messages and emails",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = None

def initialize_client():
    """Initialize the HuggingFace client"""
    global client
    try:
        client = InferenceClient(
            provider="auto",
        )
        return True
    except Exception as e:
        print(f"Error initializing model: {e}")
        return False

def analyze_text(text, client):
    """Analyze a single text for phishing"""
    try:
        result = client.text_classification(
            text,
            model="ealvaradob/bert-finetuned-phishing",
        )
        
        classification = result[0]
        label = classification['label']
        confidence = classification['score']
        
        return {
            'label': label,
            'confidence': confidence,
            'is_phishing': label.lower() == 'phishing'
        }
    except Exception as e:
        print(f"Error analyzing text: {e}")
        return None

@app.on_event("startup")
async def startup_event():
    """Initialize the model when the app starts"""
    if not initialize_client():
        raise Exception("Failed to initialize the phishing detection model")

@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "message": "Phishing Detection API",
        "version": "1.0.0",
        "endpoints": {
            "/": "API information",
            "/detect": "POST - Detect phishing in text",
            "/health": "GET - Health check"
        }
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "model_loaded": client is not None
    }

@app.post("/detect", response_model=PhishingResponse)
async def detect_phishing(request: PhishingRequest):
    """Detect phishing in the provided text"""
    if client is None:
        raise HTTPException(status_code=500, detail="Model not initialized")
    
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")
    
    result = analyze_text(request.text, client)
    
    if result is None:
        raise HTTPException(status_code=500, detail="Failed to analyze text")
    
    if result['is_phishing']:
        message = f"PHISHING DETECTED! Confidence: {result['confidence']:.2%}. This text appears to be a phishing attempt."
    else:
        message = f"SAFE. Confidence: {result['confidence']:.2%}. This text appears to be legitimate."
    
    return PhishingResponse(
        text=request.text,
        label=result['label'],
        confidence=result['confidence'],
        is_phishing=result['is_phishing'],
        message=message
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, port=8080)