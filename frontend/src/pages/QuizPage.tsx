import { useCallback, useEffect, useState } from "react";
import { apiClient, ApiError } from "../api/client";
import { useApi } from "../hooks/useApi";
import { LoadingSpinner } from "../components/LoadingSpinner";
import { ErrorBanner } from "../components/ErrorBanner";
import "./QuizPage.css";

interface QuizQuestion {
  id: number;
  question: string;
  options: { A: string; B: string; C: string; D: string };
  correctAnswer: string;
  explanation: string;
  topic: string;
  difficulty: string;
}

interface QuizData {
  questions: QuizQuestion[];
  generatedAt?: string;
  careerGoal?: string;
}

export function QuizPage() {
  const { data, loading, error, execute, reset } = useApi<QuizData>(
    useCallback(async () => {
      try {
        return await apiClient.get<QuizData>("/quiz");
      } catch (err) {
        if (err instanceof ApiError && err.statusCode === 404) return null as unknown as QuizData;
        throw err;
      }
    }, [])
  );

  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [showResults, setShowResults] = useState(false);

  useEffect(() => { execute(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleGenerate() {
    setGenerateError(null);
    setGenerating(true);
    setAnswers({});
    setShowResults(false);
    try {
      await apiClient.post("/quiz", { numQuestions: 5 });
      await execute();
    } catch (err) {
      const msg = err instanceof ApiError ? err.toUserMessage() : "Failed to generate quiz.";
      setGenerateError(msg);
    } finally {
      setGenerating(false);
    }
  }

  function selectAnswer(questionId: number, option: string) {
    if (showResults) return;
    setAnswers((prev) => ({ ...prev, [questionId]: option }));
  }

  function handleSubmit() {
    setShowResults(true);
  }

  function getScore(): number {
    if (!data?.questions) return 0;
    return data.questions.filter((q) => answers[q.id] === q.correctAnswer).length;
  }

  if (loading && data === null) return <LoadingSpinner label="Loading quiz…" />;
  if (error && data === null) return <ErrorBanner message={error} onDismiss={reset} />;

  return (
    <div className="quiz-page">
      <div className="quiz-page__top-row">
        <h1 className="quiz-page__heading">🧠 Practice Quiz</h1>
        <button
          className="quiz-page__generate-btn"
          onClick={handleGenerate}
          disabled={generating}
          aria-busy={generating}
        >
          {generating ? "Generating…" : "✨ Generate New Quiz"}
        </button>
      </div>

      {generateError && <ErrorBanner message={generateError} onDismiss={() => setGenerateError(null)} />}

      {!data || !data.questions || data.questions.length === 0 ? (
        <div className="quiz-page__empty">
          <p>No quiz yet. Click "Generate New Quiz" to create exam-style questions based on your career goal and resources.</p>
        </div>
      ) : (
        <>
          {data.careerGoal && (
            <p className="quiz-page__meta">
              📎 Based on: <strong>{data.careerGoal}</strong>
              {data.generatedAt && <> · Generated {new Date(data.generatedAt).toLocaleDateString()}</>}
            </p>
          )}

          {showResults && (
            <div className="quiz-page__score" role="alert">
              <span className="quiz-page__score-text">
                Score: {getScore()} / {data.questions.length}
              </span>
              <span className="quiz-page__score-pct">
                ({Math.round((getScore() / data.questions.length) * 100)}%)
              </span>
            </div>
          )}

          <ol className="quiz-page__questions">
            {data.questions.map((q) => (
              <li key={q.id} className="quiz-card">
                <div className="quiz-card__header">
                  <span className="quiz-card__topic">{q.topic}</span>
                  <span className={`quiz-card__difficulty quiz-card__difficulty--${q.difficulty?.toLowerCase()}`}>
                    {q.difficulty}
                  </span>
                </div>
                <p className="quiz-card__question">{q.question}</p>
                <div className="quiz-card__options">
                  {Object.entries(q.options).map(([key, value]) => {
                    const isSelected = answers[q.id] === key;
                    const isCorrect = key === q.correctAnswer;
                    let cls = "quiz-card__option";
                    if (showResults && isCorrect) cls += " quiz-card__option--correct";
                    if (showResults && isSelected && !isCorrect) cls += " quiz-card__option--wrong";
                    if (!showResults && isSelected) cls += " quiz-card__option--selected";

                    return (
                      <button
                        key={key}
                        className={cls}
                        onClick={() => selectAnswer(q.id, key)}
                        disabled={showResults}
                      >
                        <span className="quiz-card__option-key">{key}</span>
                        <span className="quiz-card__option-text">{value}</span>
                      </button>
                    );
                  })}
                </div>
                {showResults && (
                  <div className="quiz-card__explanation">
                    <strong>{answers[q.id] === q.correctAnswer ? "✅ Correct!" : "❌ Incorrect"}</strong>
                    <p>{q.explanation}</p>
                  </div>
                )}
              </li>
            ))}
          </ol>

          {!showResults && (
            <button
              className="quiz-page__submit-btn"
              onClick={handleSubmit}
              disabled={Object.keys(answers).length < data.questions.length}
            >
              Submit Answers
            </button>
          )}
        </>
      )}
    </div>
  );
}
