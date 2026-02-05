from fastapi import FastAPI, Header, HTTPException
import os, re, requests
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

API_KEY = os.getenv("API_KEY")
app = FastAPI()

sessions = {}

def detect_scam(text):
    keywords = ["blocked", "verify", "upi", "urgent", "account"]
    return any(k in text.lower() for k in keywords)

def extract_intel(text):
    return {
        "upiIds": re.findall(r"[a-zA-Z0-9.\-_]{2,}@[a-zA-Z]{2,}", text),
        "phoneNumbers": re.findall(r"\+91\d{10}", text),
        "phishingLinks": re.findall(r"https?://\S+", text),
        "suspiciousKeywords": [k for k in ["urgent","verify","blocked"] if k in text.lower()]
    }

def agent_reply(history):
    prompt = f"""
You are a worried Indian user.
You are polite and not tech savvy.
Ask innocent questions.
Conversation so far:
{history}
Reply with one short message.
"""
    res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role":"user","content":prompt}]
    )
    return res.choices[0].message.content

def send_callback(session_id, intel, total):
    payload = {
        "sessionId": session_id,
        "scamDetected": True,
        "totalMessagesExchanged": total,
        "extractedIntelligence": intel,
        "agentNotes": "Urgency and payment redirection observed"
    }
    try:
        requests.post(
            "https://hackathon.guvi.in/api/updateHoneyPotFinalResult",
            json=payload,
            timeout=5
        )
    except:
        pass

@app.post("/message")
def message_handler(body: dict, x_api_key: str = Header(...)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401)

    session_id = body["sessionId"]
    text = body["message"]["text"]

    sessions.setdefault(session_id, {"history": "", "intel": {}, "count": 0})
    s = sessions[session_id]

    s["count"] += 1
    s["history"] += f"\nScammer: {text}"

    if detect_scam(text):
        intel = extract_intel(text)
        for k, v in intel.items():
            s["intel"].setdefault(k, []).extend(v)

        reply = agent_reply(s["history"])
        s["history"] += f"\nUser: {reply}"

        if s["count"] >= 6 or intel["upiIds"] or intel["phishingLinks"]:
            send_callback(session_id, s["intel"], s["count"])

        return {"status": "success", "reply": reply}

    return {"status": "success", "reply": "Okay"}
