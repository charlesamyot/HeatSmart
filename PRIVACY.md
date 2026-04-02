# Privacy Policy

**Last updated:** April 1, 2026

WattWise ("we", "our", "the app") is operated by Charles Amyot. This policy describes how we collect, use, and protect your personal information.

## What We Collect

| Data | Purpose | Storage |
|------|---------|---------|
| Email address | Account authentication | Supabase (encrypted) |
| EcoNet username/password | Connect to your Rheem water heater | AES-256 encrypted at rest |
| Device data | Serial number, MAC address, model info | Supabase PostgreSQL |
| Energy usage history | Usage charts, cost analysis, optimization | Supabase PostgreSQL |
| Heater state snapshots | Temperature, mode, running status | Supabase PostgreSQL |
| Payment information | Premium unlock / donations | Processed by Stripe (we never see your card) |

## How We Use Your Data

- **Connect to your water heater** via the Rheem EcoNet cloud service (ClearBlade IoT)
- **Display monitoring dashboards** with real-time and historical data
- **Calculate TOU cost optimization** using your energy usage patterns and local utility rates
- **Process payments** via Stripe for premium features or donations

## What We Do NOT Do

- We do **not** sell your data to third parties
- We do **not** share your EcoNet credentials with anyone
- We do **not** use your data for advertising
- We do **not** store credit card information (Stripe handles all payment data)

## Data Security

- EcoNet credentials are encrypted with AES-256 (Fernet) at rest
- All data transmitted over HTTPS/TLS
- MQTT connections use TLS encryption
- Database access controlled by Supabase Row-Level Security (each user sees only their own data)
- Server hosted on Render.com (SOC 2 compliant)

## Your Rights

You have the right to:

- **Access** your data at any time through the app
- **Export** your energy usage data as CSV
- **Correct** your information in Settings
- **Delete** your account and all associated data (Settings > Delete Account)
- **Revoke** EcoNet credential access at any time

We will respond to data requests within 30 days.

## Data Retention

- Account data is retained while your account is active
- Energy usage history is retained for up to 2 years
- When you delete your account, all data is permanently deleted within 30 days
- Backups containing deleted data are purged within 90 days

## Children

WattWise is intended for users aged 18 and older. We do not knowingly collect data from children under 13.

## Changes

We may update this policy from time to time. Significant changes will be communicated via email or in-app notification.

## Contact

For privacy questions or data requests:
- Email: charles@wattwise.app
- GitHub: https://github.com/charlesamyot/WattWise/issues
