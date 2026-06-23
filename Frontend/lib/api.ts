const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface JobStatus {
  job_id: string;
  status: "running" | "done" | "error";
  paper_id?: number;
  error?: string;
  message?: string;
  progress?: number;
}

export interface PaperOut {
  id: number;
  board: string | null;
  level: string | null;
  subject: string | null;
  year: string | null;
  paper_code: string | null;
  tier: string | null;
  question_count: number;
}

export interface AnswerOut {
  id: number;
  category: string;
  answer_text: string;
  awarded_marks: number | null;
  verified: boolean | null;
}

export interface QuestionOut {
  id: number;
  question_number: string;
  question_text: string;
  marks: number | null;
  answer: string | null;
  mark_breakdown: string | null;
  additional_guidance: string | null;
  verification_status: string | null;
  has_image: boolean;
  answers: AnswerOut[];
}

export interface PaperDetailOut {
  id: number;
  board: string | null;
  level: string | null;
  subject: string | null;
  year: string | null;
  paper_code: string | null;
  tier: string | null;
  questions: QuestionOut[];
}

export async function runPipeline(body: {
  qp_url: string;
  qp_metadata_raw: string;
  ms_url: string;
  ms_metadata_raw: string;
}): Promise<JobStatus> {
  const res = await fetch(`${BASE}/api/pipeline/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getJobStatus(jobId: string): Promise<JobStatus> {
  const res = await fetch(`${BASE}/api/pipeline/status/${jobId}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function listPapers(): Promise<PaperOut[]> {
  const res = await fetch(`${BASE}/api/papers`, { cache: "no-store" });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getPaper(id: number): Promise<PaperDetailOut> {
  const res = await fetch(`${BASE}/api/papers/${id}`, { cache: "no-store" });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export function imageUrl(questionId: number): string {
  return `${BASE}/api/questions/${questionId}/image`;
}
