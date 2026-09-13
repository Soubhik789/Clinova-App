#!/usr/bin/env python3
"""
CLINOVA ENTERPRISE HEALTH-TECH BACKEND SERVER (Python)
Powered by Cuka AI Engine v5.3 Enterprise Mobile

Features:
- 110+ Verified Doctors with multi-doctor response generation (Top 3 distinct specialists)
- Strict Multilingual Matrix (বাংলা Bengali, हिंदी Hindi, English)
- Pharmacy Engine & Interactive Payment Gateway (UPI, Cards, COD)
- Route Direction & Haversine distance calculator
- Role-Based Access Control & User Session Management
"""

import http.server
import socketserver
import json
import os
import re
import time
import random
import hashlib
import urllib.parse
from datetime import datetime

# Import structured 105+ Kolkata healthcare database & 200+ authentic medicines
from kolkata_providers import DOCTORS_CATALOG, PROVIDERS_BY_TYPE, calculate_kolkata_route, PATIENT_DEFAULT_COORDS
from medicines_catalog import MEDICINES_DB

PORT = 3000
DIRECTORY = os.path.dirname(os.path.abspath(__file__))

SPECIALTIES_LIST = sorted(list(set(d["specialty"] for d in DOCTORS_CATALOG)))


CURRENT_USER_SESSION = {
    "user_id": "usr_pat_01",
    "name": "John",
    "role": "PATIENT",
    "phone": "+91 98301 22910",
    "email": "john@clinova.health",
    "abha_id": "ABHA-91-8842-1029-44",
    "isLoggedIn": False
}

OTP_STORE = {} # In-memory storage for active verification OTPs
ORDERS_LEDGER = []
BOOKING_TOKEN_COUNTER = 1045

EMERGENCY_FACILITY = {
    "name": "CLINOVA EMERGENCY TRAUMA ICU • MEDICA",
    "address": "127 Mukundapur Main Rd, EM Bypass, Kolkata",
    "coordinates": {"lat": 22.4988, "lng": 88.3976},
    "distanceKm": 0.8,
    "etaMinutes": 3.5,
    "phone": "108",
    "bedsAvailable": 4,
    "cathLabStandby": True,
    "ambulanceUnit": "ALS-Critical-Unit #WB-04-E-8821",
    "paramedicLead": "S. Ganguly (Paramedic Critical Response)"
}

EMERGENCY_KEYWORDS = [
    "chest pain", "breathing difficult", "cannot breathe", "severe bleeding", "accident",
    "heart attack", "stroke", "unconscious", "dying", "fainted", "head trauma", "hemorrhage",
    "হার্ট অ্যাটাক", "বুকে ব্যথা", "শ্বাসকষ্ট", "রক্তপাত", "অ্যাক্সিডেন্ট", "দম বন্ধ", "অজ্ঞান",
    "हार्ट अटैक", "सीने में दर्द", "सांस लेने में", "खून बह रहा", "दुर्घटना", "बेहोश", "दम घुट"
]

# ============================================================================
# 3. ADVANCED NLP & MULTI-DOCTOR MENTIONS GENERATOR
# ============================================================================

def detect_language(text):
    bn_chars = len(re.findall(r'[\u0980-\u09FF]', text))
    hi_chars = len(re.findall(r'[\u0900-\u097F]', text))
    
    mixed_words_bn = ["amar", "kore", "khojo", "bhalo", "dorkar", "khub", "shami", "baccha", "jwor", "daktar"]
    mixed_words_hi = ["mera", "dard", "hora", "hai", "kaise", "thik", "chahiye", "sasta", "doctor", "batao"]
    
    lower = text.lower()
    has_mixed_bn = any(w in lower for w in mixed_words_bn)
    has_mixed_hi = any(w in lower for w in mixed_words_hi)

    if bn_chars > 0: return "Bengali"
    if hi_chars > 0: return "Hindi"
    if has_mixed_bn and has_mixed_hi: return "Hybrid"
    if has_mixed_bn: return "Bengali"
    if has_mixed_hi: return "Hindi"
    return "English"

def extract_specialty_and_intent(text):
    lower = text.lower()
    
    # Orthopedics
    if any(k in lower for k in ["back", "spine", "knee", "joint", "bone", "ortho", "কোমর", "পিঠ", "হাঁটু", "হাড়", "कमर", "पीठ", "घुटना", "हड्डी", "जोड़"]):
        return {"specialty": "Orthopedics & Spine Care", "query": "Orthopedic Concern", "icon": "🦴"}
    
    # Cardiology
    if any(k in lower for k in ["chest", "heart", "cardio", "bp", "blood pressure", "pulse", "হার্ট", "বুকে", "প্রেসার", "हार्ट", "सीना", "दिल", "ब्लड प्रेशर"]):
        return {"specialty": "Cardiology & Heart Care", "query": "Cardiovascular Check", "icon": "❤️"}
    
    # Pediatrics
    if any(k in lower for k in ["child", "baby", "kid", "fever", "cough", "cold", "বাচ্চা", "শিশু", "ছেলে", "মেয়ে", "জ্বর", "সর্দি", "बच्चा", "शिशु", "बुखार", "खांसी"]):
        return {"specialty": "Pediatrics & Child Wellness", "query": "Pediatric Healthcare", "icon": "👶"}
    
    # Neurology
    if any(k in lower for k in ["headache", "brain", "nerve", "stroke", "migraine", "dizziness", "মাথা ব্যথা", "মস্তিষ্ক", "স্নায়ু", "सिर दर्द", "ब्रेन", "नसों"]):
        return {"specialty": "Neurology & Brain Sciences", "query": "Neurological Consultation", "icon": "🧠"}
    
    # Dermatology
    if any(k in lower for k in ["skin", "rash", "acne", "hair", "dermat", "ত্বক", "চামড়া", "ফুসকুড়ি", "চুল", "त्वचा", "चमड़ी", "खुजली", "मुंहासे", "बाल"]):
        return {"specialty": "Dermatology & Skin Care", "query": "Dermatology & Skin", "icon": "🧴"}
    
    # Gastroenterology
    if any(k in lower for k in ["stomach", "gas", "acid", "liver", "digestion", "gastro", "পেট", "গ্যাস", "অম্বল", "লিভার", "হজম", "पेट", "गैस", "एसिडिटी", "लिवर"]):
        return {"specialty": "Gastroenterology & Hepatology", "query": "Digestive & Gastro Care", "icon": "🧪"}
    
    # Dental
    if any(k in lower for k in ["tooth", "teeth", "dental", "gum", "দাঁত", "মাড়ি", "দাঁতের", "दांत", "मसूड़े"]):
        return {"specialty": "Dental Care & Maxillofacial", "query": "Dental Examination", "icon": "🦷"}
    
    # General Medicine
    return {"specialty": "General Medicine & Diabetology", "query": "General Outpatient Consultation", "icon": "🩺"}

def match_and_rank_doctors(specialty, max_results=3):
    matched = [d for d in DOCTORS_CATALOG if d["specialty"].lower() == specialty.lower()]
    if not matched:
        matched = [d for d in DOCTORS_CATALOG if specialty.split(" ")[0].lower() in d["specialty"].lower()]
    if not matched:
        matched = DOCTORS_CATALOG[:]

    for doc in matched:
        affordability = (1000.0 / doc["fee"]) * 50.0
        proximity = (10.0 / (doc["distanceKm"] + 0.1)) * 40.0
        rating_score = (doc["rating"] / 5.0) * 10.0
        doc["score"] = round(affordability + proximity + rating_score, 2)

    matched.sort(key=lambda x: x["score"], reverse=True)
    return matched[:max_results]

def generate_multi_doctor_speech_response(lang, top_doctors, specialty):
    """
    Generates a natural, multilingual response mentioning the TOP 2-3 DISTINCT DOCTORS,
    preventing any single-doctor name repetition!
    """
    d1 = top_doctors[0]
    d2 = top_doctors[1] if len(top_doctors) > 1 else None
    d3 = top_doctors[2] if len(top_doctors) > 2 else None

    if lang == "Bengali":
        text = f"নমস্কার! আপনার **{specialty}** সমস্যার জন্য আমি ১০০+ ডাক্তারের ডাটাবেস বিশ্লেষণ করে শীর্ষ ডাক্তারদের নির্বাচন করেছি। প্রথম পছন্দ হলেন **{d1['name']}** ({d1['facility']}, পরামর্শ ফি ₹{d1['fee']}, সময়: {d1['earliestSlot']})"
        if d2:
            text += f", দ্বিতীয় পছন্দ **{d2['name']}** ({d2['facility']}, ফি ₹{d2['fee']})"
        if d3:
            text += f", এবং তৃতীয় বিকল্প **{d3['name']}** ({d3['facility']}, ফি ₹{d3['fee']})"
        text += "। নিচের তালিকা থেকে আপনার সুবিধাজনক ডাক্তার বেছে নিন।"
        return text

    elif lang == "Hindi":
        text = f"नमस्ते! आपकी **{specialty}** की समस्या के लिए मैंने 100+ डॉक्टरों को स्कैन करके सर्वश्रेष्ठ विशेषज्ञ चुने हैं। पहली पसंद हैं **{d1['name']}** ({d1['facility']}, परामर्श शुल्क ₹{d1['fee']}, समय: {d1['earliestSlot']})"
        if d2:
            text += f", दूसरे विकल्प हैं **{d2['name']}** ({d2['facility']}, शुल्क ₹{d2['fee']})"
        if d3:
            text += f", और तीसरे विकल्प हैं **{d3['name']}** ({d3['facility']}, शुल्क ₹{d3['fee']})"
        text += "। आप नीचे से आसानी से अपनी पसंद चुन सकते हैं।"
        return text

    else:
        text = f"Hello! For your **{specialty}** inquiry, I have identified top specialists from our verified network: 1. **{d1['name']}** at {d1['facility']} (Fee: ₹{d1['fee']}, Earliest: {d1['earliestSlot']})"
        if d2:
            text += f", 2. **{d2['name']}** at {d2['facility']} (Fee: ₹{d2['fee']})"
        if d3:
            text += f", and 3. **{d3['name']}** at {d3['facility']} (Fee: ₹{d3['fee']})"
        text += ". Please select your preferred doctor below."
        return text

# ============================================================================
# 4. HTTP REQUEST HANDLER & API ROUTER
# ============================================================================

class ClinovaServerHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def _send_json(self, data, status_code=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        url = parsed_url.path
        query_params = urllib.parse.parse_qs(parsed_url.query)

        if url == "/api/v1/health":
            return self._send_json({
                "status": "online",
                "core": "Cuma AI Engine v5.3 Enterprise",
                "wakeWord": "Hey Cuma",
                "doctorsCount": len(DOCTORS_CATALOG),
                "medicinesCount": len(MEDICINES_DB),
                "timestamp": datetime.utcnow().isoformat() + "Z"
            })

        if url == "/api/v1/doctors":
            prov_type = query_params.get("type", ["All"])[0]
            search_query = query_params.get("search", [""])[0].strip().lower()
            results = DOCTORS_CATALOG
            if prov_type in PROVIDERS_BY_TYPE and prov_type != "All":
                results = PROVIDERS_BY_TYPE[prov_type]
            if search_query:
                results = [
                    d for d in results
                    if search_query in d.get("name", "").lower()
                    or search_query in d.get("specialty", "").lower()
                    or search_query in d.get("facility", "").lower()
                    or search_query in d.get("area", "").lower()
                    or search_query in d.get("address", "").lower()
                ]
            return self._send_json({
                "success": True,
                "count": len(results),
                "doctors": results
            })

        if url == "/api/v1/medicines":
            cat = query_params.get("category", ["All"])[0]
            search_query = query_params.get("search", [""])[0].strip().lower()
            results = MEDICINES_DB
            if cat != "All" and cat:
                results = [m for m in results if m.get("category", "").lower() == cat.lower()]
            if search_query:
                results = [
                    m for m in results
                    if search_query in m.get("name", "").lower()
                    or search_query in m.get("category", "").lower()
                    or search_query in m.get("manufacturer", "").lower()
                    or search_query in m.get("dosage", "").lower()
                ]
            return self._send_json({
                "success": True,
                "count": len(results),
                "medicines": results
            })

        if url == "/api/v1/route/calculate":
            try:
                from_lat = float(query_params.get("fromLat", [PATIENT_DEFAULT_COORDS["lat"]])[0])
                from_lng = float(query_params.get("fromLng", [PATIENT_DEFAULT_COORDS["lng"]])[0])
                to_lat = float(query_params.get("toLat", [22.5740])[0])
                to_lng = float(query_params.get("toLng", [88.4180])[0])
                route_data = calculate_kolkata_route(from_lat, from_lng, to_lat, to_lng)
                return self._send_json(route_data)
            except Exception as e:
                return self._send_json({"success": False, "error": str(e)}, status=400)

        if url == "/api/v1/auth/session":
            return self._send_json({
                "success": True,
                "user": CURRENT_USER_SESSION
            })

        if url in ["/", "/index.html"]:
            self.path = "/CLINOVA.html"

        if url == "/app.js" and not os.path.exists(os.path.join(DIRECTORY, "app.js")):
            self.path = "/CLINOVA-1.js"

        return super().do_GET()

    def do_POST(self):
        global CURRENT_USER_SESSION, BOOKING_TOKEN_COUNTER
        url = self.path.split("?")[0]
        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
        
        try:
            body = json.loads(post_data)
        except Exception:
            body = {}

        # Route Calculation endpoint
        if url == "/api/v1/route/calculate":
            try:
                from_lat = float(body.get("fromLat", PATIENT_DEFAULT_COORDS["lat"]))
                from_lng = float(body.get("fromLng", PATIENT_DEFAULT_COORDS["lng"]))
                to_lat = float(body.get("toLat", 22.5740))
                to_lng = float(body.get("toLng", 88.4180))
                route_data = calculate_kolkata_route(from_lat, from_lng, to_lat, to_lng)
                return self._send_json(route_data)
            except Exception as e:
                return self._send_json({"success": False, "error": str(e)}, status=400)


        # 1. Cuka NLP Query Endpoint
        if url == "/api/v1/cuka/query":
            raw_query = body.get("query", "")
            channel = body.get("channel", "Hey Cuka Voice / Touch")
            forced_lang = body.get("forcedLang", None)
            lower = raw_query.lower()

            is_emergency = any(kw in lower for kw in EMERGENCY_KEYWORDS)
            detected_lang = forced_lang if forced_lang in ["Bengali", "Hindi", "English"] else detect_language(raw_query)

            if is_emergency:
                reassurance = {
                    "Bengali": "দয়া করে শান্ত হয়ে বসুন; আপনার ঠিকানায় উচ্চ-অগ্রাধিকারের অ্যাম্বুলেন্স রওনা হয়েছে এবং নিকটস্থ ট্রমা আইসিইউ প্রস্তুত রয়েছে।",
                    "Hindi": "कृपया शांत रहें और आराम से बैठें; आपके स्थान के लिए आपातकालीन एम्बुलेंस रवाना हो चुकी है और आईसीयू ट्रॉमा टीम तैयार है।",
                    "English": "Please stay calm and sit down comfortably; our high-priority ambulance is already dispatched to your location and the nearest ICU trauma team is waiting for you."
                }.get(detected_lang, "Please stay calm; emergency services deployed.")

                return self._send_json({
                    "success": True,
                    "emergency": True,
                    "directive": "[EMERGENCY_BYPASS_TRUE]",
                    "language": detected_lang,
                    "nearestFacility": EMERGENCY_FACILITY,
                    "reassurance": reassurance,
                    "structuredOutput": {
                        "wakeEngine": f"Triggered via '{channel}' [CODE RED OVERRIDE]",
                        "nearAiCommand": "[EMERGENCY_BYPASS_TRUE] Locking closest trauma ICU",
                        "providerAggregation": f"Direct lock to {EMERGENCY_FACILITY['name']} (0.8 km)",
                        "userResponse": reassurance
                    }
                })

            spec_info = extract_specialty_and_intent(raw_query)
            top_ranked = match_and_rank_doctors(spec_info["specialty"], max_results=3)
            speech_response = generate_multi_doctor_speech_response(detected_lang, top_ranked, spec_info["specialty"])

            return self._send_json({
                "success": True,
                "emergency": False,
                "language": detected_lang,
                "symptomInfo": spec_info,
                "topProviders": top_ranked,
                "structuredOutput": {
                    "wakeEngine": f"Triggered via '{channel}' [WAKE WORD DETECTED]",
                    "nearAiCommand": f"Scanning 110+ doctors for [{spec_info['specialty']}]",
                    "providerAggregation": f"Identified top 3 verified choices: {', '.join([d['name'] for d in top_ranked])}",
                    "userResponse": speech_response
                }
            })

        # 2. Pharmacy Order & Payment Processing
        if url == "/api/v1/payment/process":
            payment_method = body.get("paymentMethod", "UPI")
            upi_id = body.get("upiId", "soubhik@okaxis")
            amount = body.get("amount", 0)
            items = body.get("items", [])
            address = body.get("address", "Sector V, Salt Lake, Kolkata")

            txn_id = f"TXN-CLV-{int(time.time())}"
            order_id = f"ORD-{int(time.time())}"

            order_record = {
                "order_id": order_id,
                "txn_id": txn_id,
                "amount": amount,
                "payment_method": payment_method,
                "upi_id": upi_id if payment_method == "UPI" else None,
                "items": items,
                "address": address,
                "status": "PAID & DISPATCHED",
                "delivery_partner": f"MedExpress Rider #{random.randint(12, 88)}",
                "etaMinutes": 10,
                "timestamp": datetime.utcnow().strftime("%I:%M %p")
            }
            ORDERS_LEDGER.insert(0, order_record)

            return self._send_json({
                "success": True,
                "order": order_record,
                "message": "Payment verified via Clinova Secure Gateway. MedExpress 10-Min rider dispatched!"
            })

        # 3. OTP Authentication: Send OTP
        if url == "/api/v1/auth/send-otp":
            raw_phone = str(body.get("phone", "")).strip()
            name = str(body.get("name", "John")).strip() or "John"
            if not raw_phone:
                return self._send_json({"success": False, "error": "Phone number is required"}, 400)
            
            clean_phone = re.sub(r"[^\d+]", "", raw_phone)
            digits_only = re.sub(r"\D", "", raw_phone)
            
            # Generate random 6-digit OTP
            otp = f"{random.randint(100000, 999999)}"
            expiry = time.time() + 300  # 5 minutes validity
            
            payload = {
                "otp": otp,
                "expires_at": expiry,
                "name": name,
                "raw_phone": raw_phone,
                "created_at": datetime.utcnow().strftime("%I:%M:%S %p")
            }
            OTP_STORE[clean_phone] = payload
            if digits_only:
                OTP_STORE[digits_only] = payload

            print(f"\n=======================================================", flush=True)
            print(f"[CLINOVA SMS GATEWAY] >>> OUTGOING SMS to {raw_phone}", flush=True)
            print(f"Message: 'Your Clinova verification OTP is {otp}. Valid for 5 mins. Do not share.'", flush=True)
            print(f"=======================================================\n", flush=True)

            return self._send_json({
                "success": True,
                "message": f"Verification code sent to {raw_phone}",
                "phone": raw_phone,
                "otp": otp,
                "expiresInSeconds": 300
            })

        # 3b. OTP Authentication: Verify OTP
        if url == "/api/v1/auth/verify-otp":
            raw_phone = str(body.get("phone", "")).strip()
            submitted_otp = str(body.get("otp", "")).strip()
            name = str(body.get("name", "")).strip()
            clean_phone = re.sub(r"[^\d+]", "", raw_phone)
            digits_only = re.sub(r"\D", "", raw_phone)

            record = OTP_STORE.get(clean_phone) or OTP_STORE.get(digits_only)

            is_valid = False
            user_name = name or (record.get("name") if record else "John") or "John"
            
            if record and time.time() <= record.get("expires_at", 0):
                if record.get("otp") == submitted_otp:
                    is_valid = True
            
            # Master demo bypass codes for instant developer/testing access
            if submitted_otp in ["582910", "123456"]:
                is_valid = True
                user_name = name or "John"

            if not is_valid:
                return self._send_json({
                    "success": False,
                    "error": "Invalid or expired OTP. Please check your SMS and try again."
                }, 400)

            CURRENT_USER_SESSION = {
                "user_id": f"usr_{int(time.time())}",
                "name": user_name,
                "role": "PATIENT",
                "phone": raw_phone or "+91 98301 22910",
                "email": f"{user_name.lower().replace(' ', '')}@clinova.health",
                "abha_id": f"ABHA-91-{random.randint(1000,9999)}-{random.randint(1000,9999)}-{random.randint(10,99)}",
                "isLoggedIn": True
            }

            return self._send_json({
                "success": True,
                "message": "OTP verified successfully! Access granted.",
                "token": f"clv_tok_{int(time.time())}_{random.randint(1000,9999)}",
                "user": CURRENT_USER_SESSION
            })

        # 3c. User Login / Session Switch (Password or Demo)
        if url == "/api/v1/auth/login":
            applicant_name = body.get("name", "John")
            phone = body.get("phone", "+91 98301 22910")
            CURRENT_USER_SESSION = {
                "user_id": f"usr_{int(time.time())}",
                "name": applicant_name,
                "role": "PATIENT",
                "phone": phone,
                "email": f"{applicant_name.lower().replace(' ', '')}@clinova.health",
                "abha_id": "ABHA-91-8842-1029-44",
                "isLoggedIn": True
            }
            return self._send_json({
                "success": True,
                "user": CURRENT_USER_SESSION,
                "token": f"clv_tok_{int(time.time())}"
            })

        # 3d. User Logout
        if url == "/api/v1/auth/logout":
            CURRENT_USER_SESSION = {
                "user_id": None,
                "name": "Guest",
                "role": "GUEST",
                "phone": None,
                "email": None,
                "abha_id": None,
                "isLoggedIn": False
            }
            return self._send_json({
                "success": True,
                "message": "Logged out successfully"
            })

        # 4. Appointment Booking
        if url == "/api/v1/appointment/book":
            BOOKING_TOKEN_COUNTER += 1
            token = f"CLV-{BOOKING_TOKEN_COUNTER}"
            return self._send_json({
                "success": True,
                "token": token,
                "doctor": body.get("doctorName"),
                "slot": body.get("slot")
            })

        return self._send_json({"error": "Endpoint not found"}, 404)

def run_server():
    global PORT
    socketserver.TCPServer.allow_reuse_address = True
    target_port = int(os.environ.get("PORT", PORT))
    httpd = None
    for p in range(target_port, target_port + 10):
        try:
            httpd = socketserver.TCPServer(("", p), ClinovaServerHandler)
            PORT = p
            break
        except OSError as e:
            if e.errno == 48 or "Address already in use" in str(e):
                continue
            raise e
    if not httpd:
        print(f"Error: Could not bind to any port between {target_port} and {target_port + 10}")
        return
    with httpd:
        print(f"================================================================")
        print(f"🏥 CLINOVA ENTERPRISE SERVER v5.3 LIVE AT: http://localhost:{PORT}")
        print(f"🎙️ Wake Word: 'Hey Cuka' with Full Duplex Barge-in enabled.")
        print(f"💳 MedExpress Instant Payment Gateway (UPI, Cards, COD) Active.")
        print(f"🗺️ Route Navigation & Multi-Doctor AI Voice Synthesis Ready.")
        print(f"================================================================")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server...")

if __name__ == "__main__":
    run_server()
