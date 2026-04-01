# Rheem EcoNet ClearBlade API — Quick Reference

## Auth
```
POST https://rheem.clearblade.com/api/v/1/user/auth
Headers: ClearBlade-SystemKey, ClearBlade-SystemSecret, Content-Type: application/json
Body: {"email": "...", "password": "..."}
Response: {user_token, user_id, options: {account_id, ...}}
```
- `user_id` = ClearBlade ID (for REST headers)
- `options.account_id` = Rheem ID (**for MQTT topics**)

## MQTT
- Host: `rheem.clearblade.com:1884` (TLS)
- Auth: `username_pw_set(user_token, SYSTEM_KEY)`
- Paho 2.x: `CallbackAPIVersion.VERSION1` required
- Subscribe: `user/{account_id}/device/reported`, `user/{account_id}/device/desired`
- Publish: `user/{account_id}/device/desired`
- Message: `{"transactionId":"ANDROID_...", "device_name":"...", "serial_number":"...", "@MODE":1}`

## Device State
```
POST /api/v/1/code/{key}/getUserDataForApp
Body: {"resource": "friedrich"}
Response: {results: {locations: [{equiptments: [{@MODE, @SETPOINT, @RUNNING, ...}]}]}}
```

## Energy Usage (WORKING)
```
POST /api/v/1/code/{key}/dynamicAction
Body: {
  "ACTION": "waterheaterUsageReportView",
  "device_name": "11980437215467865",
  "serial_number": "07-0e-17-0c-2c-32-c0-c8-01",
  "start_date": "2026-04-01T00:00:00.999",
  "end_date": "2026-04-01T23:59:59.999",
  "usage_type": "energyUsage"
}
```
- Single day → hourly: `results.energy_usage.data = [{name: hour, value: kwh}]`
- Multi-day → daily: `results.energy_usage.data = [{name: day_of_month, value: kwh}]`

## NOT WORKING (Gen5 firmware)
- All lowercase `action` dynamicAction → "Bad Request"
- All `code/getXxx` endpoints → 500
- REST messaging → "does not have permissions"
- Schedule retrieval → no endpoint found

## Constants
- System key: `e2e699cb0bb0bbb88fc8858cb5a401`
- System secret: `E2E699CB0BE6C6FADDB1B0BC9A20`
- Mode map: 0=Off, 1=Energy Saver, 2=Heat Pump, 3=High Demand, 4=Electric, 5=Vacation
- Hot water: zero=0%, ten=33%, fourty=66%, hundread=100%
