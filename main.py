from fastapi import FastAPI, Header, HTTPException
import os, re, requests
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

API_KEY = os.getenv("API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

app = FastAPI()
sessions = {}

def detect_scam(text: str) -> bool:
    keywords = [
        "blocked", "verify", "upi", "urgent",
        "account", "suspend", "click", "link"
    ]
    return any(k in text.lower() for k in keywords)

def extract_intel(text: str):
    return {
        "upiIds": re.findall(r"[a-zA-Z0-9.\-_]{2,}@[a-zA-Z]{2,}", text),
        "phoneNumbers": re.findall(r"\+91\d{10}", text),
        "phishingLinks": re.findall(r"https?://\S+", text),
        "suspiciousKeywords": [
            k for k in ["urgent", "verify", "blocked", "suspend"]
            if k in text.lower()
        ]
    }

def agent_reply(history: str) -> str:
    prompt = f"""
You are a normal Indian user.
You are worried but polite.
You are not tech savvy.
You never accuse.
You ask innocent questions.
You delay giving information.
Never reveal suspicion.

Conversation:
{history}

Reply with ONE short message.
"""
    response = model.generate_content(prompt)
    return response.text.strip()

def send_callback(session_id, intel, total):
    payload = {
        "sessionId": session_id,
        "scamDetected": True,
        "totalMessagesExchanged": total,
        "extractedIntelligence": intel,
        "agentNotes": "Used urgency and payment redirection tactics"
    }
    try:
        requests.post(
            "https://hackathon.guvi.in/api/updateHoneyPotFinalResult",
            json=payload,
            timeout=5
        )
    except Exception:
        pass

@app.post("/message")
def message_handler(body: dict, x_api_key: str = Header(...)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")

    session_id = body["sessionId"]
    text = body["message"]["text"]

    sessions.setdefault(
        session_id,
        {"history": "", "intel": {}, "count": 0, "done": False}
    )

    s = sessions[session_id]
    s["count"] += 1
    s["history"] += f"\nScammer: {text}"

    if detect_scam(text):
        intel = extract_intel(text)
        for k, v in intel.items():
            s["intel"].setdefault(k, []).extend(v)

        reply = agent_reply(s["history"])
        s["history"] += f"\nUser: {reply}"

        if not s["done"] and (
            s["count"] >= 6
            or intel["upiIds"]
            or intel["phishingLinks"]
        ):
            send_callback(session_id, s["intel"], s["count"])
            s["done"] = True

        return {"status": "success", "reply": reply}

    return {"status": "success", "reply": "Okay"}
