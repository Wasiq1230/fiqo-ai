# Login fix — setup guide

Do bugs the ka fix. Code ready hai; ab tumhe **3 jagah settings lagani hain**:
Neon (database), Render (backend), Vercel (frontend).

Total time: ~20 minute.

---

## Pehle samajh lo masla kya tha

### Bug 1 — purana account gayab ho jata tha

Backend SQLite use kar raha tha (`FiQO.db` — ek simple file). Render ka
filesystem **ephemeral** hai: jab bhi service restart hoti hai ya tum deploy
karte ho, wo file mit jati hai. Free tier pe 15 minute inactivity ke baad
service sleep bhi ho jati hai, aur wapas uthne pe disk khali.

Nateeja: tumne account banaya → thodi der baad database khali → login pe
`Invalid email or password`, kyunki account waqai maujood nahi tha.

**Fix:** database ab Postgres pe hai (Neon), jo alag server pe chalta hai aur
restart se koi farq nahi parta.

### Bug 2 — fake email chal jati thi

Code sirf email ka *format* check karta tha. `asdf@asdf.com` format ke hisaab
se bilkul theek hai, is liye accept ho jati thi.

**Fix — do layer:**

1. **Domain check** — signup pe DNS se poocha jata hai ke us domain ka koi mail
   server hai bhi ya nahi. Nahi hai → reject. Saath hi temp-mail services
   (mailinator, 10minutemail, waghera) ki list block hai.
2. **Confirmation email** — account ban to jata hai, lekin login tab tak nahi
   hota jab tak user apne inbox mein aaye link pe click na kare.

---

## Step 1 — Neon pe database banao (5 min)

1. https://neon.com khol ke GitHub se sign up karo (free, card nahi chahiye).
2. **Create project** → naam `fiqo`, region apne qareeb ka chuno.
3. Bane hue project mein **Connection string** dikhega. Usko copy karo. Shakal
   aisi hogi:

   ```
   postgresql://neondb_owner:XXXXXXXX@ep-cool-name-123456.us-east-2.aws.neon.tech/neondb?sslmode=require
   ```

   > `sslmode=require` wala hissa zaroori hai — mat hatana.

Ye string sambhal ke rakho, agle step mein chahiye.

**Neon kyun, Render ka apna Postgres kyun nahi:** Render ka free Postgres **30
din baad khud delete** ho jata hai. Us ke baad bilkul yehi bug wapas aa jata.
Neon ka free tier permanent hai (0.5 GB, jo tumhare use ke liye kaafi zyada
hai).

---

## Step 2 — Gmail App Password banao (5 min)

Verification email bhejne ke liye. Apna normal Gmail password **kaam nahi
karega** — Google alag 16-character ka password deta hai.

1. https://myaccount.google.com/security kholo.
2. **2-Step Verification** on karo agar pehle se nahi hai. (App password ka
   option isi ke baghair nahi aata.)
3. https://myaccount.google.com/apppasswords pe jao.
4. App ka naam likho — `FIQO` — aur **Create** dabao.
5. Jo 16 characters aayen wo copy kar lo. **Spaces hata do** — `abcd efgh ijkl
   mnop` ko `abcdefghijklmnop` bana lo.

> Ye password sirf ek dafa dikhta hai. Kahin note kar lo.

Limit ~500 email/din hai — student project ke liye bohat.

---

## Step 3 — Render pe environment variables lagao (5 min)

Render dashboard → apni backend service → **Environment** → har ek ke liye
**Add Environment Variable**.

| Key | Value |
|---|---|
| `DATABASE_URL` | Neon wali poori connection string (Step 1) |
| `ENVIRONMENT` | `production` |
| `DEBUG` | `false` |
| `FRONTEND_URL` | `https://<tumhari-site>.vercel.app` — **slash ke baghair aakhir mein** |
| `CORS_ORIGINS` | wahi Vercel URL |
| `ALLOWED_HOSTS` | `<tumhari-service>.onrender.com` |
| `TRUST_PROXY` | `true` |
| `REQUIRE_EMAIL_VERIFICATION` | `true` |
| `CHECK_EMAIL_MX` | `true` |
| `BLOCK_DISPOSABLE_EMAIL` | `true` |
| `EMAIL_PROVIDER` | `smtp` |
| `EMAIL_FROM` | `FIQO AI <tumhara.email@gmail.com>` |
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | `tumhara.email@gmail.com` |
| `SMTP_PASSWORD` | Step 2 wala 16-char password, bina spaces |
| `SMTP_USE_TLS` | `true` |

Aur ye pehle se hone chahiye — check kar lo maujood hain:
`SECRET_KEY`, `GROQ_API_KEY`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`.

> **Khayal rakho:** `ENVIRONMENT=production` ke saath app ab **start hi nahi
> hogi** agar in mein se koi cheez ghalat hai — SQLite reh gaya, `CORS_ORIGINS`
> mein `*` hai, ya `DEBUG=true` hai. Ye jaan bujh kar hai: crash saaf dikhta hai,
> khamoshi se toota hua deployment nahi dikhta. Log mein wajah likhi hoti hai.

Save karo → Render khud redeploy karega.

---

## Step 4 — Vercel pe frontend variable check karo (2 min)

Vercel → project → **Settings → Environment Variables**:

| Key | Value |
|---|---|
| `VITE_API_URL` | `https://<tumhari-service>.onrender.com` — slash ke baghair |

Agar pehle se sahi hai to chhoR do. Change kiya ho to **Deployments → … →
Redeploy** karna paray ga (Vite build ke waqt values bake karta hai).

---

## Step 5 — Code push karo

```bash
cd "C:\WASIQ\DOWNLOAD 222 BACKUP WASUQ\unimate-ai-production (4)\unimate-ai"
git add -A
git commit -m "Fix: Postgres persistence + email verification"
git push
```

Render aur Vercel dono khud build shuru kar denge.

---

## Step 6 — Test karo

Render ke **Logs** tab mein ye do line dhoondo:

```
Database ready: postgresql at ep-....neon.tech
Email verification: ENFORCED (provider=smtp).
```

`Using SQLITE` likha aaye to `DATABASE_URL` set nahi hui.

Phir site pe:

1. **Fake email** — `asdf@asdf.com` se signup karo
   → "No mail server exists for 'asdf.com'…" aana chahiye. ✅
2. **Temp mail** — `test@mailinator.com`
   → "Temporary or disposable email addresses are not accepted." ✅
3. **Asli email** — apni Gmail se signup karo
   → "Check your email" screen aaye, inbox mein link aaye.
   Login try karo bina click kiye → rukna chahiye. ✅
4. **Link pe click** karo → seedha andar sign in ho jao. ✅
5. **Asli test** — Render dashboard se **Manual Deploy → Restart service**,
   phir dobara login karo. **Ab chalna chahiye.** Yehi wo cheez hai jo pehle
   toot ti thi. ✅

---

## Purane users ka kya hoga?

Jo accounts pehle se database mein hain wo automatically **verified** mark ho
jate hain. Un ko koi email nahi milegi aur wo pehle ki tarah login karte
rahenge. Sirf naye signups ko confirm karna paray ga.

(Waise Render pe SQLite thi, to purana data shayad pehle hi ja chuka hai.
Users ko dobara signup karna paray ga — is dafa permanently.)

---

## Kuch kaam na kare to

| Masla | Wajah / hal |
|---|---|
| Email aa hi nahi rahi | Spam folder dekho. Render log mein `Failed to send` grep karo. 99% waqt `SMTP_PASSWORD` mein spaces reh jate hain. |
| `SMTPAuthenticationError` | App Password ghalat hai, ya 2-Step Verification off hai. Naya app password banao. |
| Email bilkul nahi ja rahi, log mein timeout | Render ne SMTP port block kiya. [resend.com](https://resend.com) pe free account banao, `EMAIL_PROVIDER=resend` aur `RESEND_API_KEY=...` set karo, SMTP_* rehne do. |
| Link pe click karne se 404 | `FRONTEND_URL` ghalat hai. Bilkul wohi URL ho jo browser mein aata hai, aakhir mein slash nahi. |
| App start hi nahi ho rahi | Log dekho — startup validation exact wajah batati hai. |
| Sab kuch theek lagta hai par login phir bhi fail | Log mein `Database ready: postgresql` confirm karo. `Using SQLITE` aaye to `DATABASE_URL` Render tak pohnchi hi nahi. |
| Signup pe "Try again in N seconds" | Yehi expected hai — ek minute mein ek confirmation email. Intezar karo. |

---

## Agar email setup abhi nahi karna

`REQUIRE_EMAIL_VERIFICATION=false` set kar do. Domain check (`CHECK_EMAIL_MX`,
`BLOCK_DISPOSABLE_EMAIL`) phir bhi kaam karta rahega, to `asdf@asdf.com` block
rahegi — bas confirmation link ka step nahi hoga.

Isi tarah agar `EMAIL_PROVIDER` set hi na ho, app khud verification off kar
deti hai — taake aise accounts na banen jinhen koi kabhi activate hi na kar
sake.

---

## Jo files change hui

**Backend**

| File | Kya hua |
|---|---|
| `app/config.py` | `postgres://` URL ko `postgresql+psycopg://` mein badalta hai; email settings; production validation |
| `app/database.py` | Postgres/SQLite dono ke liye migration; startup pe konsa DB hai wo log |
| `app/models.py` | `users.is_verified`; naya `email_verifications` table |
| `app/routers/auth.py` | Domain check, verification flow, `/verify-email`, `/resend-verification` |
| `app/services/email_validation.py` | **naya** — MX lookup + disposable blocklist |
| `app/services/email_service.py` | **naya** — SMTP / Resend / console |
| `app/services/verification.py` | **naya** — token banana aur redeem karna |
| `tests/test_email_verification.py` | **naya** — 19 tests |

**Frontend**

| File | Kya hua |
|---|---|
| `src/screens/AuthScreen.jsx` | "Check your email" screen, resend button, link handling |
| `src/context/AuthContext.jsx` | Signup ab seedha login nahi karta |
| `src/lib/services.js` | `verifyEmail`, `resendVerification` |
| `src/lib/api.js` | Structured error codes |

---

## Kya verify ho chuka hai

- Poore backend suite ke 58 tests pass (39 purane + 19 naye)
- Asli Postgres ke against end-to-end: signup → block → verify → login
- **Restart survival** — process restart ke baad account zinda (yehi bug tha)
- Purane database ki migration: `is_verified` column add hui, maujooda users
  verified mark hue — koi lock out nahi hua
- Frontend Vite build clean, `AuthScreen.jsx` lint clean

---

# Forgot password

Baad mein add kiya gaya. Do naye endpoints:

- `POST /api/auth/forgot-password` — email pe reset link bhejta hai
- `POST /api/auth/reset-password` — link se naya password set karta hai

Site pe: sign-in form ke neeche **"Forgot password?"** link aa gaya hai.

## ⚠️ Ye email ke baghair kaam nahi karega

Reset link inbox mein hi jata hai — koi aur mehfooz tareeqa hai hi nahi. Jab
tak `EMAIL_PROVIDER` sahi set na ho, "Forgot password?" dabane pe screen to
normal dikhegi (jaan bujh kar — taake ye pata na chale ke kaunsa email
registered hai) lekin **koi email nahi jayegi**.

Chalane ke liye Render pe yehi chahiye jo confirmation email ke liye chahiye:

```
EMAIL_PROVIDER   = smtp
SMTP_HOST        = smtp.gmail.com        (ya smtp-relay.brevo.com)
SMTP_PORT        = 587
SMTP_USER        = <aap ka email / Brevo login>
SMTP_PASSWORD    = <Gmail App Password / Brevo SMTP key>
SMTP_USE_TLS     = true
EMAIL_FROM       = FIQO AI <aap ka email>
FRONTEND_URL     = https://fiqo-ai.vercel.app
```

Ek dafa ye lag gaya to **dono** cheezein chal paray gi — confirmation email
bhi aur forgot password bhi. Alag se kuch nahi karna.

## Reset karte waqt kya hota hai

1. Link ek dafa istemal hota hai, 1 ghante mein expire
2. Naya password set hota hai
3. **Har device se logout ho jata hai** — agar kisi ne account hack kiya tha to
   uska session bhi foran mar jata hai (password reset karne ki sab se aam
   wajah yehi hoti hai)
4. Email verified mark ho jati hai — link khol lena wohi saboot hai

## Naye tests

`tests/test_password_reset.py` — 14 tests. Sab se ahem:

- unknown email aur asli email ka jawab bilkul ek jaisa (enumeration block)
- purana session reset ke baad mar jata hai
- confirmation token se password reset **nahi** ho sakta, aur ulta bhi nahi
- link dobara istemal nahi hota

---

# ⚠️ Render free tier SMTP block karta hai

Gmail SMTP (`smtp.gmail.com:587`) Render ke free plan pe **kaam nahi karega**.
Render ne free web services se outbound SMTP ports band kar rakhe hain — spam
rokne ke liye. Ye unka faisla hai, aap ke code ya password ka masla nahi.

Log mein aisa dikhta hai:

```
File "/app/app/services/email_service.py", line 148, in _send_smtp
  with smtplib.SMTP(settings.smtp_host, settings.smtp_port,
File "/usr/local/lib/python3.12/smtplib.py", line 312, in _get_socket
```

`_get_socket` pe rukna matlab **connection hi nahi bani** — login tak baat
pohnchi hi nahi. Is liye app password badalne ka koi faida nahi.

## Hal — Brevo, HTTPS ke zariye

Port 443 use hota hai, jo kabhi block nahi hota.

### 1. Brevo account (5 min)

1. https://www.brevo.com → **Sign up free** (300 email/din, card nahi)
2. Email verify karo

### 2. Sender verify karo (zaroori)

1. Left menu → **Senders, Domains & Dedicated IPs** → **Senders**
2. **Add a sender** → apna naam aur Gmail address
3. Us Gmail pe Brevo ka email aayega → verify link click karo

> Sirf **address** verify karni hai, poora domain nahi. Isi liye Brevo yahan
> Resend se behtar hai — Resend bina domain ke sirf aap ko hi email bhej sakta
> hai, aur kisi user ko nahi.

### 3. API key

1. Upar right corner apne naam pe click → **SMTP & API**
2. **API Keys** tab → **Generate a new API key** → naam `FIQO`
3. Key copy karo (`xkeysib-...` se shuru hoti hai) — **sirf ek dafa dikhti hai**

### 4. Render pe

```
EMAIL_PROVIDER  =  brevo
BREVO_API_KEY   =  xkeysib-...
EMAIL_FROM      =  FIQO AI <wahi verified sender address>
```

`SMTP_*` wale variables rehne do, koi nuqsan nahi — `EMAIL_PROVIDER=brevo`
hone pe wo use hi nahi hote.

> `EMAIL_FROM` ki address **bilkul wohi** honi chahiye jo Brevo mein verify ki.
> Warna Brevo reject kar dega aur log mein wajah likhi aayegi.

Save → deploy → log mein dekho:

```
Sent 'Reset your password' to w***6@gmail.com via Brevo
```

### 5. Aakhri step

Email pohnchne lage to:

```
REQUIRE_EMAIL_VERIFICATION  =  true
```

Ab sab kuch mukammal.

## Gmail SMTP kab kaam aayega

Agar kabhi Render se VPS ya paid plan pe jao, ya kahin aur host karo jahan SMTP
ports khule hon — to `EMAIL_PROVIDER=smtp` wapas kar dena, sab values pehle se
maujood hain.
