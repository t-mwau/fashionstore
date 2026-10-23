import base64
import json
import os
import re
import threading
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parent
CATALOG = json.loads((ROOT / "products.json").read_text(encoding="utf-8"))
PRODUCTS_BY_ID = {product["id"]: product for product in CATALOG}
CHECKOUTS = {}
CHECKOUTS_LOCK = threading.Lock()
MAX_REQUEST_BYTES = 16_384
PHONE_PATTERN = re.compile(r"^(?:254|0)(?:7|1)\d{8}$")
CHECKOUT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{5,100}$")
MPESA_API = "https://sandbox.safaricom.co.ke"


def json_response(handler, status, payload):
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def missing_mpesa_settings():
    required = (
        "MPESA_CONSUMER_KEY",
        "MPESA_CONSUMER_SECRET",
        "MPESA_SHORTCODE",
        "MPESA_PASSKEY",
        "MPESA_CALLBACK_URL",
    )
    missing = [name for name in required if not os.environ.get(name)]
    if os.environ.get("MPESA_ENV", "sandbox").lower() != "sandbox":
        missing.append("MPESA_ENV must be sandbox")
    callback = os.environ.get("MPESA_CALLBACK_URL", "")
    parsed_callback = urlsplit(callback)
    if callback and (
        parsed_callback.scheme != "https"
        or not parsed_callback.path.endswith("/api/mpesa/callback")
    ):
        missing.append("MPESA_CALLBACK_URL must be an HTTPS URL ending in /api/mpesa/callback")
    return missing


def mpesa_request(url, payload=None, headers=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(url, data=data, headers=headers or {}, method="GET" if data is None else "POST")
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


class UrbanWearHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def translate_path(self, path):
        requested = urlsplit(path).path
        if requested == "/":
            requested = "/index.html"
        if requested in ("/index.html", "/style.css", "/script.js", "/products.json"):
            return str(ROOT / requested.lstrip("/"))
        if re.fullmatch(r"/bootstrap/(?:css|js)/[A-Za-z0-9._-]+\.(?:css|js)", requested):
            target = (ROOT / requested.lstrip("/")).resolve()
            if target.is_relative_to(ROOT / "bootstrap"):
                return str(target)
        if re.fullmatch(r"/images/image(?:[0-9]|1[0-9]|2[0-4]|2[6-9]|3[0-9]|40)\.png", requested):
            target = (ROOT / requested.lstrip("/")).resolve()
            if target.is_relative_to(ROOT / "images"):
                return str(target)
        return str(ROOT / "__not_found__")

    def list_directory(self, path):
        self.send_error(404, "Directory listings are disabled.")
        return None

    def do_GET(self):
        parsed = urlsplit(self.path)
        if parsed.path == "/api/mpesa/status":
            checkout_id = parse_qs(parsed.query).get("checkoutRequestID", [""])[0]
            if not CHECKOUT_ID_PATTERN.fullmatch(checkout_id):
                json_response(self, 400, {"error": "A valid sandbox checkout ID is required."})
                return
            with CHECKOUTS_LOCK:
                checkout = CHECKOUTS.get(checkout_id)
            if checkout is None:
                json_response(self, 404, {"error": "Sandbox checkout not found. Restarting the server clears pending test checkouts."})
                return
            self._verify_callback_if_ready(checkout_id)
            with CHECKOUTS_LOCK:
                checkout = CHECKOUTS[checkout_id]
                public_status = {"status": checkout["status"], "message": checkout["message"]}
            json_response(self, 200, public_status)
            return
        if parsed.path.startswith("/api/"):
            json_response(self, 404, {"error": "API endpoint not found."})
            return
        if self.translate_path(self.path).endswith("__not_found__"):
            self.send_error(404, "File not found.")
            return
        super().do_GET()

    def do_POST(self):
        parsed = urlsplit(self.path)
        if parsed.path not in ("/api/mpesa/stkpush", "/api/mpesa/callback"):
            json_response(self, 404, {"error": "API endpoint not found."})
            return
        if parsed.path == "/api/mpesa/stkpush" and not self._same_origin():
            json_response(self, 403, {"error": "Cross-origin checkout requests are not allowed."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            json_response(self, 400, {"error": "Invalid request length."})
            return
        if length <= 0 or length > MAX_REQUEST_BYTES:
            json_response(self, 413, {"error": "Request body must be between 1 byte and 16 KB."})
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            json_response(self, 400, {"error": "Request body must contain valid JSON."})
            return
        if not isinstance(payload, dict):
            json_response(self, 400, {"error": "Request body must be a JSON object."})
            return

        if parsed.path == "/api/mpesa/callback":
            self._handle_callback(payload)
        else:
            self._handle_stk_push(payload)

    def _same_origin(self):
        origin = self.headers.get("Origin")
        if not origin:
            return True
        parsed_origin = urlsplit(origin)
        return (
            parsed_origin.scheme in ("http", "https")
            and parsed_origin.netloc == self.headers.get("Host")
        )

    def _handle_stk_push(self, payload):
        missing = missing_mpesa_settings()
        if missing:
            json_response(self, 503, {
                "error": "M-Pesa sandbox checkout is not configured. Set the required server environment variables: "
                + ", ".join(missing)
                + ". A public HTTPS callback URL is required."
            })
            return
        phone = payload.get("phone")
        if not isinstance(phone, str):
            json_response(self, 400, {"error": "Enter a valid Kenyan M-Pesa phone number."})
            return
        digits = re.sub(r"[\s+()-]", "", phone)
        if digits.startswith("0"):
            digits = "254" + digits[1:]
        if not PHONE_PATTERN.fullmatch(digits):
            json_response(self, 400, {"error": "Phone number must be a Kenyan 07XXXXXXXX, 01XXXXXXXX, or 254XXXXXXXXX number."})
            return

        items = payload.get("items")
        if not isinstance(items, list) or not items or len(items) > len(PRODUCTS_BY_ID):
            json_response(self, 400, {"error": "Your cart is empty or invalid."})
            return
        total = 0
        seen_ids = set()
        for item in items:
            if not isinstance(item, dict):
                json_response(self, 400, {"error": "Cart items must include a product ID and quantity."})
                return
            product_id = item.get("id")
            quantity = item.get("quantity")
            if (
                not isinstance(product_id, int)
                or isinstance(product_id, bool)
                or product_id not in PRODUCTS_BY_ID
                or not isinstance(quantity, int)
                or isinstance(quantity, bool)
                or quantity < 1
                or quantity > 20
                or product_id in seen_ids
            ):
                json_response(self, 400, {"error": "Cart contains an invalid product or quantity."})
                return
            seen_ids.add(product_id)
            total += PRODUCTS_BY_ID[product_id]["price"] * quantity
        if total > 150_000:
            json_response(self, 400, {"error": "Sandbox checkout total cannot exceed KSh 150,000."})
            return

        timestamp = datetime.now(ZoneInfo("Africa/Nairobi")).strftime("%Y%m%d%H%M%S")
        shortcode = os.environ["MPESA_SHORTCODE"]
        password = base64.b64encode(
            f"{shortcode}{os.environ['MPESA_PASSKEY']}{timestamp}".encode("utf-8")
        ).decode("ascii")
        credentials = base64.b64encode(
            f"{os.environ['MPESA_CONSUMER_KEY']}:{os.environ['MPESA_CONSUMER_SECRET']}".encode("utf-8")
        ).decode("ascii")
        try:
            token_response = mpesa_request(
                f"{MPESA_API}/oauth/v1/generate?grant_type=client_credentials",
                headers={"Authorization": f"Basic {credentials}"},
            )
            access_token = token_response.get("access_token")
            if not access_token:
                json_response(self, 502, {"error": "M-Pesa sandbox did not return an access token. Check the server credentials."})
                return
            stk_response = mpesa_request(
                f"{MPESA_API}/mpesa/stkpush/v1/processrequest",
                payload={
                    "BusinessShortCode": shortcode,
                    "Password": password,
                    "Timestamp": timestamp,
                    "TransactionType": "CustomerPayBillOnline",
                    "Amount": total,
                    "PartyA": digits,
                    "PartyB": shortcode,
                    "PhoneNumber": digits,
                    "CallBackURL": os.environ["MPESA_CALLBACK_URL"],
                    "AccountReference": "UrbanWear",
                    "TransactionDesc": "UrbanWear",
                },
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
            )
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as error:
            print(f"M-Pesa sandbox request failed: {type(error).__name__}")
            json_response(self, 502, {"error": "Could not reach the M-Pesa sandbox. Check your credentials and try again."})
            return

        checkout_id = stk_response.get("CheckoutRequestID")
        if stk_response.get("ResponseCode") != "0" or not checkout_id:
            message = stk_response.get("ResponseDescription") or stk_response.get("errorMessage")
            json_response(self, 502, {"error": message or "M-Pesa sandbox rejected the checkout request."})
            return
        with CHECKOUTS_LOCK:
            CHECKOUTS[checkout_id] = {
                "status": "pending",
                "message": "Sandbox payment prompt sent. Check the test phone and approve the prompt.",
                "amount": total,
                "callback_received": False,
                "verification_started": False,
                "last_verified_at": 0,
            }
        json_response(self, 200, {
            "checkoutRequestID": checkout_id,
            "message": "Sandbox payment prompt sent. Check the test phone and approve the prompt.",
        })

    def _handle_callback(self, payload):
        try:
            callback = payload["Body"]["stkCallback"]
            checkout_id = callback["CheckoutRequestID"]
            result_code = callback["ResultCode"]
        except (KeyError, TypeError):
            json_response(self, 400, {"error": "Invalid M-Pesa callback body."})
            return
        if not isinstance(checkout_id, str) or not CHECKOUT_ID_PATTERN.fullmatch(checkout_id):
            json_response(self, 400, {"error": "Invalid sandbox checkout ID."})
            return
        with CHECKOUTS_LOCK:
            checkout = CHECKOUTS.get(checkout_id)
            if checkout is not None:
                checkout["callback_received"] = True
                checkout["callback_result_code"] = result_code
                checkout["message"] = "Payment callback received. Verifying the transaction with the M-Pesa sandbox."
        json_response(self, 200, {"ResultCode": 0, "ResultDesc": "Accepted"})

    def _verify_callback_if_ready(self, checkout_id):
        now = datetime.now(timezone.utc).timestamp()
        with CHECKOUTS_LOCK:
            current = CHECKOUTS.get(checkout_id)
            if (
                current is None
                or not current["callback_received"]
                or current["status"] != "pending"
                or current["verification_started"]
                or now - current["last_verified_at"] < 5
            ):
                return
            current["verification_started"] = True
            current["last_verified_at"] = now

        missing = missing_mpesa_settings()
        if missing:
            result = None
        else:
            timestamp = datetime.now(ZoneInfo("Africa/Nairobi")).strftime("%Y%m%d%H%M%S")
            shortcode = os.environ["MPESA_SHORTCODE"]
            password = base64.b64encode(
                f"{shortcode}{os.environ['MPESA_PASSKEY']}{timestamp}".encode("utf-8")
            ).decode("ascii")
            credentials = base64.b64encode(
                f"{os.environ['MPESA_CONSUMER_KEY']}:{os.environ['MPESA_CONSUMER_SECRET']}".encode("utf-8")
            ).decode("ascii")
            try:
                token_response = mpesa_request(
                    f"{MPESA_API}/oauth/v1/generate?grant_type=client_credentials",
                    headers={"Authorization": f"Basic {credentials}"},
                )
                access_token = token_response.get("access_token")
                if access_token:
                    result = mpesa_request(
                        f"{MPESA_API}/mpesa/stkpushquery/v1/query",
                        payload={
                            "BusinessShortCode": shortcode,
                            "Password": password,
                            "Timestamp": timestamp,
                            "CheckoutRequestID": checkout_id,
                        },
                        headers={
                            "Authorization": f"Bearer {access_token}",
                            "Content-Type": "application/json",
                        },
                    )
                else:
                    result = None
            except (HTTPError, URLError, TimeoutError, OSError, ValueError):
                print("M-Pesa sandbox transaction verification failed.")
                result = None

        with CHECKOUTS_LOCK:
            current = CHECKOUTS.get(checkout_id)
            if current is None:
                return
            current["verification_started"] = False
            if result and str(result.get("ResultCode")) == "0":
                current["status"] = "paid"
                current["message"] = "Sandbox payment confirmed by the M-Pesa transaction query."
            elif result and result.get("ResultCode") not in (None, ""):
                current["status"] = "failed"
                current["message"] = "The M-Pesa sandbox confirmed that the payment was not completed."
            elif current["callback_result_code"] not in (0, "0"):
                current["status"] = "failed"
                current["message"] = "The M-Pesa sandbox reported that the payment was not completed."
            else:
                current["message"] = "The callback arrived; the sandbox transaction is still being verified."


if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer((host, port), UrbanWearHandler)
    print(f"UrbanWear is running at http://{host}:{port}")
    print("M-Pesa sandbox is not configured." if missing_mpesa_settings() else "M-Pesa sandbox configuration is present.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping UrbanWear.")
    finally:
        server.server_close()
