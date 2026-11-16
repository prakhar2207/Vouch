# SRI LEKH — RAZORPAY WEBHOOK CONFIGURATION GUIDE

This document provides exact instructions for configuring Razorpay Webhooks in the Razorpay Merchant Dashboard for both Staging (Test Mode) and Production (Live Mode).

---

## 1. Webhook Endpoints

| Environment | Webhook URL | Required Secret Variable | Mode in Dashboard |
| :--- | :--- | :--- | :--- |
| **Staging** | `https://vouch-u3u7.onrender.com/api/v1/billing/webhooks/razorpay/` | `RAZORPAY_WEBHOOK_SECRET` | **Test Mode** |
| **Production** | `https://api.srilekh.com/api/v1/billing/webhooks/razorpay/` *(or Render backend URL)* | `RAZORPAY_WEBHOOK_SECRET` | **Live Mode** *(requires owner KYC)* |

---

## 2. Required Webhook Events

When creating the webhook in Razorpay Dashboard (`Settings > Webhooks > Add New Webhook`), select the following event subscriptions:

### A. Payment Events
- `payment.authorized` — Payment authorized by bank.
- `payment.captured` — Payment successfully captured and credited.
- `payment.failed` — Payment failed or timed out.

### B. Order Events
- `order.paid` — Order successfully paid by customer.

### C. Subscription Events
- `subscription.authenticated` — Card/mandate successfully authorized.
- `subscription.activated` — Subscription active and running.
- `subscription.charged` — Successful periodic recurring charge.
- `subscription.pending` — Renewal payment pending retry.
- `subscription.halted` — Consecutive failures reached max threshold; mandate halted.
- `subscription.cancelled` — Subscription terminated.
- `subscription.completed` — Subscription term completed.

### D. Refund Events
- `refund.processed` — Gateway refund issued to customer.

---

## 3. Cryptographic Signature Verification

Razorpay transmits a signature header with every delivery:
```http
X-Razorpay-Signature: <64-character-hex-digest>
```

SriLekh's backend (`RazorpayService.verify_webhook_signature`) cryptographically computes:
```python
expected_signature = hmac.new(
    key=RAZORPAY_WEBHOOK_SECRET.encode('utf-8'),
    msg=request.body,  # Raw unmodified UTF-8 request bytes
    digestmod=hashlib.sha256
).hexdigest()
```
The comparison uses constant-time `hmac.compare_digest` to prevent timing attacks.

---

## 4. Idempotency & Replay Attack Defense

1. **Persistent Event Log:** Every webhook delivery records a row in `apps_billing_webhookevent`.
2. **Unique Constraint:** The `event_id` field has a unique database index.
3. **Replay Rejection:** If a webhook with an existing `event_id` arrives and has status `processed`, SriLekh returns HTTP `200 OK` immediately with `{"status": "ignored", "reason": "duplicate_event"}`.
4. **Out-of-Order Handling:** Status transitions are guarded by atomic database locks (`select_for_update`) to prevent race conditions during concurrent webhook deliveries.
