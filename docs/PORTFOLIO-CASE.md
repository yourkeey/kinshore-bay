# Kinshore Bay · A family weekend, from both sides of Reception

Kinshore Bay is a fictional Mediterranean family resort. The demo follows a family of four planning a two-night stay and the receptionist preparing for their arrival. Imagery is generated, and inventory, prices and reservations are fictional. [Image provenance](ASSETS.md)

[Watch the 22-second walkthrough](media/kinshore-bay-demo.webm)

Open the [live guest demo](https://kinshore-bay.scalo.biz/) or select **Open Mini App** in [Kinshore Bay on Telegram](https://t.me/KinshoreBay_app).

## Try the route

1. On the guest site, open **Poolside One Bedroom** and its floor plan. The bedroom has a double bed and the living room has a double sofa bed.
2. Use **Check dates** and pick an upcoming Friday through Sunday for four guests. The seeded €135 nightly rate gives a €270 total. Send the demo request and copy the reference from **My stay**.
3. Select **Open demo reception**, find the reference, choose an available apartment and confirm it. In the local development setup, sign in with the reception account described in the [README](../README.md).
4. Follow **Guest My stay** back to the request and book two places on the **Pine & Shore Walk**. **Walks** at Reception shows the party under the same reference.

## Product and implementation

- The apartment card answers where everyone sleeps before asking for dates. The guest sees the total for the whole stay. Reception assigns the individual apartment after checking overlap.
- Django supplies availability, price, status and walk capacity to both views. It keeps the requested rate on the stay and records status transitions. The PostgreSQL tests cover two simultaneous requests for the last apartment or walk place.
- In public demo mode, each browser has its own reception shift, stays, walk capacity and grill slots. Two visitors can exercise the same scenario independently.

The browser route was exercised at 320, 390 and 1440 px using Chromium. Results for observed walkthroughs with first-time visitors are still pending. [Architecture](ARCHITECTURE.md)
