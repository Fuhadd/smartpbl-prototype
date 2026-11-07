# SMARTPBL carer app (Flutter)

Today's visits and care notes for carers, on the same API as the coordinator dashboard.
Designs: `docs/design/screens/{CarerLogin,Visits,VisitDetail,Note,Submitted}.dc.html`.
Notes: `docs/learning/29-carer-api.md` (API) and `30-carer-app.md` (this app). Synthetic demo data only.

```bash
flutter pub get
flutter test                                    # 22 tests, no server needed
# Against a local API (its CORS list must include http://localhost:8081):
flutter run -d chrome --web-port 8081 --dart-define=API_URL=http://localhost:8000
# Release web build (Wasm with JS fallback), then serve build/web as static files:
flutter build web --wasm --release --dart-define=API_URL=https://<your-api>
```

Demo login: `joy@demo.smartpbl` / `demo-carer` (seeded by `scripts/seed_demo.py`, linked to CR-0001).
Joy's visits come from the latest saved rota, so a coordinator must run the optimiser first.
