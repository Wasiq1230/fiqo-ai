/**
 * Study workspace — all PDF-powered AI tools.
 *
 * Every backend call goes through lib/services.js (which targets the new
 * /api/pdf/* endpoints and returns a normalized `{ result }` shape). Errors
 * surface as toasts; in-flight work shows a skeleton loader. Nothing here
 * stores secrets or talks to the network directly.
 */
import { useRef, useState } from "react";
import * as svc from "../lib/services";
import { apiErrorMessage } from "../lib/api";
import { useToast } from "../components/Toast";
import { Ico, Icons, Spinner } from "../components/icons";
import { OutputBubble, Skeleton, EmptyState } from "../components/Output";

const PILLS = [
  { label: "Summarize", icon: Icons.summary, key: "summary" },
  { label: "Quiz", icon: Icons.quiz, key: "quiz" },
  { label: "Flashcards", icon: Icons.flashcard, key: "flashcards" },
  { label: "Viva Prep", icon: Icons.viva, key: "viva" },
  { label: "Study Plan", icon: Icons.plan, key: "plan" },
  { label: "Notes", icon: Icons.notes, key: "notes" },
  { label: "Scored Quiz", icon: Icons.star, key: "scoredQuiz" },
];

export default function WorkspaceScreen({ section, setSection, userName }) {
  const toast = useToast();

  const [file, setFile] = useState(null);
  const [multiFiles, setMultiFiles] = useState([]);
  const [pdfPreview, setPdfPreview] = useState(null);
  const [question, setQuestion] = useState("");
  const [keyword, setKeyword] = useState("");
  const [difficulty, setDifficulty] = useState("easy");
  const [notesType, setNotesType] = useState("short");
  const [showUploadPanel, setShowUploadPanel] = useState(false);
  const [showSearchPanel, setShowSearchPanel] = useState(false);

  const [summary, setSummary] = useState("");
  const [quiz, setQuiz] = useState("");
  const [searchResults, setSearchResults] = useState("");
  const [scoredQuiz, setScoredQuiz] = useState([]);
  const [userAnswers, setUserAnswers] = useState({});
  const [quizScore, setQuizScore] = useState(null);
  const [flashcards, setFlashcards] = useState("");
  const [viva, setViva] = useState("");
  const [studyPlan, setStudyPlan] = useState("");
  const [notes, setNotes] = useState("");
  const [answer, setAnswer] = useState("");
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState("");

  const fileInputRef = useRef(null);
  const multiFileInputRef = useRef(null);

  const addHistory = (label) =>
    setHistory((p) => [`${new Date().toLocaleTimeString()} — ${label}`, ...p].slice(0, 50));

  const needFile = () => {
    if (!file) {
      toast.info("Upload a PDF first.");
      setShowUploadPanel(true);
      return true;
    }
    return false;
  };
  const needMulti = () => {
    if (!multiFiles.length) {
      toast.info("Upload one or more PDFs first.");
      setShowUploadPanel(true);
      return true;
    }
    return false;
  };

  /** Run a service call with unified loading + error handling. */
  const run = async (key, fn, setter, section, label) => {
    try {
      setLoading(key);
      const result = await fn();
      setter(result);
      if (section) setSection(section);
      addHistory(label);
    } catch (err) {
      toast.error(apiErrorMessage(err, `${label} failed.`));
    } finally {
      setLoading("");
    }
  };

  const doSummary = () => !needFile() && run("summary", () => svc.summarize(file), setSummary, "Summary", "Summary");
  const doMultiSummary = () => !needMulti() && run("multiSummary", () => svc.multiSummarize(multiFiles), setSummary, "Summary", "Multi Summary");
  const doQuiz = () => !needFile() && run("quiz", () => svc.quiz(file), setQuiz, "Quiz", "Quiz");
  const doQuizDiff = () => !needFile() && run("quizDiff", () => svc.quizByDifficulty(file, difficulty), setQuiz, "Quiz", `${difficulty} Quiz`);
  const doMultiQuiz = () => !needMulti() && run("multiQuiz", () => svc.multiQuiz(multiFiles), setQuiz, "Quiz", "Multi Quiz");
  const doFlashcards = () => !needFile() && run("flashcards", () => svc.flashcards(file), setFlashcards, "Flashcards", "Flashcards");
  const doViva = () => !needFile() && run("viva", () => svc.viva(file), setViva, "Viva", "Viva");
  const doPlan = () => !needFile() && run("plan", () => svc.studyPlan(file), setStudyPlan, "Study Plan", "Study Plan");
  const doNotes = (t) => !needFile() && run(t, () => svc.notes(file, t), setNotes, "Notes", `${t} Notes`);

  const doScoredQuiz = async () => {
    if (needFile()) return;
    try {
      setLoading("scoredQuiz");
      setQuizScore(null);
      setUserAnswers({});
      const q = await svc.scoredQuiz(file);
      setScoredQuiz(q);
      setSection("Quiz");
      addHistory("Scored Quiz");
    } catch (err) {
      toast.error(apiErrorMessage(err, "Scored quiz failed."));
    } finally {
      setLoading("");
    }
  };

  const doSearchSingle = () => {
    if (needFile()) return;
    if (!keyword.trim()) return toast.info("Enter a keyword to search.");
    run("search", () => svc.search(file, keyword), setSearchResults, "Search", "Search");
  };
  const doSearchMulti = () => {
    if (needMulti()) return;
    if (!keyword.trim()) return toast.info("Enter a keyword to search.");
    run("msearch", () => svc.multiSearch(multiFiles, keyword), setSearchResults, "Search", "Multi Search");
  };
  const doChat = () => {
    if (needFile()) return;
    if (!question.trim()) return;
    run("chat", () => svc.chat(file, question), setAnswer, "Chat", "Chat");
  };
  const doMultiChat = () => {
    if (needMulti()) return;
    if (!question.trim()) return;
    run("mchat", () => svc.multiChat(multiFiles, question), setAnswer, "Chat", "Multi Chat");
  };

  const startVoice = () => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) return toast.info("Voice input needs Chrome or Edge.");
    const r = new SR();
    r.lang = "en-US";
    r.start();
    r.onresult = (e) => setQuestion(e.results[0][0].transcript);
    r.onerror = (e) => toast.error("Voice error: " + e.error);
  };

  const submitScoredQuiz = () => {
    let score = 0;
    scoredQuiz.forEach((q, i) => {
      if (userAnswers[i] === q.correct_answer) score++;
    });
    setQuizScore(score);
    addHistory(`Quiz Score: ${score}/${scoredQuiz.length}`);
  };

  const handlePill = (key) => {
    const map = {
      summary: doSummary, quiz: doQuiz, flashcards: doFlashcards,
      viva: doViva, plan: doPlan, notes: () => doNotes(notesType), scoredQuiz: doScoredQuiz,
    };
    map[key]?.();
  };

  const handleChatSubmit = (e) => {
    e?.preventDefault();
    if (!question.trim()) return;
    if (section === "Search") {
      setKeyword(question);
      if (!needFile()) run("search", () => svc.search(file, question), setSearchResults, "Search", "Search");
    } else {
      doChat();
    }
  };

  const Ld = (k, label) => (loading === k ? "Generating…" : label);
  const busy = !!loading;

  const onPickFile = (e) => {
    const f = e.target.files[0];
    setFile(f || null);
    if (f) setPdfPreview(URL.createObjectURL(f));
  };

  return (
    <>
      <div className="um-feed">
        {/* DASHBOARD */}
        {section === "Dashboard" && (
          <div className="um-dashboard">
            <div className="um-hero">
              <div className="um-hero-badge">
                <Ico path={Icons.sparkle} size={12} /> AI Study Workspace
              </div>
              <h1 className="um-hero-title">
                What are we learning<br />today, <em>{userName?.split(" ")[0] || "friend"}</em>?
              </h1>
              <p className="um-hero-sub">
                Upload a PDF and ask anything. Generate summaries, quizzes, flashcards,
                viva questions, study plans, and more.
              </p>
              <div className="um-pills">
                {PILLS.map((p) => (
                  <button key={p.key} className="um-pill" onClick={() => handlePill(p.key)} disabled={loading === p.key}>
                    <Ico path={p.icon} size={13} />
                    {loading === p.key ? "Generating…" : p.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="um-stats">
              {[
                { label: "PDF Loaded", value: file ? "1" : "—", sub: file ? file.name.slice(0, 22) : "No file yet" },
                { label: "Multi PDFs", value: multiFiles.length || "—", sub: multiFiles.length ? `${multiFiles.length} files` : "None uploaded" },
                { label: "Generations", value: history.length || "0", sub: "AI outputs created" },
                {
                  label: "Quiz Accuracy",
                  value: quizScore !== null && scoredQuiz.length ? `${Math.round((quizScore / scoredQuiz.length) * 100)}%` : "—",
                  sub: "Last scored quiz",
                },
              ].map((s) => (
                <div key={s.label} className="um-stat-card">
                  <p className="um-stat-label">{s.label}</p>
                  <p className="um-stat-value">{s.value}</p>
                  <p className="um-stat-sub">{s.sub}</p>
                </div>
              ))}
            </div>

            {loading && <Skeleton />}

            {(notes || summary) && !loading && (
              <div className="um-recent-grid">
                {notes && <OutputBubble title="AI Notes" text={notes} filename="notes.txt" />}
                {summary && <OutputBubble title="AI Summary" text={summary} filename="summary.txt" />}
              </div>
            )}
          </div>
        )}

        {/* SIMPLE OUTPUT SECTIONS */}
        {section === "Summary" && (loading ? <Skeleton /> : summary && <OutputBubble title="AI Summary" text={summary} filename="summary.txt" />)}
        {section === "Flashcards" && (loading ? <Skeleton /> : flashcards && <OutputBubble title="Flashcards" text={flashcards} filename="flashcards.txt" />)}
        {section === "Viva" && (loading ? <Skeleton /> : viva && <OutputBubble title="Viva Questions" text={viva} filename="viva.txt" />)}
        {section === "Study Plan" && (loading ? <Skeleton /> : studyPlan && <OutputBubble title="7-Day Study Plan" text={studyPlan} filename="study-plan.txt" />)}
        {section === "Chat" && (loading ? <Skeleton /> : answer && <OutputBubble title="Answer" text={answer} filename="chat-answer.txt" />)}

        {/* NOTES */}
        {section === "Notes" && (
          <>
            <div className="um-section-toolbar">
              <p className="um-section-heading"><Ico path={Icons.notes} size={15} /> Notes Generator</p>
              <div className="um-toolbar-btns">
                {["short", "detailed", "exam"].map((t) => (
                  <button key={t} className={`um-btn um-btn-sm${notesType === t ? " um-btn-active" : ""}`} onClick={() => { setNotesType(t); doNotes(t); }} disabled={loading === t}>
                    {loading === t ? "Generating…" : t.charAt(0).toUpperCase() + t.slice(1)}
                  </button>
                ))}
              </div>
            </div>
            {loading ? <Skeleton /> : notes && <OutputBubble title="AI Notes" text={notes} filename="notes.txt" />}
          </>
        )}

        {/* SEARCH */}
        {section === "Search" && (
          <>
            <div className="um-section-toolbar">
              <p className="um-section-heading"><Ico path={Icons.search} size={15} /> Search Results</p>
              <div className="um-toolbar-btns">
                <button className="um-btn um-btn-sm" onClick={doSearchMulti} disabled={busy}>{Ld("msearch", "Search Multi PDFs")}</button>
              </div>
            </div>
            {loading ? <Skeleton /> : searchResults && <OutputBubble title="Search Results" text={searchResults} filename="search.txt" />}
          </>
        )}

        {/* QUIZ */}
        {section === "Quiz" && (
          <>
            <div className="um-section-toolbar">
              <p className="um-section-heading"><Ico path={Icons.quiz} size={15} /> Quiz</p>
              <div className="um-toolbar-btns">
                <select className="um-select" value={difficulty} onChange={(e) => setDifficulty(e.target.value)} aria-label="Quiz difficulty">
                  <option value="easy">Easy</option>
                  <option value="medium">Medium</option>
                  <option value="hard">Hard</option>
                </select>
                <button className="um-btn um-btn-sm" onClick={doQuizDiff} disabled={busy}>{Ld("quizDiff", "Difficulty Quiz")}</button>
                <button className="um-btn um-btn-sm" onClick={doMultiQuiz} disabled={busy}>{Ld("multiQuiz", "Multi Quiz")}</button>
                <button className="um-btn um-btn-sm" onClick={doScoredQuiz} disabled={busy}>{Ld("scoredQuiz", "Scored Quiz")}</button>
              </div>
            </div>

            {loading && (loading === "quiz" || loading === "quizDiff" || loading === "multiQuiz" || loading === "scoredQuiz") && <Skeleton />}
            {!loading && quiz && <OutputBubble title="AI Quiz" text={quiz} filename="quiz.txt" />}

            {!loading && scoredQuiz.length > 0 && (
              <div className="um-bubble">
                <div className="um-bubble-header">
                  <div className="um-bubble-title">
                    <div className="um-bubble-avatar"><Ico path={Icons.star} size={13} /></div>
                    <span>Scored Quiz</span>
                  </div>
                  {quizScore !== null && (
                    <div className="um-score-badge">
                      {quizScore}/{scoredQuiz.length} · {Math.round((quizScore / scoredQuiz.length) * 100)}%
                    </div>
                  )}
                </div>
                <div className="um-bubble-body">
                  <div className="um-quiz-list">
                    {scoredQuiz.map((q, i) => (
                      <div key={i} className="um-quiz-q">
                        <p className="um-quiz-qtext">{i + 1}. {q.question}</p>
                        <div className="um-quiz-opts">
                          {Object.entries(q.options).map(([k, v]) => (
                            <label key={k} className="um-quiz-opt">
                              <input type="radio" name={`q-${i}`} value={k} checked={userAnswers[i] === k} onChange={() => setUserAnswers({ ...userAnswers, [i]: k })} />
                              <span>{k}) {v}</span>
                            </label>
                          ))}
                        </div>
                        {quizScore !== null && (
                          <p className={userAnswers[i] === q.correct_answer ? "um-correct" : "um-wrong"}>
                            {userAnswers[i] === q.correct_answer ? "✓ Correct" : `✗ Correct: ${q.correct_answer}`}
                          </p>
                        )}
                      </div>
                    ))}
                    <button className="um-btn um-btn-primary" onClick={submitScoredQuiz} disabled={Object.keys(userAnswers).length === 0}>
                      Submit &amp; Score
                    </button>
                  </div>
                </div>
              </div>
            )}
          </>
        )}

        {/* HISTORY */}
        {section === "History" && (
          <div className="um-bubble">
            <div className="um-bubble-header">
              <div className="um-bubble-title">
                <div className="um-bubble-avatar"><Ico path={Icons.history} size={13} /></div>
                <span>Activity History</span>
              </div>
              <button className="um-btn um-btn-sm" onClick={() => setHistory([])} disabled={!history.length}>Clear all</button>
            </div>
            <div className="um-bubble-body">
              {history.length === 0 ? (
                <p className="um-empty">No activity yet. Start generating content.</p>
              ) : (
                <div className="um-history-list">
                  {history.map((h, i) => (
                    <div key={i} className="um-history-item"><span className="um-history-dot" />{h}</div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* EMPTY STATES */}
        {["Summary", "Flashcards", "Viva", "Study Plan", "Chat"].includes(section) &&
          !loading && !summary && !flashcards && !viva && !studyPlan && !answer && (
            <EmptyState title="Nothing here yet" sub="Upload a PDF and use the input below to generate content." />
          )}
        {section === "Search" && !loading && !searchResults && (
          <EmptyState icon={Icons.search} title="Search your PDFs" sub="Open the search panel or type a keyword below." />
        )}
      </div>

      {/* UPLOAD PANEL */}
      {showUploadPanel && (
        <div className="um-panel-overlay" onClick={() => setShowUploadPanel(false)}>
          <div className="um-panel" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-label="Manage PDFs">
            <div className="um-panel-header">
              <p className="um-panel-title"><Ico path={Icons.attach} size={15} /> Manage PDFs</p>
              <button className="um-icon-btn" onClick={() => setShowUploadPanel(false)} aria-label="Close"><Ico path={Icons.close} size={15} /></button>
            </div>

            <div className="um-upload-section">
              <p className="um-upload-label">Single PDF</p>
              <label className="um-upload-drop">
                <Ico path={Icons.upload} size={20} />
                <span>{file ? file.name : "Click to browse a PDF"}</span>
                {file && <span className="um-file-badge"><Ico path={Icons.check} size={11} /> {file.name}</span>}
                <input ref={fileInputRef} type="file" accept="application/pdf" style={{ display: "none" }} onChange={onPickFile} />
              </label>
              <div className="um-btn-row">
                <button className="um-btn um-btn-sm" onClick={doSummary} disabled={busy}>{Ld("summary", "Summary")}</button>
                <button className="um-btn um-btn-sm" onClick={doQuiz} disabled={busy}>{Ld("quiz", "Quiz")}</button>
                <button className="um-btn um-btn-sm" onClick={doFlashcards} disabled={busy}>{Ld("flashcards", "Flashcards")}</button>
                <button className="um-btn um-btn-sm" onClick={doViva} disabled={busy}>{Ld("viva", "Viva")}</button>
                <button className="um-btn um-btn-sm" onClick={doPlan} disabled={busy}>{Ld("plan", "Study Plan")}</button>
                <button className="um-btn um-btn-sm" onClick={doScoredQuiz} disabled={busy}>{Ld("scoredQuiz", "Scored Quiz")}</button>
              </div>
            </div>

            <div className="um-upload-section">
              <p className="um-upload-label">Multiple PDFs</p>
              <label className="um-upload-drop">
                <Ico path={Icons.upload} size={20} />
                <span>Select multiple PDFs</span>
                {multiFiles.length > 0 && <span className="um-file-badge"><Ico path={Icons.check} size={11} /> {multiFiles.length} files</span>}
                <input ref={multiFileInputRef} type="file" accept="application/pdf" multiple style={{ display: "none" }} onChange={(e) => setMultiFiles(Array.from(e.target.files))} />
              </label>
              <div className="um-btn-row">
                <button className="um-btn um-btn-sm" onClick={doMultiSummary} disabled={busy}>{Ld("multiSummary", "Multi Summary")}</button>
                <button className="um-btn um-btn-sm" onClick={doMultiQuiz} disabled={busy}>{Ld("multiQuiz", "Multi Quiz")}</button>
                <button className="um-btn um-btn-sm" onClick={doMultiChat} disabled={busy}>{Ld("mchat", "Ask Multi")}</button>
              </div>
            </div>

            {pdfPreview && (
              <div className="um-upload-section">
                <p className="um-upload-label">PDF Preview</p>
                <iframe src={pdfPreview} className="um-pdf-iframe" title="PDF Preview" />
              </div>
            )}
          </div>
        </div>
      )}

      {/* SEARCH PANEL */}
      {showSearchPanel && (
        <div className="um-panel-overlay" onClick={() => setShowSearchPanel(false)}>
          <div className="um-panel um-panel-sm" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-label="Search PDF">
            <div className="um-panel-header">
              <p className="um-panel-title"><Ico path={Icons.search} size={15} /> Search PDF</p>
              <button className="um-icon-btn" onClick={() => setShowSearchPanel(false)} aria-label="Close"><Ico path={Icons.close} size={15} /></button>
            </div>
            <div className="um-upload-section">
              <input className="um-input" placeholder="Enter keyword or topic…" value={keyword} onChange={(e) => setKeyword(e.target.value)} onKeyDown={(e) => e.key === "Enter" && doSearchSingle()} />
              <div className="um-btn-row" style={{ marginTop: 10 }}>
                <button className="um-btn um-btn-sm um-btn-primary" onClick={() => { doSearchSingle(); setShowSearchPanel(false); setSection("Search"); }} disabled={busy}>{Ld("search", "Search Single PDF")}</button>
                <button className="um-btn um-btn-sm" onClick={() => { doSearchMulti(); setShowSearchPanel(false); setSection("Search"); }} disabled={busy}>{Ld("msearch", "Search Multi PDFs")}</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* INPUT BAR */}
      <div className="um-input-bar">
        <div className="um-input-inner">
          {file && (
            <div className="um-input-file-badge">
              <Ico path={Icons.file} size={12} />
              <span>{file.name.length > 20 ? file.name.slice(0, 20) + "…" : file.name}</span>
              <button className="um-input-file-remove" onClick={() => { setFile(null); setPdfPreview(null); }} aria-label="Remove file"><Ico path={Icons.close} size={10} /></button>
            </div>
          )}
          <form className="um-input-row" onSubmit={handleChatSubmit}>
            <button type="button" className="um-input-icon-btn" onClick={() => setShowUploadPanel(true)} title="Manage PDFs" aria-label="Manage PDFs"><Ico path={Icons.attach} size={17} /></button>
            <button type="button" className="um-input-icon-btn" onClick={() => setShowSearchPanel(true)} title="Search PDF" aria-label="Search PDF"><Ico path={Icons.search} size={17} /></button>
            <input
              className="um-chat-input"
              placeholder={section === "Search" ? "Search for a keyword in your PDF…" : "Ask anything about your PDF…"}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              aria-label="Ask a question"
            />
            <button type="button" className="um-input-icon-btn" onClick={startVoice} title="Voice input" aria-label="Voice input"><Ico path={Icons.mic} size={17} /></button>
            {multiFiles.length > 0 && (
              <button type="button" className="um-input-icon-btn" onClick={doMultiChat} disabled={busy} title="Ask multiple PDFs" aria-label="Ask multiple PDFs"><Ico path={Icons.grid} size={16} /></button>
            )}
            <button type="submit" className="um-send-btn" disabled={!question.trim() || busy} aria-label="Send">
              {loading === "chat" || loading === "mchat" ? <Spinner /> : <Ico path={Icons.send} size={15} strokeWidth={2} />}
            </button>
          </form>
        </div>
        <p className="um-input-hint">FIQO uses AI. Always verify important information.</p>
      </div>
    </>
  );
}
