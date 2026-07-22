import { useState, useEffect } from 'react';
import { Sparkles, CheckCircle2, ChevronRight, ChevronLeft, FileText, Settings, Layers, HelpCircle, AlertCircle, Loader2, X } from 'lucide-react';
import { api } from '../lib/api.jsx';

export default function PreGenerationWizard({ tenderId, solicitationNumber, proposalType = 'Prime RFP Response', onCancel, onConfirmGenerate }) {
  const [step, setStep] = useState(1); // 1: Questions, 2: Outline Preview, 3: Finalize
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Question & Answers state
  const [questions, setQuestions] = useState([]);
  const [answers, setAnswers] = useState({}); // { question_id: [selected_option_ids] }

  // Company selection states
  const [ownCompany, setOwnCompany] = useState(null);
  const [selectedCompanyId, setSelectedCompanyId] = useState('parent');

  useEffect(() => {
    api.getOwnCompanyProfile()
      .then(data => {
        setOwnCompany(data || null);
      })
      .catch(err => console.error("Error loading company profile for wizard:", err));
  }, []);

  // Outline state
  const [outline, setOutline] = useState(null);
  const [sections, setSections] = useState([]);
  const [generatingOutline, setGeneratingOutline] = useState(false);

  // Fetch wizard questions on mount
  useEffect(() => {
    setLoading(true);
    const params = { proposal_type: proposalType };
    if (tenderId) params.tender_id = tenderId;

    api.getPreviewQuestions(params)
      .then((data) => {
        setQuestions(data.questions || []);
        const initialAnswers = {};
        (data.questions || []).forEach((q) => {
          if (q.recommended_option_id) {
            initialAnswers[q.id] = [q.recommended_option_id];
          } else if (q.options?.length > 0) {
            initialAnswers[q.id] = [q.options[0].id];
          }
        });
        setAnswers(initialAnswers);
        setLoading(false);
      })
      .catch((err) => {
        console.warn('Failed to load pre-generation questions:', err);
        setError('Could not load customization questions.');
        setLoading(false);
      });
  }, [tenderId, proposalType]);

  const handleOptionToggle = (questionId, optionId, isMultiSelect = false) => {
    setAnswers((prev) => {
      const current = prev[questionId] || [];
      if (isMultiSelect) {
        if (current.includes(optionId)) {
          return { ...prev, [questionId]: current.filter((id) => id !== optionId) };
        } else {
          return { ...prev, [questionId]: [...current, optionId] };
        }
      } else {
        return { ...prev, [questionId]: [optionId] };
      }
    });
  };

  const handleGenerateOutline = () => {
    setGeneratingOutline(true);
    const formattedAnswers = Object.keys(answers).map((qId) => ({
      question_id: qId,
      selected_option_ids: answers[qId] || [],
    }));

    const selectedProfile = selectedCompanyId === 'parent'
      ? {
          name: ownCompany?.name,
          description: ownCompany?.description,
          uei: ownCompany?.uei,
          cage_code: ownCompany?.cage_code,
          primary_naics: ownCompany?.primary_naics,
          primary_naics_desc: ownCompany?.primary_naics_desc,
          city: ownCompany?.city,
          state: ownCompany?.state,
          email: ownCompany?.email,
          phone: ownCompany?.phone,
          size: ownCompany?.size,
          certifications: ownCompany?.certifications
        }
      : ownCompany?.sub_companies?.[parseInt(selectedCompanyId)];

    const payload = {
      tender_id: tenderId,
      solicitation_number: solicitationNumber,
      proposal_type: proposalType,
      answers: formattedAnswers,
      company_profile: selectedProfile
    };

    api.getPreviewOutline(payload)
      .then((data) => {
        setOutline(data);
        setSections(data.sections || []);
        setGeneratingOutline(false);
        setStep(2);
      })
      .catch((err) => {
        console.warn('Outline API error, continuing with standard layout:', err);
        setGeneratingOutline(false);
        setStep(2);
      });
  };

  const toggleSectionIncluded = (index) => {
    setSections((prev) => {
      const updated = [...prev];
      updated[index] = { ...updated[index], included: !updated[index].included };
      return updated;
    });
  };

  const updateSectionTitle = (index, newTitle) => {
    setSections((prev) => {
      const updated = [...prev];
      updated[index] = { ...updated[index], title: newTitle };
      return updated;
    });
  };

  const updateSectionDescription = (index, newDesc) => {
    setSections((prev) => {
      const updated = [...prev];
      updated[index] = { ...updated[index], description: newDesc };
      return updated;
    });
  };

  const deleteSection = (index) => {
    setSections((prev) => prev.filter((_, i) => i !== index));
  };

  const addSection = () => {
    setSections((prev) => [
      ...prev,
      { key: `custom_${Date.now()}`, title: 'New Section', word_budget: 300, key_points: [], description: '', included: true }
    ]);
  };

  const handleStartGeneration = () => {
    const selectedProfile = selectedCompanyId === 'parent'
      ? {
          name: ownCompany?.name,
          description: ownCompany?.description,
          uei: ownCompany?.uei,
          cage_code: ownCompany?.cage_code,
          primary_naics: ownCompany?.primary_naics,
          primary_naics_desc: ownCompany?.primary_naics_desc,
          city: ownCompany?.city,
          state: ownCompany?.state,
          email: ownCompany?.email,
          phone: ownCompany?.phone,
          size: ownCompany?.size,
          certifications: ownCompany?.certifications
        }
      : ownCompany?.sub_companies?.[parseInt(selectedCompanyId)];

    const wizardConfig = {
      answers,
      sections: sections.filter((s) => s.included),
      company_profile: selectedProfile
    };
    onConfirmGenerate(wizardConfig);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-navy-950/80 p-4 backdrop-blur-md" onClick={onCancel}>
      <div className="w-full max-w-3xl rounded-2xl bg-white dark:bg-navy-800 shadow-2xl overflow-hidden border border-slate-100 dark:border-navy-700" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-100 dark:border-navy-700 p-5 bg-gradient-to-r from-brand-600 to-brand-700 text-white">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-white/10 backdrop-blur-md text-white">
              <Sparkles size={20} />
            </div>
            <div>
              <h3 className="text-base font-extrabold leading-tight">Proposal Generation Wizard</h3>
              <p className="text-xs text-brand-100 mt-0.5">Customize strategy & structure before AI generation</p>
            </div>
          </div>
          <button onClick={onCancel} className="rounded-lg p-2 text-white/80 hover:text-white hover:bg-white/10 transition-colors">
            <X size={20} />
          </button>
        </div>

        {/* Step Indicator */}
        <div className="flex items-center justify-between border-b border-slate-100 dark:border-navy-700 bg-slate-50 dark:bg-navy-900 px-6 py-3 text-xs font-semibold">
          <div className={`flex items-center gap-2 ${step >= 1 ? 'text-brand-600 dark:text-brand-400' : 'text-slate-400'}`}>
            <span className={`flex h-5 w-5 items-center justify-center rounded-full text-[10px] ${step >= 1 ? 'bg-brand-500 text-white' : 'bg-slate-200 text-slate-600'}`}>1</span>
            Strategy Alignment
          </div>
          <ChevronRight size={14} className="text-slate-300" />
          <div className={`flex items-center gap-2 ${step >= 2 ? 'text-brand-600 dark:text-brand-400' : 'text-slate-400'}`}>
            <span className={`flex h-5 w-5 items-center justify-center rounded-full text-[10px] ${step >= 2 ? 'bg-brand-500 text-white' : 'bg-slate-200 text-slate-600'}`}>2</span>
            Outline Preview
          </div>
          <ChevronRight size={14} className="text-slate-300" />
          <div className={`flex items-center gap-2 ${step >= 3 ? 'text-brand-600 dark:text-brand-400' : 'text-slate-400'}`}>
            <span className={`flex h-5 w-5 items-center justify-center rounded-full text-[10px] ${step >= 3 ? 'bg-brand-500 text-white' : 'bg-slate-200 text-slate-600'}`}>3</span>
            Finalize
          </div>
        </div>

        {/* Modal Body */}
        <div className="p-6 max-h-[60vh] overflow-y-auto">
          {loading ? (
            <div className="flex flex-col items-center justify-center py-12">
              <Loader2 className="animate-spin text-brand-500" size={32} />
              <p className="mt-3 text-sm text-slate-500">Preparing wizard questions...</p>
            </div>
          ) : step === 1 ? (
            /* STEP 1: Questions */
            <div className="space-y-6">
              {ownCompany && (
                <div className="rounded-xl border border-slate-200 dark:border-navy-700 p-4 bg-slate-50 dark:bg-navy-900/60 shadow-sm">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-brand-600 dark:text-brand-400 bg-brand-50 dark:bg-navy-800 px-2 py-0.5 rounded">
                    Entity Selection
                  </span>
                  <h4 className="text-sm font-bold text-navy-900 dark:text-white mt-1 mb-3">Select Bidding Company / Sub-Company Entity</h4>
                  <div className="grid grid-cols-1 gap-2.5">
                    {/* Parent Company Option */}
                    <div
                      onClick={() => setSelectedCompanyId('parent')}
                      className={`flex items-start gap-3 rounded-xl border p-3 cursor-pointer transition-all ${
                        selectedCompanyId === 'parent'
                          ? 'border-brand-500 bg-brand-50/30 dark:bg-brand-950/20 shadow-sm'
                          : 'border-slate-200 dark:border-navy-700 bg-white dark:bg-navy-800 hover:border-brand-300'
                      }`}
                    >
                      <input
                        type="radio"
                        checked={selectedCompanyId === 'parent'}
                        onChange={() => {}}
                        className="mt-1 text-brand-500 focus:ring-brand-400"
                      />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <p className="text-xs font-bold text-navy-900 dark:text-white">{ownCompany.name} (Parent Company)</p>
                          <span className="inline-flex items-center gap-0.5 text-[9px] font-extrabold bg-blue-50 text-blue-700 dark:bg-blue-950/50 dark:text-blue-300 px-1.5 py-0.2 rounded">
                            Main
                          </span>
                        </div>
                        <p className="text-[10px] text-slate-500 mt-0.5">UEI: {ownCompany.uei} · CAGE: {ownCompany.cage_code || 'N/A'} · NAICS: {ownCompany.primary_naics || 'N/A'}</p>
                      </div>
                    </div>

                    {/* Sub-companies Options */}
                    {(ownCompany.sub_companies || []).map((sub, idx) => (
                      <div
                        key={idx}
                        onClick={() => setSelectedCompanyId(idx.toString())}
                        className={`flex items-start gap-3 rounded-xl border p-3 cursor-pointer transition-all ${
                          selectedCompanyId === idx.toString()
                            ? 'border-brand-500 bg-brand-50/30 dark:bg-brand-950/20 shadow-sm'
                            : 'border-slate-200 dark:border-navy-700 bg-white dark:bg-navy-800 hover:border-brand-300'
                        }`}
                      >
                        <input
                          type="radio"
                          checked={selectedCompanyId === idx.toString()}
                          onChange={() => {}}
                          className="mt-1 text-brand-500 focus:ring-brand-400"
                        />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <p className="text-xs font-bold text-navy-900 dark:text-white">{sub.name} (Subsidiary)</p>
                          </div>
                          <p className="text-[10px] text-slate-500 mt-0.5">UEI: {sub.uei} · CAGE: {sub.cage_code || 'N/A'} · NAICS: {sub.primary_naics || 'N/A'}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {questions.map((q) => (
                <div key={q.id} className="rounded-xl border border-slate-100 dark:border-navy-700 p-4 bg-slate-50/50 dark:bg-navy-900/50">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-brand-600 dark:text-brand-400 bg-brand-50 dark:bg-navy-800 px-2 py-0.5 rounded">
                      {q.category}
                    </span>
                    {q.is_multi_select && <span className="text-[10px] text-slate-400">Select all that apply</span>}
                  </div>
                  <h4 className="text-sm font-bold text-navy-900 dark:text-white mb-3">{q.question}</h4>
                  <div className="space-y-2">
                    {q.options?.map((opt) => {
                      const isSelected = (answers[q.id] || []).includes(opt.id);
                      const isRecommended = q.recommended_option_id === opt.id;
                      return (
                        <div
                          key={opt.id}
                          onClick={() => handleOptionToggle(q.id, opt.id, q.is_multi_select)}
                          className={`flex items-start gap-3 rounded-xl border p-3 cursor-pointer transition-all ${
                            isSelected
                              ? 'border-brand-500 bg-brand-50/30 dark:bg-brand-950/20 shadow-sm'
                              : 'border-slate-200 dark:border-navy-700 bg-white dark:bg-navy-800 hover:border-brand-300'
                          }`}
                        >
                          <input
                            type={q.is_multi_select ? 'checkbox' : 'radio'}
                            checked={isSelected}
                            onChange={() => {}}
                            className="mt-1 text-brand-500 focus:ring-brand-400 rounded"
                          />
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <p className="text-xs font-bold text-navy-900 dark:text-white">{opt.label}</p>
                              {isRecommended && (
                                <span className="inline-flex items-center gap-0.5 text-[9px] font-extrabold bg-amber-100 text-amber-800 dark:bg-amber-950/50 dark:text-amber-300 px-1.5 py-0.2 rounded">
                                  Recommended
                                </span>
                              )}
                            </div>
                            {opt.description && <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">{opt.description}</p>}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          ) : step === 2 ? (
            /* STEP 2: Outline Preview */
            <div className="space-y-4">
              <div className="flex items-center justify-between bg-brand-50 dark:bg-navy-900 p-3.5 rounded-xl border border-brand-100 dark:border-navy-700">
                <div>
                  <p className="text-xs font-bold text-brand-900 dark:text-brand-200">Document Outline Structure</p>
                  <p className="text-[11px] text-brand-700 dark:text-brand-400 mt-0.5">
                    Est. {outline?.total_estimated_pages || 10} Pages · ~{outline?.total_estimated_words || 4500} Words
                  </p>
                </div>
                <span className="text-xs font-bold bg-brand-500 text-white px-2.5 py-1 rounded-lg">
                  {sections.filter((s) => s.included).length} Sections Included
                </span>
              </div>

              <div className="space-y-2.5">
                {sections.map((sec, idx) => (
                  <div
                    key={sec.key || idx}
                    className={`rounded-xl border p-3.5 transition-all ${
                      sec.included
                        ? 'border-slate-200 dark:border-navy-700 bg-white dark:bg-navy-800'
                        : 'border-slate-100 dark:border-navy-900 bg-slate-50/50 opacity-60'
                    }`}
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex items-start gap-3 w-full pr-2">
                        <input
                          type="checkbox"
                          checked={sec.included}
                          onChange={() => toggleSectionIncluded(idx)}
                          className="h-4 w-4 mt-1 rounded text-brand-500 focus:ring-brand-400"
                        />
                        <div className="flex-1 space-y-2">
                          <input
                            type="text"
                            value={sec.title}
                            onChange={(e) => updateSectionTitle(idx, e.target.value)}
                            className="w-full text-xs font-bold bg-transparent border-b border-transparent focus:border-brand-500 focus:outline-none text-navy-900 dark:text-white"
                            placeholder="Section Title"
                          />
                          <p className="text-[10px] text-slate-400 mt-0.5">Target budget: ~{sec.word_budget} words</p>
                          <textarea
                            value={sec.description ?? (sec.key_points ? sec.key_points.join('\n') : '')}
                            onChange={(e) => updateSectionDescription(idx, e.target.value)}
                            className="w-full text-[11px] text-slate-600 dark:text-slate-300 bg-slate-50 dark:bg-navy-900 border border-slate-200 dark:border-navy-700 rounded-md p-2 mt-2 focus:outline-none focus:ring-1 focus:ring-brand-500"
                            rows={3}
                            placeholder="Enter section key points or description..."
                          />
                        </div>
                      </div>
                      <button onClick={() => deleteSection(idx)} className="p-1.5 text-slate-400 hover:text-red-500 transition-colors bg-slate-50 hover:bg-red-50 dark:bg-navy-700 dark:hover:bg-red-900/30 rounded-lg">
                        <X size={14} />
                      </button>
                    </div>
                  </div>
                ))}
                
                <button 
                  onClick={addSection}
                  className="w-full py-3 border-2 border-dashed border-slate-200 dark:border-navy-700 rounded-xl text-xs font-semibold text-slate-500 hover:text-brand-600 hover:border-brand-300 dark:hover:border-brand-700 transition-colors flex items-center justify-center gap-2"
                >
                  <Layers size={14} />
                  Add Custom Section
                </button>
              </div>
            </div>
          ) : (
            /* STEP 3: Finalize */
            <div className="flex flex-col items-center justify-center py-6 text-center space-y-4">
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-emerald-50 text-emerald-600 dark:bg-emerald-950/40 dark:text-emerald-400">
                <CheckCircle2 size={32} />
              </div>
              <div>
                <h4 className="text-base font-extrabold text-navy-900 dark:text-white">Ready to Generate Document</h4>
                <p className="text-xs text-slate-500 dark:text-slate-400 max-w-md mt-1">
                  The document will be generated using AI and styled according to OrbitAvanya branding rules.
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Footer Controls */}
        <div className="flex items-center justify-between border-t border-slate-100 dark:border-navy-700 p-4 bg-slate-50 dark:bg-navy-900">
          {step > 1 ? (
            <button
              onClick={() => setStep((s) => s - 1)}
              className="inline-flex items-center gap-1 rounded-xl border border-slate-200 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 dark:border-navy-700 dark:bg-navy-800 dark:text-slate-200"
            >
              <ChevronLeft size={14} /> Back
            </button>
          ) : (
            <button
              onClick={onCancel}
              className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 dark:border-navy-700 dark:bg-navy-800 dark:text-slate-200"
            >
              Cancel
            </button>
          )}

          {step === 1 ? (
            <button
              onClick={handleGenerateOutline}
              disabled={generatingOutline}
              className="inline-flex items-center gap-1.5 rounded-xl bg-brand-500 px-5 py-2 text-xs font-bold text-white shadow-soft hover:bg-brand-600 disabled:opacity-50"
            >
              {generatingOutline ? <Loader2 size={14} className="animate-spin" /> : null}
              Next: Outline Preview <ChevronRight size={14} />
            </button>
          ) : step === 2 ? (
            <button
              onClick={() => setStep(3)}
              className="inline-flex items-center gap-1.5 rounded-xl bg-brand-500 px-5 py-2 text-xs font-bold text-white shadow-soft hover:bg-brand-600"
            >
              Next: Finalize <ChevronRight size={14} />
            </button>
          ) : (
            <button
              onClick={handleStartGeneration}
              className="inline-flex items-center gap-2 rounded-xl bg-emerald-500 px-6 py-2.5 text-xs font-extrabold text-white shadow-soft hover:bg-emerald-600"
            >
              <Sparkles size={14} /> Start Proposal Generation
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
