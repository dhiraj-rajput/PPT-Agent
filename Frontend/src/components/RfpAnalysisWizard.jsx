import { useState, useEffect, useRef } from 'react';
import { Loader2, FileSearch, HelpCircle, CheckCircle2, ArrowRight, SkipForward, AlertTriangle } from 'lucide-react';
import { api } from '../lib/api.jsx';

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
export default function RfpAnalysisWizard({ rfpFiles, templateFile, onCancel, onReadyToGenerate }) {
  const [phase, setPhase] = useState('analyzing'); // analyzing | questions | error
  const [taskId, setTaskId] = useState(null);
  const [analysis, setAnalysis] = useState(null); // { rfp_type, summary, outline, questions, round, is_final_round }
  const [answers, setAnswers] = useState({}); // { [questionId]: value }
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const pollRef = useRef(null);
  const startedRef = useRef(false);

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;
    (async () => {
      try {
        const { task_id } = await api.analyzeRfp(rfpFiles, templateFile);
        setTaskId(task_id);
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
        if (state.status === 'completed') {
          clearInterval(pollRef.current);
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
            // Nothing to ask -- go straight to generation.
            onReadyToGenerate(taskId, []);
          }
        } else if (state.status === 'failed') {
          clearInterval(pollRef.current);
          setError(state.message || 'RFP analysis failed.');
          setPhase('error');
        }
      } catch (err) {
        // Transient poll errors are fine; only bail after the caller's own
        // network layer gives up.
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
      if (Array.isArray(res.questions) && res.questions.length > 0 && !res.is_final_round) {
        setAnalysis((prev) => ({ ...prev, questions: res.questions, round: res.round, is_final_round: res.is_final_round }));
        setAnswers({});
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
            <div className="flex flex-col items-center justify-center py-10 gap-3 text-slate-500 dark:text-slate-400">
              <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
              <p className="text-sm text-center">
                Parsing every page of your RFP, mapping its required annexures/forms, and building a
                response outline that matches this specific tender — this can take a minute or two for
                large documents.
              </p>
            </div>
          )}

          {phase === 'error' && (
            <div className="text-sm text-red-600 dark:text-red-400 py-4">{error}</div>
          )}

          {phase === 'questions' && analysis && (
            <div className="space-y-5">
              {analysis.summary && (
                <div className="text-sm text-slate-600 dark:text-slate-300 bg-slate-50 dark:bg-slate-800 rounded-lg p-3 border border-slate-200 dark:border-slate-700">
                  {analysis.summary}
                </div>
              )}

              {analysis.questions.map((q) => (
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
                      rows={2}
                      value={answers[q.id] || ''}
                      onChange={(e) => setAnswer(q.id, e.target.value)}
                      className="w-full text-sm rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2 text-slate-800 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
                      placeholder={q.allow_skip === false ? 'Required — this affects compliance' : 'Optional'}
                    />
                  )}
                </div>
              ))}

              {error && <div className="text-sm text-red-600 dark:text-red-400">{error}</div>}
            </div>
          )}
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
