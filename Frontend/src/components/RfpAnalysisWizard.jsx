import { useState, useEffect, useRef } from 'react';
import { Loader2, FileSearch, HelpCircle, CheckCircle2, ArrowRight, SkipForward, AlertTriangle } from 'lucide-react';
import { api } from '../lib/api.jsx';

const POLL_MS = 2000;

/**
 * RfpAnalysisWizard.jsx
 * ----------------------
 * Uploads RFP → kicks off /rfp-respond/analyze → polls until ready →
 * shows clarifying questions GROUPED BY ROUND (all questions for a round at
 * once; the round counter advances when the user submits answers or skips).
 *
 * Props:
 *   rfpFiles          — File[] selected by user (can be empty if resuming)
 *   templateFile      — File | null
 *   resumeTaskId      — if set, skip upload and resume polling this task
 *   onTaskStarted     — (taskId: string) => void  called when analysis task is created
 *   onCancel          — () => void
 *   onReadyToGenerate — (taskId: string, answers: []) => void
 */
const ANALYZE_STEPS = [
  { key: 'upload', label: 'Upload received' },
  { key: 'parse', label: 'Parse RFP (all sections)' },
  { key: 'outline', label: 'Build response outline' },
  { key: 'questions', label: 'Prepare clarifying questions' },
];

function resolveAnalyzeStep(progress, message) {
  const msg = String(message || '').toLowerCase();
  if (progress >= 100) return 3;
  if (progress >= 80) return 3;
  if (progress >= 60) return 2;
  if (progress >= 40) return 1;
  if (progress >= 5) return 1;
  if (/clarif|question|ready for clarifying/.test(msg)) return 3;
  if (/building rfp-specific outline|deduping template/.test(msg)) return 2;
  if (/chunk |merging |pars|section-aware split/.test(msg)) return 1;
  if (/upload/.test(msg)) return 0;
  return 0;
}

export default function RfpAnalysisWizard({
  rfpFiles,
  templateFile,
  resumeTaskId,
  onTaskStarted,
  onCancel,
  onReadyToGenerate,
}) {
  const [phase, setPhase] = useState('analyzing');
  const [taskId, setTaskId] = useState(resumeTaskId || null);
  const [analysis, setAnalysis] = useState(null);
  const [answers, setAnswers] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [analyzeProgress, setAnalyzeProgress] = useState(resumeTaskId ? 30 : 0);
  const [analyzeMessage, setAnalyzeMessage] = useState(
    resumeTaskId ? 'Resuming analysis — checking status…' : 'Starting analysis…'
  );
  const pollRef = useRef(null);
  const startedRef = useRef(false);

  // ---- Upload & kick off analysis (skip if resuming) ----
  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;

    if (resumeTaskId) {
      // Already have a task — go straight to polling
      return;
    }

    (async () => {
      try {
        const { task_id } = await api.analyzeRfp(rfpFiles, templateFile);
        setTaskId(task_id);
        if (onTaskStarted) onTaskStarted(task_id);
        setAnalyzeMessage('Upload accepted — parsing RFP…');
        setAnalyzeProgress(5);
      } catch (err) {
        setError(err.message || 'Failed to start RFP analysis.');
        setPhase('error');
      }
    })();
  }, []);

  // ---- Poll task status ----
  useEffect(() => {
    if (!taskId || phase !== 'analyzing') return;
    pollRef.current = setInterval(async () => {
      try {
        const state = await api.getRfpAnalyzeStatus(taskId);
        if (typeof state.progress === 'number') setAnalyzeProgress(state.progress);
        if (state.message) setAnalyzeMessage(state.message);

        if (state.status === 'completed') {
          clearInterval(pollRef.current);
          setAnalyzeProgress(100);
          const result = state.result?.analysis || state.analysis || null;
          if (!result) {
            setError('Analysis completed but returned no data.');
            setPhase('error');
            return;
          }
          setAnalysis(result);
          if (Array.isArray(result.questions) && result.questions.length > 0) {
            setPhase('questions');
          } else {
            onReadyToGenerate(taskId, []);
          }
        } else if (state.status === 'failed') {
          clearInterval(pollRef.current);
          setError(state.message || 'RFP analysis failed.');
          setPhase('error');
        }
      } catch (err) {
        console.warn('RFP analyze poll error:', err);
      }
    }, POLL_MS);
    return () => clearInterval(pollRef.current);
  }, [taskId, phase]);

  function setAnswer(id, value) {
    setAnswers((prev) => ({ ...prev, [id]: value }));
  }

  async function handleSubmitAnswers() {
    if (!analysis) return;
    setSubmitting(true);
    setError('');
    try {
      const payload = (analysis.questions || [])
        .map((q) => ({ id: q.id, question: q.question, answer: answers[q.id] }))
        .filter((a) => a.answer !== undefined && a.answer !== '' && (!Array.isArray(a.answer) || a.answer.length > 0));

      const res = await api.clarifyRfp(taskId, payload);
      if (Array.isArray(res.questions) && res.questions.length > 0) {
        // Next round — show ALL new questions for this round at once
        setAnalysis((prev) => ({
          ...prev,
          questions: res.questions,
          round: res.round ?? (prev?.round || 1) + 1,
          is_final_round: !!res.is_final_round,
        }));
        setAnswers({});
        setPhase('questions');
        setSubmitting(false);
      } else {
        onReadyToGenerate(taskId, payload);
      }
    } catch (err) {
      setError(err.message || 'Failed to submit answers.');
      setSubmitting(false);
    }
  }

  function handleSkipAll() {
    onReadyToGenerate(taskId, []);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
      <div className="bg-white dark:bg-slate-900 rounded-xl shadow-2xl w-full max-w-2xl max-h-[85vh] overflow-y-auto border border-slate-200 dark:border-slate-700">
        <div className="p-6 border-b border-slate-200 dark:border-slate-700">
          <h2 className="text-lg font-semibold flex items-center gap-2 text-slate-900 dark:text-white">
            {phase === 'analyzing' ? (
              <><FileSearch className="w-5 h-5 text-blue-500" /> Reading your RFP…</>
            ) : phase === 'error' ? (
              <><AlertTriangle className="w-5 h-5 text-red-500" /> Analysis Failed</>
            ) : (
              <><HelpCircle className="w-5 h-5 text-blue-500" /> A few things we need from you</>
            )}
          </h2>
          {phase === 'questions' && analysis && (
            <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
              We read the RFP and built a {analysis.outline?.sections?.length || 0}-section outline tailored to it.
              {analysis.round > 1 ? ` Round ${analysis.round} of clarification.` : ''}
              {' '}Answer what you know — blank fields get a clearly marked placeholder.
            </p>
          )}
          {resumeTaskId && phase === 'analyzing' && (
            <p className="text-xs text-amber-600 dark:text-amber-400 mt-1">↩ Resumed from where you left off.</p>
          )}
        </div>

        <div className="p-6">
          {/* ---- ANALYZING PHASE ---- */}
          {phase === 'analyzing' && (
            <div className="py-6 space-y-5">
              <div className="flex items-center gap-3 text-slate-600 dark:text-slate-300">
                <Loader2 className="w-6 h-6 animate-spin text-blue-500 shrink-0" />
                <div className="min-w-0">
                  <p className="text-sm font-medium text-slate-800 dark:text-slate-100">
                    {analyzeMessage || 'Working…'}
                  </p>
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                    Large multi-section tenders can take a minute or two — stages advance as each finishes.
                  </p>
                </div>
              </div>

              <div className="h-2 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
                <div
                  className="h-full rounded-full bg-blue-500 transition-all duration-500"
                  style={{ width: `${Math.min(100, Math.max(4, analyzeProgress))}%` }}
                />
              </div>
              <p className="text-xs font-semibold text-slate-500 text-right">{analyzeProgress}%</p>

              <ol className="space-y-2">
                {ANALYZE_STEPS.map((step, i) => {
                  const activeIdx = resolveAnalyzeStep(analyzeProgress, analyzeMessage);
                  const done = i < activeIdx || analyzeProgress >= 100;
                  const active = i === activeIdx && analyzeProgress < 100;
                  return (
                    <li
                      key={step.key}
                      className={`flex items-center gap-2.5 rounded-lg border px-3 py-2 text-sm ${
                        done
                          ? 'border-emerald-200 bg-emerald-50/60 text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950/30 dark:text-emerald-300'
                          : active
                            ? 'border-blue-200 bg-blue-50/60 text-blue-800 dark:border-blue-800 dark:bg-blue-950/30 dark:text-blue-300'
                            : 'border-slate-100 bg-slate-50/50 text-slate-400 dark:border-slate-800 dark:bg-slate-900/40'
                      }`}
                    >
                      {done ? (
                        <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-500" />
                      ) : active ? (
                        <Loader2 className="w-4 h-4 shrink-0 animate-spin text-blue-500" />
                      ) : (
                        <span className="w-4 h-4 shrink-0 rounded-full border border-slate-300 dark:border-slate-600" />
                      )}
                      <span className="font-medium">{i + 1}. {step.label}</span>
                      {active && <span className="ml-auto text-[10px] font-bold uppercase tracking-wide">In progress</span>}
                      {done && <span className="ml-auto text-[10px] font-bold uppercase tracking-wide">Done</span>}
                    </li>
                  );
                })}
              </ol>
            </div>
          )}

          {/* ---- ERROR PHASE ---- */}
          {phase === 'error' && (
            <div className="text-sm text-red-600 dark:text-red-400 py-4">{error}</div>
          )}

          {/* ---- QUESTIONS PHASE — ALL questions for this round at once ---- */}
          {phase === 'questions' && analysis && (() => {
            const allQ = analysis.questions || [];
            const round = analysis.round || 1;
            const isFinalRound = analysis.is_final_round;
            return (
              <div className="space-y-6">
                {/* Round indicator */}
                <div className="flex items-center justify-between text-xs">
                  <span className="font-semibold text-slate-700 dark:text-slate-300">
                    Round {round}{isFinalRound ? ' — Final round' : ''} · {allQ.length} question{allQ.length !== 1 ? 's' : ''}
                  </span>
                  {isFinalRound && (
                    <span className="text-amber-600 dark:text-amber-400 font-medium text-xs">
                      Only critical items remain
                    </span>
                  )}
                </div>

                {/* RFP summary on round 1 */}
                {analysis.summary && round === 1 && (
                  <div className="text-sm text-slate-600 dark:text-slate-300 bg-slate-50 dark:bg-slate-800 rounded-lg p-3 border border-slate-200 dark:border-slate-700">
                    {analysis.summary}
                  </div>
                )}

                {/* All questions for this round */}
                {allQ.map((q, qIdx) => (
                  <div key={q.id} className="space-y-2 pb-5 border-b border-slate-100 dark:border-slate-800 last:border-0 last:pb-0">
                    <div className="flex items-start gap-2">
                      <span className="text-xs font-bold text-slate-400 dark:text-slate-500 mt-0.5 shrink-0 w-5">Q{qIdx + 1}</span>
                      <label className="block text-sm font-medium text-slate-800 dark:text-slate-100">
                        {q.question}
                        {q.allow_skip === false && <span className="text-red-500 ml-1">*</span>}
                      </label>
                    </div>
                    {q.why_it_matters && (
                      <p className="text-xs text-slate-400 dark:text-slate-500 ml-7">{q.why_it_matters}</p>
                    )}
                    {q.category && (
                      <span className="ml-7 inline-block text-[10px] font-semibold uppercase tracking-wide text-slate-400 bg-slate-100 dark:bg-slate-800 rounded px-1.5 py-0.5">
                        {q.category}
                      </span>
                    )}

                    <div className="ml-7">
                      {q.input_type === 'single_select' && Array.isArray(q.options) && q.options.length > 0 ? (
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-1">
                          {q.options.map((opt) => (
                            <button
                              key={opt.id}
                              type="button"
                              onClick={() => setAnswer(q.id, opt.label)}
                              className={`text-left px-3 py-2 rounded-lg border text-sm transition-colors ${
                                answers[q.id] === opt.label
                                  ? 'border-blue-500 bg-blue-50 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300'
                                  : 'border-slate-200 dark:border-slate-700 hover:border-blue-300 text-slate-700 dark:text-slate-300'
                              }`}
                            >
                              <div className="font-medium">{opt.label}</div>
                              {opt.description && <div className="text-xs text-slate-400 mt-0.5">{opt.description}</div>}
                            </button>
                          ))}
                        </div>
                      ) : q.input_type === 'multi_select' && Array.isArray(q.options) && q.options.length > 0 ? (
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-1">
                          {q.options.map((opt) => {
                            const selected = Array.isArray(answers[q.id]) && answers[q.id].includes(opt.label);
                            return (
                              <button
                                key={opt.id}
                                type="button"
                                onClick={() => {
                                  const current = Array.isArray(answers[q.id]) ? answers[q.id] : [];
                                  setAnswer(
                                    q.id,
                                    selected ? current.filter((v) => v !== opt.label) : [...current, opt.label]
                                  );
                                }}
                                className={`text-left px-3 py-2 rounded-lg border text-sm transition-colors ${
                                  selected
                                    ? 'border-blue-500 bg-blue-50 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300'
                                    : 'border-slate-200 dark:border-slate-700 hover:border-blue-300 text-slate-700 dark:text-slate-300'
                                }`}
                              >
                                {opt.label}
                              </button>
                            );
                          })}
                        </div>
                      ) : (
                        <textarea
                          rows={3}
                          value={answers[q.id] || ''}
                          onChange={(e) => setAnswer(q.id, e.target.value)}
                          className="w-full text-sm rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2 text-slate-800 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500 mt-1"
                          placeholder={q.allow_skip === false ? 'Required — this affects compliance' : 'Optional — leave blank to use a placeholder'}
                        />
                      )}
                    </div>
                  </div>
                ))}

                {error && <div className="text-sm text-red-600 dark:text-red-400">{error}</div>}
              </div>
            );
          })()}
        </div>

        <div className="p-6 border-t border-slate-200 dark:border-slate-700 flex items-center justify-between gap-3">
          <button
            type="button"
            onClick={onCancel}
            className="text-sm text-slate-500 hover:text-slate-700 dark:hover:text-slate-300"
          >
            Cancel
          </button>
          {phase === 'questions' && (
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleSkipAll}
                disabled={submitting}
                className="flex items-center gap-1.5 text-sm px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-500 hover:bg-slate-50 dark:hover:bg-slate-800"
              >
                <SkipForward className="w-4 h-4" /> Skip &amp; generate now
              </button>
              <button
                type="button"
                onClick={handleSubmitAnswers}
                disabled={submitting}
                className="flex items-center gap-1.5 text-sm px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-medium disabled:opacity-60"
              >
                {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <ArrowRight className="w-4 h-4" />}
                {analysis?.is_final_round === false ? 'Submit & continue' : 'Generate Proposal'}
              </button>
            </div>
          )}
          {phase === 'error' && (
            <button
              type="button"
              onClick={onCancel}
              className="text-sm px-4 py-2 rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300"
            >
              Close
            </button>
          )}
        </div>
      </div>
    </div>
  );
}


const POLL_MS = 2000;

/**
 * RfpAnalysisWizard.jsx
 * ----------------------
 * Replaces the old flow where PreGenerationWizard opened immediately on file
 * selection and asked generic, RFP-blind questions (the uploaded RFP hadn't
 * even reached the server yet at that point).
 *
 * This component:
 *   1. Uploads the RFP (+ optional template) and kicks off /rfp-respond/analyze
 *      -- the RFP is actually parsed, an RFP-specific outline is built, and a
 *      short list of genuinely-necessary clarifying questions is generated
 *      from THIS document's own gaps/mandatory-forms, not a generic list.
 *   2. Polls until analysis is ready, then shows those questions (if any).
 *   3. On submit, calls /rfp-respond/clarify -- if the RFP still has open
 *      items after this round (capped at 3 rounds total), shows the next
 *      round; once questions come back empty, proceeds straight to
 *      generation, reusing the already-uploaded files/parsed RFP/outline so
 *      nothing has to be re-uploaded or re-parsed.
 */
const ANALYZE_STEPS = [
  { key: 'upload', label: 'Upload received' },
  { key: 'parse', label: 'Parse RFP (all sections)' },
  { key: 'outline', label: 'Build response outline' },
  { key: 'questions', label: 'Prepare clarifying questions' },
];

function resolveAnalyzeStep(progress, message) {
  const msg = String(message || '').toLowerCase();
  // Prefer numeric bands — message keywords are secondary and must not
  // mis-fire on "section-aware" during parse (that used to jump to outline).
  if (progress >= 100) return 3;
  if (progress >= 80) return 3;
  if (progress >= 60) return 2;
  if (progress >= 40) return 1; // parse finished → show parse as done, outline next
  if (progress >= 5) return 1;  // still parsing (incl. chunk N/M)
  if (/clarif|question|ready for clarifying/.test(msg)) return 3;
  if (/building rfp-specific outline|deduping template/.test(msg)) return 2;
  if (/chunk |merging |pars|section-aware split/.test(msg)) return 1;
  if (/upload/.test(msg)) return 0;
  return 0;
}

export default function RfpAnalysisWizard({ rfpFiles, templateFile, onCancel, onReadyToGenerate }) {
  const [phase, setPhase] = useState('analyzing'); // analyzing | questions | error
  const [taskId, setTaskId] = useState(null);
  const [analysis, setAnalysis] = useState(null); // { rfp_type, summary, outline, questions, round, is_final_round }
  const [answers, setAnswers] = useState({}); // { [questionId]: value }
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [analyzeProgress, setAnalyzeProgress] = useState(0);
  const [analyzeMessage, setAnalyzeMessage] = useState('Starting analysis…');
  // Question pagination — one question per page so long RFP forms stay usable
  const [qPage, setQPage] = useState(0);
  const QUESTIONS_PER_PAGE = 1;
  const pollRef = useRef(null);
  const startedRef = useRef(false);

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;
    (async () => {
      try {
        const { task_id } = await api.analyzeRfp(rfpFiles, templateFile);
        setTaskId(task_id);
        setAnalyzeMessage('Upload accepted — parsing RFP…');
        setAnalyzeProgress(5);
      } catch (err) {
        setError(err.message || 'Failed to start RFP analysis.');
        setPhase('error');
      }
    })();
  }, []);

  useEffect(() => {
    if (!taskId || phase !== 'analyzing') return;
    pollRef.current = setInterval(async () => {
      try {
        const state = await api.getRfpAnalyzeStatus(taskId);
        if (typeof state.progress === 'number') setAnalyzeProgress(state.progress);
        if (state.message) setAnalyzeMessage(state.message);

        if (state.status === 'completed') {
          clearInterval(pollRef.current);
          setAnalyzeProgress(100);
          const result = state.result?.analysis || state.analysis || null;
          if (!result) {
            setError('Analysis completed but returned no data.');
            setPhase('error');
            return;
          }
          setAnalysis(result);
          if (Array.isArray(result.questions) && result.questions.length > 0) {
            setPhase('questions');
          } else {
            onReadyToGenerate(taskId, []);
          }
        } else if (state.status === 'failed') {
          clearInterval(pollRef.current);
          setError(state.message || 'RFP analysis failed.');
          setPhase('error');
        }
      } catch (err) {
        console.warn('RFP analyze poll error:', err);
      }
    }, POLL_MS);
    return () => clearInterval(pollRef.current);
  }, [taskId, phase]);

  function setAnswer(id, value) {
    setAnswers((prev) => ({ ...prev, [id]: value }));
  }

  async function handleSubmitAnswers() {
    if (!analysis) return;
    setSubmitting(true);
    setError('');
    try {
      const payload = (analysis.questions || [])
        .map((q) => ({ id: q.id, question: q.question, answer: answers[q.id] }))
        .filter((a) => a.answer !== undefined && a.answer !== '' && (!Array.isArray(a.answer) || a.answer.length > 0));

      const res = await api.clarifyRfp(taskId, payload);
      // Show ANY remaining questions (including final-round). Only start
      // generation when the server returns an empty list.
      if (Array.isArray(res.questions) && res.questions.length > 0) {
        setAnalysis((prev) => ({
          ...prev,
          questions: res.questions,
          round: res.round ?? (prev?.round || 1) + 1,
          is_final_round: !!res.is_final_round,
        }));
        setAnswers({});
        setQPage(0);
        setPhase('questions');
        setSubmitting(false);
      } else {
        onReadyToGenerate(taskId, payload);
      }
    } catch (err) {
      setError(err.message || 'Failed to submit answers.');
      setSubmitting(false);
    }
  }

  function handleSkipAll() {
    onReadyToGenerate(taskId, []);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
      <div className="bg-white dark:bg-slate-900 rounded-xl shadow-2xl w-full max-w-2xl max-h-[85vh] overflow-y-auto border border-slate-200 dark:border-slate-700">
        <div className="p-6 border-b border-slate-200 dark:border-slate-700">
          <h2 className="text-lg font-semibold flex items-center gap-2 text-slate-900 dark:text-white">
            {phase === 'analyzing' ? (
              <><FileSearch className="w-5 h-5 text-blue-500" /> Reading your RFP…</>
            ) : phase === 'error' ? (
              <><AlertTriangle className="w-5 h-5 text-red-500" /> Analysis Failed</>
            ) : (
              <><HelpCircle className="w-5 h-5 text-blue-500" /> A few things we need from you</>
            )}
          </h2>
          {phase === 'questions' && analysis && (
            <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
              We read the RFP and built a {analysis.outline?.sections?.length || 0}-section outline tailored to it.
              {analysis.round > 1 ? ` (Round ${analysis.round} of clarification.)` : ''}
              {' '}Only answer what you know — anything left blank will be generated with a clearly marked placeholder.
            </p>
          )}
        </div>

        <div className="p-6">
          {phase === 'analyzing' && (
            <div className="py-6 space-y-5">
              <div className="flex items-center gap-3 text-slate-600 dark:text-slate-300">
                <Loader2 className="w-6 h-6 animate-spin text-blue-500 shrink-0" />
                <div className="min-w-0">
                  <p className="text-sm font-medium text-slate-800 dark:text-slate-100">
                    {analyzeMessage || 'Working…'}
                  </p>
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                    Large multi-section tenders can take a minute or two — stages advance as each finishes.
                  </p>
                </div>
              </div>

              <div className="h-2 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
                <div
                  className="h-full rounded-full bg-blue-500 transition-all duration-500"
                  style={{ width: `${Math.min(100, Math.max(4, analyzeProgress))}%` }}
                />
              </div>
              <p className="text-xs font-semibold text-slate-500 text-right">{analyzeProgress}%</p>

              <ol className="space-y-2">
                {ANALYZE_STEPS.map((step, i) => {
                  const activeIdx = resolveAnalyzeStep(analyzeProgress, analyzeMessage);
                  const done = i < activeIdx || analyzeProgress >= 100;
                  const active = i === activeIdx && analyzeProgress < 100;
                  return (
                    <li
                      key={step.key}
                      className={`flex items-center gap-2.5 rounded-lg border px-3 py-2 text-sm ${
                        done
                          ? 'border-emerald-200 bg-emerald-50/60 text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950/30 dark:text-emerald-300'
                          : active
                            ? 'border-blue-200 bg-blue-50/60 text-blue-800 dark:border-blue-800 dark:bg-blue-950/30 dark:text-blue-300'
                            : 'border-slate-100 bg-slate-50/50 text-slate-400 dark:border-slate-800 dark:bg-slate-900/40'
                      }`}
                    >
                      {done ? (
                        <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-500" />
                      ) : active ? (
                        <Loader2 className="w-4 h-4 shrink-0 animate-spin text-blue-500" />
                      ) : (
                        <span className="w-4 h-4 shrink-0 rounded-full border border-slate-300 dark:border-slate-600" />
                      )}
                      <span className="font-medium">{i + 1}. {step.label}</span>
                      {active && <span className="ml-auto text-[10px] font-bold uppercase tracking-wide">In progress</span>}
                      {done && <span className="ml-auto text-[10px] font-bold uppercase tracking-wide">Done</span>}
                    </li>
                  );
                })}
              </ol>
            </div>
          )}

          {phase === 'error' && (
            <div className="text-sm text-red-600 dark:text-red-400 py-4">{error}</div>
          )}

          {phase === 'questions' && analysis && (() => {
            const allQ = analysis.questions || [];
            const totalPages = Math.max(1, Math.ceil(allQ.length / QUESTIONS_PER_PAGE));
            const page = Math.min(qPage, totalPages - 1);
            const slice = allQ.slice(page * QUESTIONS_PER_PAGE, page * QUESTIONS_PER_PAGE + QUESTIONS_PER_PAGE);
            return (
            <div className="space-y-5">
              {analysis.summary && page === 0 && (
                <div className="text-sm text-slate-600 dark:text-slate-300 bg-slate-50 dark:bg-slate-800 rounded-lg p-3 border border-slate-200 dark:border-slate-700">
                  {analysis.summary}
                </div>
              )}

              <div className="flex items-center justify-between text-xs text-slate-500">
                <span>
                  Question {page * QUESTIONS_PER_PAGE + 1}
                  {allQ.length > 1 ? `–${Math.min((page + 1) * QUESTIONS_PER_PAGE, allQ.length)}` : ''} of {allQ.length}
                  {analysis.round ? ` · Round ${analysis.round}` : ''}
                  {analysis.is_final_round ? ' · Final round' : ''}
                </span>
                <span>Page {page + 1} / {totalPages}</span>
              </div>

              {slice.map((q) => (
                <div key={q.id} className="space-y-1.5">
                  <label className="block text-sm font-medium text-slate-800 dark:text-slate-100">
                    {q.question}
                    {q.allow_skip === false && <span className="text-red-500 ml-1">*</span>}
                  </label>
                  {q.why_it_matters && (
                    <p className="text-xs text-slate-400 dark:text-slate-500">{q.why_it_matters}</p>
                  )}

                  {q.input_type === 'single_select' && Array.isArray(q.options) && q.options.length > 0 ? (
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-1">
                      {q.options.map((opt) => (
                        <button
                          key={opt.id}
                          type="button"
                          onClick={() => setAnswer(q.id, opt.label)}
                          className={`text-left px-3 py-2 rounded-lg border text-sm transition-colors ${
                            answers[q.id] === opt.label
                              ? 'border-blue-500 bg-blue-50 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300'
                              : 'border-slate-200 dark:border-slate-700 hover:border-blue-300 text-slate-700 dark:text-slate-300'
                          }`}
                        >
                          <div className="font-medium">{opt.label}</div>
                          {opt.description && <div className="text-xs text-slate-400 mt-0.5">{opt.description}</div>}
                        </button>
                      ))}
                    </div>
                  ) : q.input_type === 'multi_select' && Array.isArray(q.options) && q.options.length > 0 ? (
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-1">
                      {q.options.map((opt) => {
                        const selected = Array.isArray(answers[q.id]) && answers[q.id].includes(opt.label);
                        return (
                          <button
                            key={opt.id}
                            type="button"
                            onClick={() => {
                              const current = Array.isArray(answers[q.id]) ? answers[q.id] : [];
                              setAnswer(
                                q.id,
                                selected ? current.filter((v) => v !== opt.label) : [...current, opt.label]
                              );
                            }}
                            className={`text-left px-3 py-2 rounded-lg border text-sm transition-colors ${
                              selected
                                ? 'border-blue-500 bg-blue-50 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300'
                                : 'border-slate-200 dark:border-slate-700 hover:border-blue-300 text-slate-700 dark:text-slate-300'
                            }`}
                          >
                            {opt.label}
                          </button>
                        );
                      })}
                    </div>
                  ) : (
                    <textarea
                      rows={4}
                      value={answers[q.id] || ''}
                      onChange={(e) => setAnswer(q.id, e.target.value)}
                      className="w-full text-sm rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2 text-slate-800 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
                      placeholder={q.allow_skip === false ? 'Required — this affects compliance' : 'Optional'}
                    />
                  )}
                </div>
              ))}

              {totalPages > 1 && (
                <div className="flex items-center justify-between pt-2">
                  <button
                    type="button"
                    disabled={page <= 0}
                    onClick={() => setQPage((p) => Math.max(0, p - 1))}
                    className="text-sm px-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 disabled:opacity-40 hover:bg-slate-50 dark:hover:bg-slate-800"
                  >
                    ← Previous
                  </button>
                  <div className="flex gap-1">
                    {Array.from({ length: totalPages }, (_, i) => (
                      <button
                        key={i}
                        type="button"
                        onClick={() => setQPage(i)}
                        className={`w-7 h-7 rounded text-xs ${
                          i === page
                            ? 'bg-blue-600 text-white'
                            : 'border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300'
                        }`}
                      >
                        {i + 1}
                      </button>
                    ))}
                  </div>
                  <button
                    type="button"
                    disabled={page >= totalPages - 1}
                    onClick={() => setQPage((p) => Math.min(totalPages - 1, p + 1))}
                    className="text-sm px-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 disabled:opacity-40 hover:bg-slate-50 dark:hover:bg-slate-800"
                  >
                    Next →
                  </button>
                </div>
              )}

              {error && <div className="text-sm text-red-600 dark:text-red-400">{error}</div>}
            </div>
            );
          })()}
        </div>

        <div className="p-6 border-t border-slate-200 dark:border-slate-700 flex items-center justify-between gap-3">
          <button
            type="button"
            onClick={onCancel}
            className="text-sm text-slate-500 hover:text-slate-700 dark:hover:text-slate-300"
          >
            Cancel
          </button>
          {phase === 'questions' && (
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleSkipAll}
                disabled={submitting}
                className="flex items-center gap-1.5 text-sm px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-500 hover:bg-slate-50 dark:hover:bg-slate-800"
              >
                <SkipForward className="w-4 h-4" /> Skip &amp; generate now
              </button>
              <button
                type="button"
                onClick={handleSubmitAnswers}
                disabled={submitting}
                className="flex items-center gap-1.5 text-sm px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-medium disabled:opacity-60"
              >
                {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <ArrowRight className="w-4 h-4" />}
                {analysis?.is_final_round === false ? 'Continue' : 'Generate Proposal'}
              </button>
            </div>
          )}
          {phase === 'error' && (
            <button
              type="button"
              onClick={onCancel}
              className="text-sm px-4 py-2 rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300"
            >
              Close
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
