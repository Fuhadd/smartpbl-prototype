/// Build-time configuration, set with `--dart-define` (like Vite's `VITE_*` variables:
/// baked into the build, public, never secrets).
library;

/// The SMARTPBL API. `flutter build web --dart-define=API_URL=https://…run.app`.
const apiUrl = String.fromEnvironment('API_URL', defaultValue: 'http://localhost:8000');

/// The office line for "Call office". An Ofcom drama number (0121 496 0000–0999 are
/// reserved for fiction), so the demo can never ring a real person.
const officePhoneDisplay = '0121 496 0000';
const officePhoneUri = 'tel:+441214960000';

/// The public demo carer account, exactly as on CarerLogin.dc.html (seeded by
/// scripts/seed_demo.py; the API refuses it outside local/demo environments).
const demoEmail = 'joy@demo.smartpbl';
const demoPassword = 'demo-carer';
