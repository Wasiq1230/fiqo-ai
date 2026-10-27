/**
 * Presentational building blocks shared across sections:
 *  - FormatText: renders AI plain-text output with light heading/bullet styling
 *  - OutputBubble: a titled result card with read-aloud + TXT/PDF export
 *  - Skeleton: shimmer placeholder shown while a generation is in flight
 *  - EmptyState: friendly "nothing here yet" placeholder
 */
import { useState, useEffect } from "react";
import jsPDF from "jspdf";
import { Ico, Icons } from "./icons";
import { useToast } from "./Toast";

/* ── download / speech helpers ── */

export const downloadText = (filename, text) => {
  try {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(a.href);
  } catch (err) {
    console.error("Text download failed", err);
  }
};

export const downloadPDF = (filename, title, text) => {
  try {
    const doc = new jsPDF();
    doc.setFont("helvetica", "bold");
    doc.setFontSize(16);
    doc.text(title, 15, 20);
    doc.setFont("helvetica", "normal");
    doc.setFontSize(11);

    // Split text with height safety bounds
    const splitText = doc.splitTextToSize(String(text), 180);

    // Page height logic for multi-page PDF generation if text is long
    let y = 34;
    const pageHeight = doc.internal.pageSize.height;

    for (let i = 0; i < splitText.length; i++) {
      if (y > pageHeight - 20) {
        doc.addPage();
        y = 20; // reset y on new page
      }
      doc.text(splitText[i], 15, y);
      y += 6; // line height spacing
    }

    doc.save(filename);
  } catch (err) {
    throw new Error("Failed to compile or save PDF output.");
  }
};

/* ── FormatText ── */

export function FormatText({ text }) {
  if (!text) return <p className="um-empty">Nothing generated yet…</p>;
  return (
    <div className="um-formatted">
      {String(text)
        .split("\n")
        .map((line, i) => {
          const clean = line.replace(/\*\*/g, "").trim();
          if (!clean) return <div key={i} className="um-spacer" />;
          if (
            clean.startsWith("#") ||
            clean.endsWith(":") ||
            /^day\s/i.test(clean) ||
            /^question/i.test(clean)
          )
            return (
              <p key={i} className="um-fmtheading">
                {clean.replace(/#/g, "")}
              </p>
            );
          if (clean.startsWith("-") || clean.startsWith("*") || /^\d+\./.test(clean))
            return (
              <p key={i} className="um-fmtpoint">
                <span className="um-bullet">·</span>
                {clean.replace(/^[-*]\s*/, "").replace(/^\d+\.\s*/, "")}
              </p>
            );
          return (
            <p key={i} className="um-fmtline">
              {clean}
            </p>
          );
        })}
    </div>
  );
}

/* ── OutputBubble ── */

export function OutputBubble({ title, text, filename }) {
  const toast = useToast();
  const [speaking, setSpeaking] = useState(false);

  useEffect(() => {
    // Sync with global speech state / window switches
    const checkSpeech = setInterval(() => {
      if ("speechSynthesis" in window) {
        setSpeaking(window.speechSynthesis.speaking);
      }
    }, 250);

    return () => {
      clearInterval(checkSpeech);
      if ("speechSynthesis" in window) {
        window.speechSynthesis.cancel();
      }
    };
  }, []);

  const handleSpeak = () => {
    if (!text?.trim()) return;
    if (!("speechSynthesis" in window)) {
      toast.info("Text-to-speech is not supported in this browser.");
      return;
    }

    try {
      window.speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text);
      u.lang = "en-US";
      u.rate = 0.9;
      u.onend = () => setSpeaking(false);
      u.onerror = () => setSpeaking(false);
      window.speechSynthesis.speak(u);
      setSpeaking(true);
    } catch (err) {
      console.error(err);
      setSpeaking(false);
    }
  };

  const handleStop = () => {
    if ("speechSynthesis" in window) {
      window.speechSynthesis.cancel();
      setSpeaking(false);
    }
  };

  const handlePDFDownload = () => {
    try {
      downloadPDF(filename.replace(".txt", ".pdf"), title, text);
      toast.success("PDF Downloaded successfully!");
    } catch (err) {
      toast.error(err.message || "Failed to download PDF.");
    }
  };

  return (
    <div className="um-bubble">
      <div className="um-bubble-header">
        <div className="um-bubble-title">
          <div className="um-bubble-avatar">
            <Ico path={Icons.sparkle} size={13} />
          </div>
          <span>{title}</span>
        </div>
        <div className="um-bubble-actions">
          <button
            className={`um-action-btn${speaking ? " um-speaking-active" : ""}`}
            onClick={handleSpeak}
            title="Read aloud"
            aria-label="Read aloud"
          >
            <Ico path={Icons.volume} size={14} className={speaking ? "um-pulse" : ""} />
          </button>
          {speaking && (
            <button
              className="um-action-btn"
              onClick={handleStop}
              title="Stop reading"
              aria-label="Stop reading"
            >
              <Ico path={Icons.stop} size={14} />
            </button>
          )}
          <button className="um-action-btn" onClick={() => { downloadText(filename, text); toast.success("TXT Downloaded successfully!"); }} title="Download as text">
            <Ico path={Icons.download} size={14} />
            <span>TXT</span>
          </button>
          <button
            className="um-action-btn um-action-primary"
            onClick={handlePDFDownload}
            title="Download as PDF"
          >
            <Ico path={Icons.download} size={14} />
            <span>PDF</span>
          </button>
        </div>
      </div>
      <div className="um-bubble-body">
        <FormatText text={text} />
      </div>
    </div>
  );
}

/* ── Skeleton ── */

export function Skeleton() {
  return (
    <div className="um-bubble" aria-hidden="true">
      <div className="um-bubble-body">
        <div className="um-skeleton um-skeleton-line w-40" />
        <div className="um-skeleton um-skeleton-line w-90" />
        <div className="um-skeleton um-skeleton-line w-70" />
        <div className="um-skeleton um-skeleton-block" style={{ marginTop: 14 }} />
      </div>
    </div>
  );
}

/* ── EmptyState ── */

export function EmptyState({ icon = Icons.sparkle, title, sub }) {
  return (
    <div className="um-empty-state">
      <div className="um-empty-icon">
        <Ico path={icon} size={28} />
      </div>
      <p className="um-empty-title">{title}</p>
      <p className="um-empty-sub">{sub}</p>
    </div>
  );
}
