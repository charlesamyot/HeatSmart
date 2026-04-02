"""Stripe payment routes — donations and premium unlock."""
from __future__ import annotations

import logging

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request

from .auth import get_current_user
from .config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/payments")


@router.post("/create-checkout")
async def create_checkout_session(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Create a Stripe checkout session for premium unlock or donation."""
    settings = get_settings()
    if not settings.stripe_secret_key:
        raise HTTPException(503, "Payments not configured")

    stripe.api_key = settings.stripe_secret_key
    body = await request.json()
    payment_type = body.get("type", "premium")  # "premium" or "donation"
    amount = body.get("amount_cents", 999)  # default $9.99

    if payment_type == "premium":
        amount = 999  # fixed $9.99
        description = "WattWise Premium Unlock"
    else:
        description = f"WattWise Donation — ${amount / 100:.2f}"

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": description},
                    "unit_amount": amount,
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=f"{request.base_url}dashboard?payment=success",
            cancel_url=f"{request.base_url}dashboard?payment=cancelled",
            metadata={"user_id": user["sub"], "type": payment_type},
        )
        return {"checkout_url": session.url}
    except stripe.error.StripeError as exc:
        logger.error("Stripe error: %s", exc)
        raise HTTPException(500, "Payment setup failed")


@router.post("/webhook")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events (payment success, etc.)."""
    settings = get_settings()
    if not settings.stripe_webhook_secret:
        raise HTTPException(503, "Webhook not configured")

    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")

    try:
        stripe.api_key = settings.stripe_secret_key
        event = stripe.Webhook.construct_event(
            payload, sig, settings.stripe_webhook_secret
        )
    except (ValueError, stripe.error.SignatureVerificationError) as exc:
        logger.warning("Webhook verification failed: %s", exc)
        raise HTTPException(400, "Invalid webhook")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        user_id = session.get("metadata", {}).get("user_id")
        payment_type = session.get("metadata", {}).get("type", "premium")
        amount = session.get("amount_total", 0)
        logger.info("Payment complete: user=%s type=%s amount=%d",
                    user_id, payment_type, amount)
        # TODO: Update user profile is_premium=True in Supabase
        # TODO: Record payment in payments table

    return {"status": "ok"}
