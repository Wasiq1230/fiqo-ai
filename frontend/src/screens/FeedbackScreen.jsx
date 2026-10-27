/**
 * Feedback & support screen (Phase 7).
 *
 * One form covering all submission types — general feedback, bug report,
 * complaint, feature request, and contact support — posted to /api/feedback.
 * Works for both anonymous and signed-in users (the backend links it to the
 * account when a valid token is present).
 *
 * Spam protection: a hidden "website" honeypot field that must stay empty
 * (the backend rejects any non-empty value). Real users never see or fill it.
 */
import { useState } from "react";
import { submitFeedback } from "../lib/services";
import { useToast } from "../components/Toast";
import { useAuth } from "../context/AuthContext";
import { apiErrorMessage } from "../lib/api";
import { Ico, Icons, Spinner } from "../components/icons";

const TYPES = [
  { key: "feedback", label: "General feedback" },
  { key: "bug", label: "Bug report" },
  { key: "complaint", label: "Complaint" },
  { key: "feature", label: "Feature request" },
  { key: "support", label: "Contact support" },
];

const emailRe = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function FeedbackScreen() {
  const toast = useToast();
  const { user } = useAuth();

  const [type, setType] = useState("feedback");
  const [name, setName] = useState(user?.name || "");
  const [email, setEmail] = useState(user?.email || "");
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const [website, setWebsite] = useState(""); // honeypot
  const [errors, setErrors] = useState({});
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  const validate = () => {
    const e = {};
    if (name.trim().length < 2) e.name = "Please enter your name.";
    if (!emailRe.test(email)) e.email = "Enter a valid email address.";
    if (subject.trim().length < 3) e.subject = "Add a short subject.";
    if (message.trim().length < 10) e.message = "Please add a little more detail (10+ characters).";
    setErrors(e);
    return Object.keys(e).length === 0;
  };

  const submit = async (ev) => {
    ev.preventDefault();
    if (busy || !validate()) return;
    setBusy(true);
    try {
      await submitFeedback({
        type,
        name: name.trim(),
        email: email.trim(),
        subject: subject.trim(),
        message: message.trim(),
        website,
      });
      setDone(true);
      setSubject("");
      setMessage("");
      toast.success("Thank you! Your submission was received.");
    } catch (err) {
      toast.error(apiErrorMessage(err, "Could not send. Please try again."));
    } finally {
      setBusy(false);
    }
  };

  if (done)
    return (
      <div className="um-empty-state">
        <div className="um-empty-icon">
          <Ico path={Icons.check} size={28} />
        </div>
        <p className="um-empty-title">Submission received</p>
        <p className="um-empty-sub">
          Thanks for reaching out — we read every message. We'll follow up by email if needed.
        </p>
        <button className="um-btn um-btn-sm" style={{ marginTop: 16 }} onClick={() => setDone(false)}>
          Send another
        </button>
      </div>
    );

  return (
    <div className="um-bubble" style={{ maxWidth: 620, margin: "0 auto" }}>
      <div className="um-bubble-header">
        <div className="um-bubble-title">
          <div className="um-bubble-avatar">
            <Ico path={Icons.message} size={13} />
          </div>
          <span>Feedback &amp; Support</span>
        </div>
      </div>
      <div className="um-bubble-body">
        <form onSubmit={submit} noValidate>
          <div className="um-field">
            <label className="um-field-label" htmlFor="fb-type">What can we help with?</label>
            <select id="fb-type" className="um-select" value={type} onChange={(e) => setType(e.target.value)} style={{ width: "100%" }}>
              {TYPES.map((t) => (
                <option key={t.key} value={t.key}>{t.label}</option>
              ))}
            </select>
          </div>

          <div className="um-field">
            <label className="um-field-label" htmlFor="fb-name">Name</label>
            <input id="fb-name" className="um-input" value={name} onChange={(e) => setName(e.target.value)} aria-invalid={!!errors.name} />
            {errors.name && <p className="um-field-error">{errors.name}</p>}
          </div>

          <div className="um-field">
            <label className="um-field-label" htmlFor="fb-email">Email</label>
            <input id="fb-email" className="um-input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} aria-invalid={!!errors.email} />
            {errors.email && <p className="um-field-error">{errors.email}</p>}
          </div>

          <div className="um-field">
            <label className="um-field-label" htmlFor="fb-subject">Subject</label>
            <input id="fb-subject" className="um-input" value={subject} onChange={(e) => setSubject(e.target.value)} aria-invalid={!!errors.subject} />
            {errors.subject && <p className="um-field-error">{errors.subject}</p>}
          </div>

          <div className="um-field">
            <label className="um-field-label" htmlFor="fb-message">Message</label>
            <textarea id="fb-message" className="um-textarea" value={message} onChange={(e) => setMessage(e.target.value)} aria-invalid={!!errors.message} />
            {errors.message && <p className="um-field-error">{errors.message}</p>}
          </div>

          {/* Honeypot — hidden from real users, bots tend to fill it. */}
          <div className="um-hp" aria-hidden="true">
            <label htmlFor="fb-website">Website</label>
            <input
              id="fb-website"
              tabIndex={-1}
              autoComplete="off"
              value={website}
              onChange={(e) => setWebsite(e.target.value)}
            />
          </div>

          <button className="um-btn um-btn-primary um-btn-full" type="submit" disabled={busy}>
            {busy ? <Spinner /> : "Send message"}
          </button>
        </form>
      </div>
    </div>
  );
}
