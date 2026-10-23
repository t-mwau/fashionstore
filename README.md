# UrbanWear

## Run locally

From this directory, start the app server:

```bash
python3 server.py
```

Open <http://127.0.0.1:8000>. The app uses the local Bootstrap files and local product images. The catalog and cart work without an external image or icon service.

## M-Pesa sandbox setup

The checkout endpoint uses Safaricom Daraja's sandbox STK Push API. It is deliberately disabled until sandbox credentials and a public HTTPS callback are configured. Create sandbox credentials in the Safaricom Daraja developer portal, then set these server environment variables before starting `server.py`:

```bash
export MPESA_ENV=sandbox
export MPESA_CONSUMER_KEY='your-sandbox-consumer-key'
export MPESA_CONSUMER_SECRET='your-sandbox-consumer-secret'
export MPESA_SHORTCODE='your-sandbox-shortcode'
export MPESA_PASSKEY='your-sandbox-passkey'
export MPESA_CALLBACK_URL='https://your-public-host/api/mpesa/callback'
python3 server.py
```

Use a secure HTTPS tunnel or hosted development URL to forward the callback path to this server. The callback URL must end in `/api/mpesa/callback`. Use only the sandbox phone numbers and credentials shown in your Daraja portal; never put API credentials in `script.js`, HTML, or a public repository.

The app calculates the payment total from the server-side product catalog, sends an STK Push request, receives the callback, and checks the transaction through the sandbox query API before displaying payment as confirmed. Pending test checkouts are held in server memory and are cleared when the server restarts. This is a local sandbox integration, not a production payment service: it does not persist orders, verify delivery, or provide production-grade monitoring, rate limiting, and payment operations.

## Catalog notes

The folder has 40 PNG images: `image0.png` through `image24.png`, and `image26.png` through `image40.png`. `image25.png` is not present. Every available image is represented in the catalog; where two files contain the same product photograph, the extra photos are selectable from that product card.
